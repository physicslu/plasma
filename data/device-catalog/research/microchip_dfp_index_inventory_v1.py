#!/usr/bin/env python3
"""Offline-only Microchip Device Family Pack index discovery.

Parses archived *official* Packs Repository HTML with Python stdlib.
Support-list device names are firmware/tool discovery seeds, NOT manufacturer
exact ordering SKUs, product lifecycle, or complete MCU population.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ENDPOINT = 'https://packs.download.microchip.com/'
MAX_BYTES = 25_000_000
LANES = ('8bit', '16bit', '32bit-pic-sam', '32bit-avr-risc', 'wireless')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def lane_for(pack_name):
    """Conservative discovery heuristic; unresolved families remain explicitly so."""
    if pack_name.startswith(('PIC32CX-BZ', 'PIC32MZ-W', 'PIC32WK', 'PIC32WM',
                             'SAMR', 'WLR')):
        return 'wireless'
    if pack_name.startswith(('PIC10', 'PIC12', 'PIC16', 'PIC18', 'PIC-8bitAC',
                             'ATautomotive', 'ATmega', 'ATtiny', 'AVR-', 'XMEGA')):
        return '8bit'
    if pack_name.startswith(('PIC24', 'dsPIC', 'PIC-16bitAC')):
        return '16bit'
    if pack_name.startswith(('SAM9', 'SAMA')):
        return 'excluded_mpu_candidate'
    if pack_name.startswith(('PIC32', 'SAM')):
        return '32bit-pic-sam'
    return 'unclassified_or_non_mcu_pack'


class DevicePackParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pack = None
        self.packs = []
        self.capture = None
        self.capture_tag = None
        self.buffer = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = (attrs.get('class') or '').split()
        if tag == 'article' and 'pack-card' in classes:
            require(self.pack is None, 'nested pack cards')
            self.pack = {'html_id': attrs.get('id'), 'subtitle': None,
                         'badge': None, 'version': None,
                         'download_filename': None, 'device_names': [],
                         'announced_device_count': None, 'last_chip_id': None}
            return
        if self.pack is None:
            return
        if tag in ('a', 'span') and 'device-chip' in classes:
            chip_id = attrs.get('id')
            require(isinstance(chip_id, str) and bool(chip_id.strip()),
                    'missing manufacturer pack device identifier')
            self.pack['last_chip_id'] = chip_id
            self.pack['device_names'].append(chip_id)
        field = None
        if tag in ('div', 'span') and 'pack-subtitle' in classes:
            field = 'subtitle'
        elif tag == 'span' and 'pack-badge' in classes:
            field = 'badge'
        elif tag == 'span' and 'device-name' in classes:
            field = 'device_name'
        elif tag == 'a' and 'pack-version' in classes:
            field = 'version'
            self.pack['download_filename'] = attrs.get('href')
        elif tag == 'h4':
            field = 'heading'
        if field is not None:
            require(self.capture is None, 'nested capture labels')
            self.capture, self.capture_tag, self.buffer = field, tag, []

    def handle_data(self, data):
        if self.capture is not None:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if self.pack is None:
            return
        if self.capture is not None and tag == self.capture_tag:
            value = ''.join(self.buffer).strip()
            if self.capture == 'device_name':
                require(value == self.pack['last_chip_id'],
                        'device name disagrees with manufacturer pack chip identity')
            elif self.capture == 'heading':
                match = re.fullmatch(r'Supported Devices \((\d+)\)', value)
                if match:
                    require(self.pack['announced_device_count'] is None,
                            'duplicate supported-device table')
                    self.pack['announced_device_count'] = int(match.group(1))
            else:
                self.pack[self.capture] = value
            self.capture, self.capture_tag, self.buffer = None, None, []
        if tag == 'article':
            require(self.capture is None, 'unterminated card label')
            require(self.pack['html_id'] is not None, 'missing pack card identifier')
            self.packs.append(self.pack)
            self.pack = None


def parse_original_html(raw: bytes, source_sha256: str) -> dict:
    require(isinstance(raw, bytes) and 1_000 <= len(raw) <= MAX_BYTES,
            'unexpected manufacturer index byte length')
    require(b'<html' in raw[:1000].lower() and b'Microchip' in raw,
            'not an official-style Microchip packs HTML page')
    require(hashlib.sha256(raw).hexdigest() == source_sha256,
            'original manufacturer index digest mismatch')
    parser = DevicePackParser()
    parser.feed(raw.decode('utf-8-sig'))
    parser.close()
    require(parser.pack is None and parser.capture is None, 'incomplete card')
    require(len(parser.packs) > 0, 'no manufacturer pack cards')
    card_ids = [p['html_id'] for p in parser.packs]
    require(len(card_ids) == len(set(card_ids)), 'duplicate pack card identifiers')
    out = []
    for p in parser.packs:
        if p['badge'] != 'Device Pack':
            continue
        sub = p['subtitle']
        require(isinstance(sub, str) and ' • ' in sub, 'invalid manufacturer/publisher')
        publisher, name = sub.split(' • ', 1)
        ids = p['device_names']
        require(len(ids) > 0 and p['announced_device_count'] == len(ids),
                'manufacturer pack support-list count mismatch')
        require(len(set(ids)) == len(ids), 'duplicate device name in a pack')
        require(isinstance(p['version'], str) and p['version'].startswith('v'),
                'missing manufacturer pack version')
        require(isinstance(p['download_filename'], str) and
                p['download_filename'].endswith('.atpack') and
                '/' not in p['download_filename'], 'unsafe pack download path')
        out.append({'publisher': publisher, 'pack_name': name,
                    'pack_version': p['version'],
                    'pack_download_filename': p['download_filename'],
                    'device_names': ids, 'supported_name_count': len(ids),
                    'discovery_lane': lane_for(name)
                    if publisher == 'Microchip' else 'other_publisher'})
    microchip = [p for p in out if p['publisher'] == 'Microchip']
    all_names = [device for p in microchip for device in p['device_names']]
    require(len(set(all_names)) == len(all_names),
            'cross-pack repeated support names require explicit reconciliation')
    categories = {}
    for lane in (*LANES, 'excluded_mpu_candidate',
                 'unclassified_or_non_mcu_pack'):
        selected = [p for p in microchip if p['discovery_lane'] == lane]
        categories[lane] = {'pack_count': len(selected),
                            'candidate_device_name_count': sum(
                                p['supported_name_count'] for p in selected),
                            'pack_names': [p['pack_name'] for p in selected]}
    return {
        'schema_version': 1,
        'manufacturer': 'Microchip',
        'source_url': ENDPOINT,
        'source_bytes_sha256': source_sha256,
        'source_bytes_count': len(raw),
        'manufacturer_device_pack_count': len(microchip),
        'other_publisher_device_pack_count': len(out)-len(microchip),
        'observed_manufacturer_device_support_names': len(all_names),
        'observed_distinct_device_support_names': len(set(all_names)),
        'device_support_list_is_complete_commercial_sku_inventory': False,
        'lifecycle_verified': False,
        'population_boundary_validated': False,
        'global_active_denominator': None,
        'production_write_authorized': False,
        'lanes': categories,
        'device_packs': microchip,
    }


def archived_inventory(source_dir: Path):
    source_dir = Path(source_dir)
    manifest = json.loads((source_dir / 'manifest.json').read_text())
    require(isinstance(manifest, dict) and manifest.get('endpoint') == ENDPOINT,
            'unexpected source endpoint')
    require(manifest.get('population_boundary_validated') is False and
            manifest.get('production_write_authorized') is False,
            'unsafe source scope claim')
    raw = (source_dir / 'index.html').read_bytes()
    require(manifest.get('source_bytes') == len(raw), 'original source length mismatch')
    return parse_original_html(raw, manifest.get('sha256'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    inventory = archived_inventory(args.evidence_root)
    dst = args.output.resolve()
    require('production' not in dst.parts, 'Production output is forbidden')
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(inventory, indent=2, sort_keys=True)+'\n')
    print(json.dumps({key: value for key, value in inventory.items()
                      if key != 'device_packs'}, indent=2))


if __name__ == '__main__':
    main()
