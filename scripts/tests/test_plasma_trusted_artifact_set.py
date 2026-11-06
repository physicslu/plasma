#!/usr/bin/env python3
"""Deterministic host-only producer, archive and credential-boundary tests."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import plasma_trusted_artifact_set as m
import plasma_development_dispatch as dispatch

SHA = 'a' * 40
NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)


def pins():
    result = {}
    for kind, (workflow, name) in m.PRODUCERS.items():
        engine = kind == 'engine_candidate'
        result[kind] = dict(repository=m.REPOSITORY, workflow=workflow,
            run_id=123, artifact_id=456, source_sha=SHA, zip_sha256='b' * 64,
            artifact_name=name or 'plasma-z2-ps-kit-0.2.1-' + SHA[:12],
            event='pull_request' if engine else 'workflow_dispatch',
            branch='agent/engine' if engine else 'main', pr_number=1300 if engine else 0)
    return result


def metadata(pin):
    pr = dict(number=1300, user={'login': m.OWNER},
              head={'sha': SHA, 'ref': pin['branch'], 'repo': {'full_name': m.REPOSITORY}},
              base={'ref': 'main', 'repo': {'full_name': m.REPOSITORY}})
    run = dict(id=123, path=pin['workflow'], event=pin['event'], head_sha=SHA,
               head_branch=pin['branch'], repository={'full_name': m.REPOSITORY, 'id': 42},
               head_repository={'full_name': m.REPOSITORY}, status='completed',
               conclusion='success', run_attempt=1, actor={'login': m.OWNER},
               triggering_actor={'login': m.OWNER}, pull_requests=[pr])
    artifact = dict(id=456, name=pin['artifact_name'], expired=False,
                    expires_at='2026-11-20T00:00:00Z', size_in_bytes=100,
                    digest='sha256:' + pin['zip_sha256'],
                    workflow_run={'id': 123, 'head_sha': SHA, 'head_branch': pin['branch'],
                                  'repository_id': 42})
    return run, dict(total_count=1, artifacts=[artifact]), pr


def tar_bytes(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o644
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


def summed(files):
    return ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                   for name, data in files.items()).encode()


def fixture_zip(base, kind, *, change=None):
    pin = pins()[kind]
    if kind == 'factory':
        manifest = dict(schema_version=1, product='plasma-ppu-bootstrap', bootstrap_version='0.1.0',
            git_sha=SHA, runtime_included=False, control_token_included=False, fpga_update=False,
            publisher_authenticity='not_qualified')
        files = {'manifest.json': json.dumps(manifest).encode(),
                 'scripts/ppu_site_adapter_abi5.py': b'# abi', 'scripts/ppu-bootstrap.py': b'# factory'}
        if change:
            change(files)
        files['SHA256SUMS'] = summed(files)
        root = 'plasma-ppu-bootstrap-0.1.0-' + SHA[:12]
        files = {root + '/' + name: data for name, data in files.items()}
        name = root + '.tar.gz'
    elif kind == 'engine_candidate':
        binary = b'\x7fELF\x01\x01' + b'\0' * 12 + b'\x28\0' + b'plasma_swd PS_OWNER_SITE_NOT_SELECTED PS_OWNER_BIND_DENIED'
        admission = b'release.abi_version == 0x00050001\n"abi_version": 5'
        files = {'openocd': binary, 'plasma_swd_site_admission.py': admission,
                 'tcl/target.cfg': b'# tcl', 'PROVENANCE.txt': b'candidate'}
        files['openocd.sha256'] = summed({k: files[k] for k in ('openocd', 'plasma_swd_site_admission.py')})
        files['candidate-evidence.json'] = json.dumps(dict(schema='plasma.openocd.armv7.candidate-evidence.v1',
            plasma_source_sha=SHA, openocd_source_sha='5088db4c9154ca833c6d558381074b33672e127a',
            architecture='ARMv7', hardware_runtime_ready=False,
            openocd_binary_sha256=hashlib.sha256(binary).hexdigest(),
            site_admission_script_sha256=hashlib.sha256(admission).hexdigest())).encode()
        if change:
            change(files)
        name = 'plasma-openocd5088-armv7-candidate.tar.gz'
    else:
        files = {}
        for nested_name, nested_root, manifest in (
            ('plasma-ppu-0.2.1-linux-armv7l.tar.gz', 'plasma-release',
             {'git_sha': SHA, 'role': 'ppu', 'target': 'linux-armv7l', 'product_version': '0.2.1'}),
            ('plasma-python-3.10.1-linux-armv7l.tar.gz', 'python-runtime', {}),
            ('plasma-openocd-test-linux-armv7l.tar.gz', 'openocd-runtime', {})):
            inner = {'release.json': json.dumps(manifest).encode()}
            inner['SHA256SUMS'] = summed(inner)
            data = tar_bytes({nested_root + '/' + k: v for k, v in inner.items()})
            files['artifacts/' + nested_name] = data
            files['artifacts/' + nested_name + '.sha256'] = (hashlib.sha256(data).hexdigest() + '  ' + nested_name + '\n').encode()
        for script in ('plasmactl', 'plasmactl-z2-ps', 'ppu-bootstrap-deployment.py',
                       'ppu-z2-installer.py', 'ppu-z2-installer-core.py', 'z2-python-runtime.py', 'openocd-runtime.py'):
            files['scripts/' + script] = b'# script'
        if change:
            change(files)
        files['SHA256SUMS'] = summed(files)
        files = {pin['artifact_name'] + '/' + k: v for k, v in files.items()}
        name = pin['artifact_name'] + '.tar.gz'
    data = tar_bytes(files)
    path = base / 'artifact.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(name, data)
        archive.writestr(name + '.sha256', hashlib.sha256(data).hexdigest() + '  ' + name + '\n')
        if kind == 'factory':
            archive.writestr('bootstrap-install-evidence.json', '{}')
    pin.update(zip_sha256=m.kit.sha256(path), size_in_bytes=path.stat().st_size)
    return pin, path


class MetadataTests(unittest.TestCase):
    def test_all_three_owner_pins(self):
        m.validate_pins(pins())
        for kind, pin in pins().items():
            run, listing, pr = metadata(pin)
            self.assertEqual(m.admit(kind, pin, run, listing, pr=pr, now=NOW)['artifact_id'], 456)

    def test_bad_pins(self):
        for kind in m.PRODUCERS:
            for field, value in [('repository', 'evil/plasma'), ('workflow', '../wrong'),
                ('run_id', True), ('artifact_id', 0), ('source_sha', 'a' * 12),
                ('zip_sha256', 'bad'), ('artifact_name', '../artifact'), ('event', 'schedule'),
                ('branch', '../wrong'), ('pr_number', True)]:
                candidate = pins(); candidate[kind][field] = value
                with self.subTest(kind=kind, field=field), self.assertRaises(m.kit.ArtifactDenied):
                    m.validate_pins(candidate)
        for value in ({}, {'ps_kit': pins()['ps_kit']}, {**pins(), 'extra': {}}):
            with self.assertRaises(m.kit.ArtifactDenied):
                m.validate_pins(value)

    def test_run_adversaries(self):
        for kind, pin in pins().items():
            for field, value in [('id', 124), ('path', 'wrong'), ('event', 'schedule'),
                ('head_sha', 'c' * 40), ('head_branch', 'wrong'), ('status', 'queued'),
                ('conclusion', 'failure'), ('run_attempt', 2), ('actor', {'login': 'intruder'}),
                ('triggering_actor', {'login': 'intruder'}), ('repository', {'full_name': 'evil/plasma'}),
                ('head_repository', {'full_name': 'evil/plasma'})]:
                run, listing, pr = metadata(pin); run[field] = value
                with self.subTest(kind=kind, field=field), self.assertRaises(m.kit.ArtifactDenied):
                    m.admit(kind, pin, run, listing, pr=pr, now=NOW)

    def test_artifact_adversaries(self):
        for kind, pin in pins().items():
            for field, value in [('id', 457), ('name', 'renamed'), ('expired', True),
                ('expires_at', '2020-01-01T00:00:00Z'), ('digest', 'sha256:' + 'd' * 64),
                ('size_in_bytes', m.LIMIT + 1), ('workflow_run', {'id': 124})]:
                run, listing, pr = metadata(pin); listing['artifacts'][0][field] = value
                with self.subTest(kind=kind, field=field), self.assertRaises(m.kit.ArtifactDenied):
                    m.admit(kind, pin, run, listing, pr=pr, now=NOW)
            for count in (0, 2):
                run, listing, pr = metadata(pin)
                listing['artifacts'] *= count; listing['total_count'] = count
                with self.assertRaises(m.kit.ArtifactDenied):
                    m.admit(kind, pin, run, listing, pr=pr, now=NOW)
        pin = pins()['engine_candidate']; run, listing, pr = metadata(pin)
        pr['head']['sha'] = 'c' * 40
        with self.assertRaises(m.kit.ArtifactDenied):
            m.admit('engine_candidate', pin, run, listing, pr=pr, now=NOW)


class PayloadTests(unittest.TestCase):
    def verify(self, kind, pin, path, base):
        return m.verify_zip(kind, pin, path, base / 'verified', helper=ROOT / 'scripts/ppu-bootstrap-kit.py')

    def test_real_nested_positive_all_classes(self):
        for kind in m.PRODUCERS:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); pin, path = fixture_zip(base, kind)
                self.assertEqual(self.verify(kind, pin, path, base)['status'], 'TRUSTED_OFFICIAL_ARTIFACT_VERIFIED')

    def test_internal_identity_or_checksum_tampering(self):
        changes = {
            'factory': lambda f: f.pop('manifest.json'),
            'engine_candidate': lambda f: f.update(openocd=b'tampered'),
            'ps_kit': lambda f: f.update({'artifacts/plasma-python-3.10.1-linux-armv7l.tar.gz': b'tampered'}),
        }
        for kind, change in changes.items():
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); pin, path = fixture_zip(base, kind, change=change)
                with self.assertRaises(Exception):
                    self.verify(kind, pin, path, base)

    def test_resealed_payload_still_requires_source_and_admission_identity(self):
        def wrong_factory(files):
            manifest = json.loads(files['manifest.json']); manifest['git_sha'] = 'c' * 40
            files['manifest.json'] = json.dumps(manifest).encode()
        def wrong_engine(files):
            evidence = json.loads(files['candidate-evidence.json']); evidence['plasma_source_sha'] = 'c' * 40
            files['candidate-evidence.json'] = json.dumps(evidence).encode()
        def wrong_admission(files):
            evidence = json.loads(files['candidate-evidence.json']); evidence['site_admission_script_sha256'] = 'c' * 64
            files['candidate-evidence.json'] = json.dumps(evidence).encode()
        def wrong_ps(files):
            name = 'plasma-ppu-0.2.1-linux-armv7l.tar.gz'
            inner = {'release.json': json.dumps(dict(git_sha='c' * 40, role='ppu',
                target='linux-armv7l', product_version='0.2.1')).encode()}
            inner['SHA256SUMS'] = summed(inner)
            data = tar_bytes({'plasma-release/' + k: v for k, v in inner.items()})
            files['artifacts/' + name] = data
            files['artifacts/' + name + '.sha256'] = (hashlib.sha256(data).hexdigest() + '  ' + name).encode()
        for kind, change in [('factory', wrong_factory), ('engine_candidate', wrong_engine),
                             ('engine_candidate', wrong_admission), ('ps_kit', wrong_ps)]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); pin, path = fixture_zip(base, kind, change=change)
                with self.assertRaises(m.kit.ArtifactDenied): self.verify(kind, pin, path, base)

    def test_wrong_zip_digest_and_size(self):
        for field, value in [('zip_sha256', '0' * 64), ('size_in_bytes', 1)]:
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); pin, path = fixture_zip(base, 'factory'); pin[field] = value
                with self.assertRaises(m.kit.ArtifactDenied):
                    self.verify('factory', pin, path, base)
                self.assertFalse((base / 'verified').exists())

    def test_zip_slip_symlink_duplicate_and_bomb(self):
        for variant in ('slip', 'symlink', 'duplicate', 'bomb'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); pin, path = fixture_zip(base, 'factory')
                with zipfile.ZipFile(path, 'a') as archive:
                    info = zipfile.ZipInfo('../outside' if variant == 'slip' else 'extra')
                    if variant == 'symlink':
                        info.create_system = 3; info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, b'x')
                    if variant == 'duplicate': archive.writestr(info, b'x')
                pin.update(zip_sha256=m.kit.sha256(path), size_in_bytes=path.stat().st_size)
                with self.assertRaises(m.kit.ArtifactDenied):
                    self.verify('factory', pin, path, base)

    def test_expected_zip_member_symlink_and_expansion_bomb(self):
        for variant in ('symlink', 'bomb'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); pin = pins()['engine_candidate']; path = base / 'artifact.zip'
                name = 'plasma-openocd5088-armv7-candidate.tar.gz'
                with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    info = zipfile.ZipInfo(name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    if variant == 'symlink':
                        info.create_system = 3; info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, b'x' * 100000)
                    archive.writestr(name + '.sha256', b'sidecar')
                pin.update(zip_sha256=m.kit.sha256(path), size_in_bytes=path.stat().st_size)
                with mock.patch.object(m, 'LIMIT', 10000):
                    with self.assertRaises(m.kit.ArtifactDenied):
                        self.verify('engine_candidate', pin, path, base)

    def test_tar_links_paths_and_expansion_limit(self):
        for variant in ('link', 'path', 'bomb'):
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); path = base / 'bad.tar.gz'
                with tarfile.open(path, 'w:gz') as archive:
                    member = tarfile.TarInfo('../escape' if variant == 'path' else 'payload')
                    if variant == 'link': member.type = tarfile.SYMTYPE; member.linkname = '/tmp/outside'
                    archive.addfile(member)
                with mock.patch.object(m, 'MAX_FILES', 0 if variant == 'bomb' else 20000):
                    with self.assertRaises(m.kit.ArtifactDenied):
                        m.untar(path, base / 'out')


class BoundaryTests(unittest.TestCase):
    def test_work_order_schema_and_digest(self):
        order = dict(schema=dispatch.WORK_ORDER_SCHEMA, execution_path='path3-codex',
            capability='codex-workspace', objective='Host only official artifacts validation',
            acceptance='Observe deterministic adversarial test results', artifact_sources=pins())
        event = {'comment': {'body': dispatch.WORK_ORDER_PREFIX + json.dumps(order)}}
        self.assertEqual(dispatch.parse_dynamic_work_order(event), order)
        old = dispatch.work_order_digest(order); order['artifact_sources']['factory']['run_id'] += 1
        self.assertNotEqual(old, dispatch.work_order_digest(order))
        order['artifact_source'] = {'run_id': 123, 'source_sha': SHA}
        event['comment']['body'] = dispatch.WORK_ORDER_PREFIX + json.dumps(order)
        with self.assertRaises(dispatch.Denied): dispatch.parse_dynamic_work_order(event)

    def test_workflow_token_isolation_and_permissions(self):
        source = (ROOT / '.github/workflows/plasma-engineering-runtime-dispatch.yml').read_text()
        step = source.split('      - name: Fetch and verify owner-pinned')[1].split('      - name: Codex develops')[0]
        self.assertIn('GH_TOKEN: ${{ github.token }}', step)
        self.assertIn('trusted/scripts/plasma_trusted_artifact_set.py', step)
        self.assertIn('actions: read', source)
        child = source.split('      - name: Codex develops')[1].split('      - name: Collect Path 3')[0]
        self.assertNotIn('GH_TOKEN:', child); self.assertNotIn('GITHUB_TOKEN:', child)
        self.assertNotIn('github.token', child)

    def test_trusted_transport_all_or_nothing_and_readonly_paths(self):
        for failure in (None, 'factory', 'permission'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); all_pins = {}; payloads = {}
                for kind in m.PRODUCERS:
                    folder = base / kind; folder.mkdir()
                    pin, path = fixture_zip(folder, kind)
                    pin.pop('size_in_bytes'); all_pins[kind] = pin; payloads[kind] = path.read_bytes()
                order = dict(schema=dispatch.WORK_ORDER_SCHEMA, execution_path='path3-codex',
                    capability='codex-workspace', objective='Official artifacts host only validation',
                    acceptance='Verify all or nothing trusted local payload paths', artifact_sources=all_pins)
                event = base / 'event.json'
                event.write_text(json.dumps({'comment': {'body': dispatch.WORK_ORDER_PREFIX + json.dumps(order)}}))
                output = base / 'github-env'; destination = base / 'verified'
                def fetch(endpoint, token, *, binary=False):
                    self.assertEqual(token, 'PRIVATE_TEST_TOKEN')
                    if binary:
                        # Fixture IDs are intentionally shared; calls occur per class in insertion order.
                        return payloads[current[0]]
                    if endpoint.startswith('pulls/'):
                        return metadata(all_pins[current[0]])[2]
                    if '/artifacts?' not in endpoint:
                        current[0] = next(sequence)
                        run, _, _ = metadata(all_pins[current[0]])
                        return run
                    pin = all_pins[current[0]]; _, listing, _ = metadata(pin)
                    listing['artifacts'][0]['size_in_bytes'] = len(payloads[current[0]])
                    listing['artifacts'][0]['expires_at'] = '2099-01-01T00:00:00Z'
                    if failure == current[0]: listing['artifacts'][0]['expired'] = True
                    return listing
                current = [None]; sequence = iter(m.PRODUCERS)
                args = ['verifier', '--event', str(event), '--work-order-sha256', dispatch.work_order_digest(order),
                        '--destination', str(destination), '--github-env', str(output)]
                with mock.patch.object(sys, 'argv', args), mock.patch.object(m, 'fetch', side_effect=fetch), \
                     mock.patch.dict(m.os.environ, {'GH_TOKEN': '' if failure == 'permission' else 'PRIVATE_TEST_TOKEN'}), \
                     mock.patch('sys.stderr', new_callable=io.StringIO), mock.patch('sys.stdout', new_callable=io.StringIO):
                    result = m.main()
                if failure:
                    self.assertEqual(result, 2); self.assertFalse(output.exists())
                else:
                    self.assertEqual(result, 0)
                    text = output.read_text()
                    self.assertNotIn('PRIVATE_TEST_TOKEN', text); self.assertNotIn('https:', text)
                    self.assertEqual(len(text.splitlines()), 7)
                    receipt = destination / 'verified-receipt.json'
                    self.assertEqual(set(json.loads(receipt.read_text())), set(m.PRODUCERS))
                    self.assertEqual(receipt.stat().st_mode & 0o777, 0o400)
                if destination.exists():
                    destination.chmod(0o700)
                    for path in destination.rglob('*'):
                        path.chmod(0o700 if path.is_dir() else 0o600)

    def test_no_token_missing_permission_or_transport_leak(self):
        with mock.patch.object(m.urllib.request, 'build_opener', side_effect=RuntimeError('Bearer SECRET signed-url')):
            with self.assertRaisesRegex(m.kit.ArtifactDenied, '^GITHUB_FETCH_DENIED$'):
                m.fetch('actions/runs/123', 'SECRET')
        request = m.urllib.request.Request('https://api.github.com/example', headers={'Authorization': 'Bearer SECRET'})
        redirected = m.NoBearerRedirect().redirect_request(request, None, 302, '', {}, 'https://storage.example/zip?signature=SECRET')
        self.assertIsNone(redirected.get_header('Authorization'))


if __name__ == '__main__':
    unittest.main()
