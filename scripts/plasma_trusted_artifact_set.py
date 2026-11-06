#!/usr/bin/env python3
"""Trusted Actions-only official artifact transport. Never invoke from Codex.

The authenticated Work Order supplies all pins. Only sanitized receipts and
read-only payloads cross the boundary; HTTP errors never include request data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import urllib.request
import urllib.parse
import zipfile

import plasma_trusted_z2_ci_artifact as kit

REPOSITORY = kit.REPOSITORY
OWNER = 'physicslu'
PRODUCERS = {
    'ps_kit': (kit.WORKFLOW, None),
    'factory': ('.github/workflows/ppu-bootstrap.yml', 'ppu-bootstrap-factory-bundle'),
    'engine_candidate': ('.github/workflows/swd-openocd5088-armv7-candidate.yml',
                         'plasma-openocd5088-armv7-candidate'),
}
LIMIT = 512 * 1024 * 1024
EXPANDED_LIMIT = 3 * 1024 * 1024 * 1024
MAX_FILES = 20000
need = kit.need


def validate_pins(pins):
    need(type(pins) is dict and set(pins) == set(PRODUCERS), 'ARTIFACT_SET_INVALID')
    fields = {'repository', 'workflow', 'run_id', 'artifact_id', 'source_sha',
              'zip_sha256', 'artifact_name', 'event', 'branch', 'pr_number'}
    for kind, pin in pins.items():
        workflow, name = PRODUCERS[kind]
        need(type(pin) is dict and set(pin) == fields, 'ARTIFACT_PIN_FIELDS_INVALID')
        need(pin['repository'] == REPOSITORY and pin['workflow'] == workflow,
             'ARTIFACT_PRODUCER_DENIED')
        for field in ('run_id', 'artifact_id'):
            need(type(pin[field]) is int and 0 < pin[field] < 10**15, 'ARTIFACT_ID_INVALID')
        need(type(pin['source_sha']) is str and kit.SHA40.fullmatch(pin['source_sha']) and
             type(pin['zip_sha256']) is str and kit.SHA256.fullmatch(pin['zip_sha256']),
             'ARTIFACT_DIGEST_INVALID')
        need(type(pin['artifact_name']) is str and
             ((name is not None and pin['artifact_name'] == name) or
              (name is None and kit.KIT_NAME.fullmatch(pin['artifact_name']) and
               pin['artifact_name'].endswith(pin['source_sha'][:12]))), 'ARTIFACT_NAME_DENIED')
        if kind == 'engine_candidate':
            need(pin['event'] == 'pull_request' and type(pin['pr_number']) is int and
                 pin['pr_number'] > 0 and type(pin['branch']) is str and
                 re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_.-]{0,120}', pin['branch']) and
                 pin['branch'] != 'main', 'ARTIFACT_PR_PIN_DENIED')
        else:
            need(pin['event'] in ('push', 'workflow_dispatch') and pin['branch'] == 'main' and
                 type(pin['pr_number']) is int and pin['pr_number'] == 0,
                 'ARTIFACT_MAIN_PIN_DENIED')
    return pins


def admit(kind, pin, run, listing, *, pr=None, now=None):
    repo = run.get('repository', {})
    need(repo.get('full_name') == REPOSITORY and type(repo.get('id')) is int and
         run.get('head_repository', {}).get('full_name') == REPOSITORY,
         'RUN_REPOSITORY_DENIED')
    need(run.get('id') == pin['run_id'] and type(run.get('id')) is int and
         run.get('path') == pin['workflow'] and run.get('event') == pin['event'] and
         run.get('head_branch') == pin['branch'] and run.get('head_sha') == pin['source_sha'] and
         run.get('status') == 'completed' and run.get('conclusion') == 'success' and
         type(run.get('run_attempt')) is int and run['run_attempt'] == 1 and
         run.get('actor', {}).get('login') == OWNER and
         run.get('triggering_actor', {}).get('login') == OWNER, 'RUN_PROVENANCE_DENIED')
    if kind == 'engine_candidate':
        need(type(pr) is dict and pr.get('number') == pin['pr_number'] and
             pr.get('user', {}).get('login') == OWNER and
             pr.get('head', {}).get('sha') == pin['source_sha'] and
             pr.get('head', {}).get('ref') == pin['branch'] and
             pr.get('head', {}).get('repo', {}).get('full_name') == REPOSITORY and
             pr.get('base', {}).get('ref') == 'main' and
             pr.get('base', {}).get('repo', {}).get('full_name') == REPOSITORY and
             any(p.get('number') == pin['pr_number'] and
                 p.get('head', {}).get('sha') == pin['source_sha'] and
                 p.get('head', {}).get('ref') == pin['branch']
                 for p in run.get('pull_requests', [])), 'RUN_PR_RELATION_DENIED')
    records = listing.get('artifacts')
    need(type(records) is list and type(listing.get('total_count')) is int and
         len(records) == listing['total_count'] <= 100, 'ARTIFACT_LIST_INCOMPLETE')
    matches = [r for r in records if r.get('name') == pin['artifact_name']]
    need(len(matches) == 1, 'ARTIFACT_NOT_UNIQUE')
    item = matches[0]
    producer = item.get('workflow_run', {})
    try:
        expires = datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00'))
        current = now or datetime.now(timezone.utc)
        unexpired = expires > current
    except (KeyError, TypeError, ValueError):
        unexpired = False
    need(item.get('id') == pin['artifact_id'] and type(item.get('id')) is int and
         item.get('expired') is False and unexpired and
         item.get('digest') == 'sha256:' + pin['zip_sha256'] and
         type(item.get('size_in_bytes')) is int and 0 < item['size_in_bytes'] <= LIMIT and
         producer.get('id') == pin['run_id'] and producer.get('head_sha') == pin['source_sha'] and
         producer.get('head_branch') == pin['branch'] and
         producer.get('repository_id') == repo['id'], 'ARTIFACT_PROVENANCE_DENIED')
    return {**pin, 'size_in_bytes': item['size_in_bytes']}


def safe_name(name):
    need(type(name) is str and name and '\\' not in name and '\x00' not in name and
         not name.startswith('/') and not any(ord(c) < 32 for c in name), 'ARCHIVE_PATH_DENIED')
    pure = PurePosixPath(name.rstrip('/'))
    need(pure.as_posix() == name.rstrip('/') and '..' not in pure.parts,
         'ARCHIVE_PATH_DENIED')
    return pure.as_posix()


def untar(path, destination, *, budget=None):
    destination.mkdir(mode=0o700)
    seen, total = set(), 0
    if budget is None:
        budget = [0]
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            name = safe_name(member.name)
            need(name not in seen and len(seen) < MAX_FILES, 'ARCHIVE_DUPLICATE_OR_EXCESS')
            seen.add(name)
            need(member.isfile() or member.isdir(), 'ARCHIVE_LINK_DENIED')
            need(not member.mode & 0o7000, 'ARCHIVE_MODE_DENIED')
            target = destination / name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            total += member.size
            budget[0] += member.size
            need(budget[0] <= EXPANDED_LIMIT and 0 <= member.size <= EXPANDED_LIMIT and total <= EXPANDED_LIMIT,
                 'ARCHIVE_SIZE_DENIED')
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            need(source is not None, 'ARCHIVE_FILE_DENIED')
            with source, target.open('xb') as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
    return destination


def checksums(root, sums, expected=None):
    need(sums.is_file() and sums.stat().st_size <= 4 * 1024 * 1024, 'CHECKSUMS_MISSING')
    seen = set()
    for line in sums.read_text(encoding='ascii').splitlines():
        need(len(line) > 66 and line[64:66] == '  ' and kit.SHA256.fullmatch(line[:64]),
             'CHECKSUM_FORMAT_DENIED')
        name = safe_name(line[66:])
        need(name not in seen, 'CHECKSUM_DUPLICATE')
        seen.add(name)
        file = root / name
        need(file.is_file() and not file.is_symlink() and kit.sha256(file) == line[:64],
             'CHECKSUM_MISMATCH')
    if expected is None:
        expected = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != sums}
    need(seen == expected, 'CHECKSUM_FILE_SET_DENIED')


def verify_payload(kind, pin, archive, sidecar, destination, helper):
    need(sidecar.stat().st_size <= 256 and sidecar.read_text(encoding='ascii').strip() ==
         f'{kit.sha256(archive)}  {archive.name}', 'SIDECAR_MISMATCH')
    if kind == 'ps_kit':
        kit.verify_kit_source(archive, sidecar, pin['source_sha'], pin['artifact_name'], helper=helper)
        budget = [0]
        expanded = untar(archive, destination, budget=budget)
        root = expanded / pin['artifact_name']
        checksums(root, root / 'SHA256SUMS')
        # Full nested runtime checksums, never execution of shipped tooling.
        nested_archives = list((root / 'artifacts').glob('*.tar.gz'))
        need(len(nested_archives) == 3, 'NESTED_ARTIFACT_SET_DENIED')
        for index, nested in enumerate(nested_archives):
            nested_sidecar = nested.with_name(nested.name + '.sha256')
            need(nested_sidecar.is_file() and nested_sidecar.stat().st_size <= 256 and
                 nested_sidecar.read_text(encoding='ascii').strip() ==
                 f'{kit.sha256(nested)}  {nested.name}', 'NESTED_SIDECAR_MISMATCH')
            nested_root = untar(nested, expanded / ('nested-' + str(index)), budget=budget)
            roots = list(nested_root.iterdir())
            need(len(roots) == 1 and roots[0].is_dir(), 'NESTED_ROOT_DENIED')
            checksums(roots[0], roots[0] / 'SHA256SUMS')
        return
    root = untar(archive, destination)
    if kind == 'factory':
        roots = list(root.iterdir())
        need(len(roots) == 1 and roots[0].is_dir() and
             roots[0].name == 'plasma-ppu-bootstrap-0.1.0-' + pin['source_sha'][:12],
             'FACTORY_ROOT_DENIED')
        root = roots[0]
        checksums(root, root / 'SHA256SUMS')
        manifest = kit.read_json(root / 'manifest.json')
        need(manifest.get('git_sha') == pin['source_sha'] and
             manifest.get('schema_version') == 1 and
             manifest.get('product') == 'plasma-ppu-bootstrap' and
             manifest.get('bootstrap_version') == '0.1.0' and
             all(manifest.get(k) is False for k in ('runtime_included', 'control_token_included', 'fpga_update')) and
             manifest.get('publisher_authenticity') == 'not_qualified' and
             (root / 'scripts/ppu_site_adapter_abi5.py').is_file() and
             (root / 'scripts/ppu-bootstrap.py').is_file(), 'FACTORY_IDENTITY_DENIED')
    else:
        checksums(root, root / 'openocd.sha256', {'openocd', 'plasma_swd_site_admission.py'})
        evidence = kit.read_json(root / 'candidate-evidence.json')
        binary, admission = root / 'openocd', root / 'plasma_swd_site_admission.py'
        need(evidence.get('schema') == 'plasma.openocd.armv7.candidate-evidence.v1' and
             evidence.get('plasma_source_sha') == pin['source_sha'] and
             evidence.get('openocd_source_sha') == '5088db4c9154ca833c6d558381074b33672e127a' and
             evidence.get('architecture') == 'ARMv7' and
             evidence.get('openocd_binary_sha256') == kit.sha256(binary) and
             evidence.get('site_admission_script_sha256') == kit.sha256(admission) and
             evidence.get('hardware_runtime_ready') is False, 'ENGINE_IDENTITY_DENIED')
        with binary.open('rb') as stream:
            elf = stream.read(20)
        need(len(elf) == 20 and elf[:6] == b'\x7fELF\x01\x01' and elf[18:20] == b'\x28\x00',
             'ENGINE_ARCHITECTURE_DENIED')
        need(all(marker in binary.read_bytes() for marker in
                 (b'plasma_swd', b'PS_OWNER_SITE_NOT_SELECTED', b'PS_OWNER_BIND_DENIED')) and
             b'release.abi_version == 0x00050001' in admission.read_bytes() and
             b'\"abi_version\": 5' in admission.read_bytes() and (root / 'tcl').is_dir() and
             (root / 'PROVENANCE.txt').is_file(), 'ENGINE_ABI_DENIED')


def verify_zip(kind, pin, path, destination, *, helper):
    need(path.is_file() and not path.is_symlink() and
         path.stat().st_size == pin['size_in_bytes'] <= LIMIT and
         kit.sha256(path) == pin['zip_sha256'], 'ZIP_BYTES_DENIED')
    need(not destination.exists() and not destination.is_symlink(), 'DESTINATION_EXISTS')
    destination.mkdir(mode=0o700)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [safe_name(i.filename) for i in infos]
        need(len(names) == len(set(names)) and 2 <= len(names) <= 3 and
             all('/' not in n for n in names), 'ZIP_FILE_SET_DENIED')
        archives = [n for n in names if n.endswith('.tar.gz')]
        need(len(archives) == 1, 'ZIP_FILE_SET_DENIED')
        name = archives[0]
        expected = {name, name + '.sha256'}
        if kind == 'factory':
            expected.add('bootstrap-install-evidence.json')
            need(name == 'plasma-ppu-bootstrap-0.1.0-' + pin['source_sha'][:12] + '.tar.gz',
                 'FACTORY_ARCHIVE_NAME_DENIED')
        elif kind == 'engine_candidate':
            need(name == 'plasma-openocd5088-armv7-candidate.tar.gz', 'ENGINE_ARCHIVE_NAME_DENIED')
        else:
            need(name == pin['artifact_name'] + '.tar.gz', 'KIT_ARCHIVE_NAME_DENIED')
        need(set(names) == expected, 'ZIP_FILE_SET_DENIED')
        total = 0
        for info in infos:
            total += info.file_size
            need(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG) and
                 not info.is_dir() and not info.flag_bits & 1 and
                 0 < info.file_size <= LIMIT and total <= LIMIT and
                 (not info.filename.endswith('.sha256') or info.file_size <= 256),
                 'ZIP_MEMBER_DENIED')
            with archive.open(info) as source, (destination / info.filename).open('xb') as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
    payload = destination / name
    sidecar = destination / (name + '.sha256')
    verify_payload(kind, pin, payload, sidecar, destination / 'payload', helper)
    # Expose the original archive/sidecar; extracted validation scratch is not an execution route.
    return {**{k: v for k, v in pin.items() if k != 'size_in_bytes'},
            'status': 'TRUSTED_OFFICIAL_ARTIFACT_VERIFIED', 'kind': kind,
            **({'engine_identity': 'plasma_swd:5'} if kind == 'engine_candidate' else {}),
            'artifact_path': str(payload.resolve()), 'sidecar_path': str(sidecar.resolve()),
            'payload_sha256': kit.sha256(payload)}


class NoBearerRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # GitHub redirects artifact ZIPs to signed storage. Strip authorization
        # rather than allowing urllib's default cross-host header propagation.
        need(newurl.startswith('https://') and not urllib.parse.urlsplit(newurl).username,
             'DOWNLOAD_REDIRECT_DENIED')
        return urllib.request.Request(newurl, headers={'Accept': 'application/octet-stream'})


def fetch(endpoint, token, *, binary=False):
    request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + '/' + endpoint,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with urllib.request.build_opener(NoBearerRedirect()).open(request, timeout=120) as response:
            data = response.read((LIMIT if binary else 4 * 1024 * 1024) + 1)
        need(len(data) <= (LIMIT if binary else 4 * 1024 * 1024), 'DOWNLOAD_SIZE_DENIED')
        return data if binary else json.loads(data)
    except Exception:
        raise kit.ArtifactDenied('GITHUB_FETCH_DENIED') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', type=Path, required=True)
    parser.add_argument('--work-order-sha256', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--github-env', type=Path, required=True)
    args = parser.parse_args()
    try:
        import plasma_development_dispatch as dispatch
        order = dispatch.parse_dynamic_work_order(json.loads(args.event.read_text()))
        need(dispatch.work_order_digest(order) == args.work_order_sha256, 'WORK_ORDER_DIGEST_DENIED')
        pins = validate_pins(order['artifact_sources'])
        token = os.environ.pop('GH_TOKEN', '')
        need(bool(token), 'GITHUB_PERMISSION_MISSING')
        need(not args.destination.exists() and not args.destination.is_symlink(), 'DESTINATION_EXISTS')
        args.destination.mkdir(mode=0o700)
        receipts = {}
        for kind, pin in pins.items():
            run = fetch(f"actions/runs/{pin['run_id']}", token)
            listing = fetch(f"actions/runs/{pin['run_id']}/artifacts?per_page=100", token)
            pr = fetch(f"pulls/{pin['pr_number']}", token) if pin['pr_number'] else None
            admitted = admit(kind, pin, run, listing, pr=pr)
            path = args.destination / (kind + '.zip')
            path.write_bytes(fetch(f"actions/artifacts/{pin['artifact_id']}/zip", token, binary=True))
            receipts[kind] = verify_zip(kind, admitted, path, args.destination / kind,
                helper=Path(__file__).with_name('ppu-bootstrap-kit.py'))
        receipt = args.destination / 'verified-receipt.json'
        receipt.write_text(json.dumps(receipts, sort_keys=True) + '\n')
        # All-or-nothing export. No metadata JSON or signed URL is exported.
        for path in args.destination.rglob('*'):
            path.chmod(0o500 if path.is_dir() else 0o400)
        args.destination.chmod(0o500)
        with args.github_env.open('a') as output:
            output.write(f'PLASMA_OFFICIAL_ARTIFACT_RECEIPT_PATH={receipt.resolve()}\n')
            for kind, record in receipts.items():
                label = "Z2_KIT" if kind == "ps_kit" else kind.upper()
                output.write(f"PLASMA_{label}_ARTIFACT_PATH={record['artifact_path']}\n")
                output.write(f"PLASMA_{label}_SIDECAR_PATH={record['sidecar_path']}\n")
    except Exception:
        print('TRUSTED_ARTIFACT_SET_BLOCKED', file=__import__('sys').stderr)
        return 2
    print('TRUSTED_ARTIFACT_SET_VERIFIED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
