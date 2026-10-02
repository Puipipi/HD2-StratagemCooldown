# -*- coding: utf-8 -*-
"""Read the VehicleCooldown runtime log (and optionally SmoothBoot's) and report
what the addon actually did, stage by stage.

    python -B tools/analyze_vehicle_cooldown_log.py
    python -B tools/analyze_vehicle_cooldown_log.py --log <path> --smooth-log <path> --json

This is a read-only diagnostic: it never touches the game, its files or memory.
It exists because "the mod does nothing" is only answerable from the log, and
the 1.5.x family proved that a mod can stay silent for 165 sessions without
leaving a single trace.
"""
import argparse
import collections
import datetime
import io
import json
import os
import re
import sys

DEFAULT_LOG = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'CowboyBingus',
                           'Helldivers2', 'Logs', 'VehicleCooldown.log')
DEFAULT_SMOOTH = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'CowboyBingus',
                              'Helldivers2', 'Logs', 'SmoothBoot.log')

STAGES = [
    ('locate failed', re.compile(r'STOPPED at load')),
    ('located', re.compile(r'table located at load')),
    ('installed', re.compile(r'v([\d.]+) installed')),
    ('gate', re.compile(r'uptime gate passed')),
    ('records', re.compile(r'vehicle records appeared')),
    ('no-records', re.compile(r'no vehicle records yet')),
    ('applied', re.compile(r'cooldown applied to')),
    ('re-applied', re.compile(r'cooldown re-applied')),
    ('rollback', re.compile(r'ABORTED \+ rolled back')),
    ('disabled', re.compile(r'cooldown disabled')),
    ('relocate', re.compile(r're-resolved table base')),
    ('error', re.compile(r'error: ')),
    ('heartbeat', re.compile(r'heartbeat: ')),
]


def read_lines(path):
    if not path or not os.path.exists(path):
        return None
    with io.open(path, encoding='utf-8', errors='replace') as fh:
        return [ln.rstrip('\r\n') for ln in fh if ln.strip()]


def sessions(lines):
    """Split the log into load-to-load sessions."""
    out, current = [], None
    for line in lines:
        if 'table located at load' in line and current is not None:
            out.append(current)
            current = None
        if 'installed:' in line:
            if current is None:
                current = []
            current.append(line)
        elif current is not None:
            current.append(line)
    if current:
        out.append(current)
    return out


def analyse(log_path):
    lines = read_lines(log_path)
    if lines is None:
        return {'log': log_path, 'readable': False}
    counts = collections.Counter()
    versions = collections.Counter()
    for line in lines:
        for name, pattern in STAGES:
            if pattern.search(line):
                counts[name] += 1
        m = re.search(r'v([\d.]+) installed', line)
        if m:
            versions[m.group(1)] += 1
    runs = sessions(lines)
    last = runs[-1] if runs else []
    reached = [name for name, pattern in STAGES
               if any(pattern.search(ln) for ln in last)]
    verdict = 'unknown'
    if 'applied' in reached or 're-applied' in reached:
        verdict = 'applied a cooldown in the last session'
    elif 'rollback' in reached:
        verdict = 'write failed and was rolled back (safe stand-down)'
    elif 'error' in reached:
        verdict = 'raised an error in the last session (see M.last_error / log)'
    elif 'no-records' in reached:
        verdict = 'table readable but no vehicle record matched'
    elif 'gate' in reached:
        verdict = 'reached the uptime gate and produced no scan result'
    elif 'installed' in reached:
        verdict = 'installed but never reached the uptime gate'
    elif 'locate failed' in reached:
        verdict = 'stopped at load: the table could not be resolved'
    return {
        'log': log_path,
        'readable': True,
        'lines': len(lines),
        'sessions': len(runs),
        'versions': dict(versions),
        'counts': dict(counts),
        'last_session_stages': reached,
        'last_session': last[-8:],
        'verdict': verdict,
    }


def analyse_smooth(path):
    lines = read_lines(path)
    if lines is None:
        return {'log': path, 'readable': False}
    status = collections.Counter()
    phase = collections.Counter()
    samples = 0
    for line in lines:
        m = re.search(r'runtime state HD2VehicleCooldown: (.*)$', line)
        if not m:
            continue
        samples += 1
        body = m.group(1)
        s = re.search(r'status=([^,]+)', body)
        p = re.search(r'phase=([^,]+)', body)
        if s:
            status[s.group(1).strip()] += 1
        if p:
            phase[p.group(1).strip()] += 1
    return {'log': path, 'readable': True, 'samples': samples,
            'status': dict(status), 'phase': dict(phase)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', default=DEFAULT_LOG)
    parser.add_argument('--smooth-log', default=DEFAULT_SMOOTH)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    report = {'generated': datetime.datetime.now().isoformat(timespec='seconds'),
              'vehicle_cooldown': analyse(args.log),
              'smoothboot_snapshot': analyse_smooth(args.smooth_log)}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    vc = report['vehicle_cooldown']
    print('VehicleCooldown log: %s' % vc.get('log'))
    if not vc.get('readable'):
        print('  not found - the addon has never run on this machine (or a different LOCALAPPDATA)')
    else:
        print('  %d lines, %d session(s), versions %s' % (vc['lines'], vc['sessions'], vc['versions']))
        for name, _ in STAGES:
            if vc['counts'].get(name):
                print('    %-12s %d' % (name, vc['counts'][name]))
        print('  last session stages: %s' % (', '.join(vc['last_session_stages']) or 'none'))
        print('  verdict: %s' % vc['verdict'])
        for line in vc['last_session']:
            print('    | %s' % line)
    snap = report['smoothboot_snapshot']
    if snap.get('readable') and snap.get('samples'):
        print('SmoothBoot runtime snapshots: %d' % snap['samples'])
        for key, value in sorted(snap['status'].items(), key=lambda kv: -kv[1])[:6]:
            print('    status=%-58s %d' % (key[:58], value))
    return 0


if __name__ == '__main__':
    sys.exit(main())
