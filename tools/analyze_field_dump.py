#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyse the addon's read-only field dump and rank call-in / drop-time candidates.

The addon (4.8.7+) logs one line per target record, once per session:

    ... fields <id> <name>: 50=3, 68=90, 84=120, ...

This tool parses those lines, collects every f32 field per record, and ranks the offsets that
look like a call-in / drop time:

  * the value is one of the times the game actually uses for arrivals (0, 2, 5, 10, 15, 20,
    25, 30, 45, 60, 90, 120 seconds)
  * the offset appears on many records (a per-stratagem field, not a one-off)
  * the known anchors are excluded: the charge count at 0x50 (integer) and the cooldown at
    0x68 (float) - a candidate that always equals the cooldown is just that field.

Usage:  python -B tools/analyze_field_dump.py [--log PATH] [--write-report]
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from collections import Counter, defaultdict

CALLIN_TIMES = {0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 45.0, 60.0, 90.0, 120.0}
KNOWN = {0x50: 'charges (int32)', 0x68: 'cooldown (f32)', 0x10: 'name pointer', 0x00: 'id',
         0x04: 'hash'}

DEFAULT_LOG = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'CowboyBingus', 'Helldivers2',
                           'Logs', 'VehicleCooldown.log')
LINE = re.compile(r'Z fields (\d+) (.+?): (.*)$')


def parse(log_path: str) -> dict[tuple[str, str], dict[int, float]]:
    records: dict[tuple[str, str], dict[int, float]] = {}
    with io.open(log_path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = LINE.search(line)
            if not m:
                continue
            rid, name, body = m.group(1), m.group(2), m.group(3)
            fields: dict[int, float] = {}
            for part in body.split(','):
                if '=' not in part:
                    continue
                off, val = part.strip().split('=', 1)
                try:
                    fields[int(off, 16)] = float(val)
                except ValueError:
                    continue
            if fields:
                records[(rid, name)] = fields
    return records


def analyse(records) -> tuple[Counter, dict[int, list[tuple[str, str, float]]]]:
    freq: Counter = Counter()
    hits: dict[int, list[tuple[str, str, float]]] = defaultdict(list)
    for (rid, name), fields in records.items():
        for off, val in fields.items():
            freq[off] += 1
            if val in CALLIN_TIMES:
                hits[off].append((rid, name, val))
    return freq, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', default=DEFAULT_LOG)
    ap.add_argument('--write-report', action='store_true')
    args = ap.parse_args()
    if not os.path.exists(args.log):
        print('log not found:', args.log)
        return 1
    records = parse(args.log)
    print('records with a field dump: %d' % len(records))
    if not records:
        print('no dump lines yet - the addon logs them once per session (4.8.7+), so run one game first')
        return 0
    freq, hits = analyse(records)
    print('\noffsets seen (top 15):')
    for off, count in freq.most_common(15):
        note = ('  <- ' + KNOWN[off]) if off in KNOWN else ''
        print('   %#06x  on %3d record(s)%s' % (off, count, note))
    print('\ncall-in-time candidates (value is a common arrival time, many records):')
    rows = []
    for off, examples in hits.items():
        if off in KNOWN:
            continue
        # a candidate that always tracks the cooldown is that field, not a new one
        same_as_cd = all(ex[2] == records[(ex[0], ex[1])].get(0x68, object()) for ex in examples)
        rows.append((len(examples), off, examples, same_as_cd))
    for count, off, examples, same_as_cd in sorted(rows, reverse=True)[:8]:
        tag = ' [tracks 0x68 - rejected]' if same_as_cd else ''
        print('   %#06x  on %d record(s)%s' % (off, count, tag))
        for rid, name, val in examples[:5]:
            print('        %-4s %-46s %s' % (rid, name[:46], val))
    if args.write_report:
        out = os.path.join(os.path.dirname(os.path.abspath(args.log)), 'field-dump-report.txt')
        with io.open(out, 'w', encoding='utf-8') as fh:
            fh.write('records: %d\n' % len(records))
            for off, count in freq.most_common():
                fh.write('offset %#06x on %d records\n' % (off, count))
        print('\nreport written:', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
