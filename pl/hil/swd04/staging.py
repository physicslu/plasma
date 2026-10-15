"""Host-only artifact/BIN verification and dependency-free offline kit creation.

Never opens devices, connects to a target, runs conversion tools or loads FPGA.
Missing recovery bytes produce a usable inspection kit but an explicit NO-GO.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile

from pl.hil.swd04 import contract as c


def bit_payload(data: bytes) -> bytes:
    """Parse the Xilinx tagged BIT envelope; reject truncation/trailing bytes."""
    def word(offset: int) -> int:
        return struct.unpack_from('>H', data, offset)[0]
    try:
        magic_len = word(0)
        c._require(data[2:2 + magic_len] == bytes.fromhex('0ff00ff00ff00ff000'),
                   'Unexpected BIT envelope magic')
        pos = 2 + magic_len
        c._require(word(pos) == 1, 'Missing BIT tag marker')
        pos += 2
        for tag in b'abcd':
            c._require(data[pos] == tag, 'Unexpected BIT metadata tag')
            length = word(pos + 1)
            pos += 3
            c._require(length > 0 and pos + length <= len(data), 'Truncated BIT metadata')
            if tag == ord('b'):
                c._require(data[pos:pos + length].rstrip(b'\0') == b'7z020clg400',
                           'Wrong BIT target part')
            pos += length
        c._require(data[pos] == ord('e'), 'Missing BIT payload tag')
        length = struct.unpack_from('>I', data, pos + 1)[0]
        pos += 5
        c._require(length > 0 and length % 4 == 0 and pos + length == len(data),
                   'BIT payload size mismatch')
        return data[pos:]
    except (IndexError, struct.error) as exc:
        raise c.SafetyError('Truncated BIT envelope') from exc


def verify_bin(bit: Path, firmware: Path) -> dict:
    """Compare every word with bootgen's byte-swapped Zynq payload.

    This checks conversion format/provenance, not physical configuration success.
    A BOOT.BIN/FSBL image, unswapped payload, BIT envelope or unreviewed extra bytes fail.
    """
    payload = bit_payload(bit.read_bytes())
    expected = bytearray(len(payload))
    for offset in range(0, len(payload), 4):
        expected[offset:offset + 4] = payload[offset:offset + 4][::-1]
    # Bootgen 2026.1 adds one 0x20000000 NOP to this qualified payload.
    # Verify that exact observed output, not arbitrary trailing padding.
    expected.extend(bytes.fromhex('00000020'))
    actual = firmware.read_bytes()
    c._require(actual == expected, 'BIN is not the exact bootgen Zynq swapped payload')
    c._require(c.sha256_file(firmware) == c.CANDIDATE_BIN_SHA256,
               'BIN does not match the qualified conversion digest')
    c._require(bytes.fromhex('665599aa') in actual[:256], 'Missing BIN sync word')
    return {'sha256': c.sha256_file(firmware), 'size_bytes': len(actual),
            'format': 'zynq_fpga_manager_word_swapped_raw_payload',
            'physical_configuration': 'NOT_RUN'}


def create_kit(candidate: c.Candidate, firmware: Path, output: Path) -> dict:
    c.verify_candidate(candidate)
    conversion = verify_bin(candidate.bit, firmware)
    # Verify all provided recovery bytes before creating any destination.
    recovery = candidate.recovery_bin.is_file() and candidate.recovery_hwh.is_file()
    if recovery:
        c.verify_artifacts(candidate)
    elif candidate.recovery_bin.is_file() or candidate.recovery_hwh.is_file():
        raise c.SafetyError('Recovery pair incomplete')
    output.mkdir(parents=True, exist_ok=False)
    files = {
        'artifacts/candidate.bit': candidate.bit,
        'artifacts/candidate.hwh': candidate.hwh,
        'artifacts/manifest.json': candidate.manifest,
        'artifacts/candidate.bin': firmware,
    }
    if recovery:
        files.update({'recovery/base.bin': candidate.recovery_bin,
                      'recovery/base.hwh': candidate.recovery_hwh})
    source_root = Path(__file__).resolve().parents[3]
    for p in sorted(Path(__file__).parent.glob('*.py')):
        files['pl/hil/swd04/' + p.name] = p
    checklist = source_root / 'docs/development/swd04-offline-execution-checklist.md'
    files['CHECKLIST.md'] = checklist if checklist.is_file() else source_root / 'CHECKLIST.md'
    for name, source in files.items():
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    # False-by-default operator templates are not readiness attestations.
    attestation = dict.fromkeys((
        'exclusive_pl_ownership_confirmed', 'uart_console_verified',
        'independent_power_recovery_verified', 'maintenance_window_confirmed',
        'restoration_operator_ready', 'no_external_dut_connected',
        'original_metadata_backed_up', 'uio_driver_reconciliation_planned'), False)
    attestation['schema_version'] = 1
    session = dict.fromkeys((
        'confirmed_after_gate2_merge', 'live_fpga_manager_load_supervised',
        'candidate_bitstream_loaded_and_verified', 'original_services_quiesced_for_pl_access',
        'all_prior_pl_consumers_isolated', 'uios_unbound_or_ownership_reconciled',
        'uart_console_verified', 'independent_power_recovery_verified',
        'no_external_dut_connected', 'operator_present_at_console',
        'original_metadata_backup_verified'), False)
    session.update(candidate_source=c.SOURCE_SHA, candidate_bit_sha256=c.BIT_SHA256,
                   candidate_hwh_sha256=c.HWH_SHA256,
                   candidate_bin_sha256=c.CANDIDATE_BIN_SHA256,
                   recovery_bin_sha256=c.RECOVERY_BIN_SHA256,
                   p0_sha256='', supervised_load_log_sha256='')
    templates = {'attestation': attestation}
    for phase in ('HIL01', 'HIL02', 'HIL03'):
        templates['session-' + phase] = dict(session, stage=phase)
    for name, data in templates.items():
        filename = 'templates/' + name + '.json'
        dest = output / filename
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
        files[filename] = dest
    checksums = {name: c.sha256_file(output / name) for name in files}
    report = {
        'qualification': 'SWD04_OFFLINE_STAGING',
        'candidate_source': c.SOURCE_SHA,
        'candidate_contract': 'PASS', 'bin_conversion': conversion,
        'recovery_bytes_verified': recovery,
        'physical_execution_readiness': 'REQUIRES_FRESH_TARGET_CHECKS' if recovery else 'NO_GO',
        'blockers': [] if recovery else ['Original base.bin and base.hwh bytes unavailable'],
        'runtime': {'architecture': 'pure Python; ARMv7 compatible source',
                    'python_minimum': '3.10', 'third_party_dependencies': [],
                    'system_commands': ['systemctl', 'sha256sum', 'curl'],
                    'armv7_execution': 'NOT_RUN'},
        'sha256': checksums, 'hardware_access': 'NOT_RUN',
        'live_authorization': 'NOT_GRANTED',
    }
    (output / 'staging-report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    checksums['staging-report.json'] = c.sha256_file(output / 'staging-report.json')
    (output / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(checksums.items())))
    # A fresh output directory ensures no accidental overwrite of archived kits.
    with tarfile.open(output / 'swd04-offline.tar.gz', 'x:gz') as archive:
        for name in sorted([*checksums, 'SHA256SUMS']):
            archive.add(output / name, arcname='swd04/' + name, recursive=False)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bit', 'hwh', 'manifest', 'candidate-bin', 'recovery-bin', 'recovery-hwh', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = create_kit(c.Candidate(args.bit, args.hwh, args.manifest,
                                       args.recovery_bin, args.recovery_hwh),
                            args.candidate_bin, args.output)
    except (OSError, ValueError, c.SafetyError) as exc:
        print('SWD04_STAGING_NO_GO: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['recovery_bytes_verified'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
