# -*- coding: utf-8 -*-
"""Validate (and optionally build) HD2 Vehicle Cooldown without touching the game.

Hard rules, each learned from a real incident:
  * the source must compile under **LuaJIT**, not only plain Lua 5.1 - the game
    runs LuaJIT and a chunk that only PUC Lua accepts is a dead addon;
  * the file must be plain UTF-8 Lua without a BOM or NUL byte, and its
    ``-- HD2-Addon:`` declaration must match the resource path, because that is
    what the loader resolves and what the official packer checks;
  * no user32 symbol may be declared with ffi.cdef - LuaJIT's C namespace is
    process-global and a duplicate declaration silently breaks other mods;
  * the version reported by the source and the archive name must agree.

Usage (from the repository root):

    python -B work/standalone/build_vc.py --validate-only
    python -B work/standalone/build_vc.py --output-dir dist

Building needs the externally supplied Bingus packer in
``work/standalone/vendor/bingus/`` (see THIRD_PARTY_NOTICES.md).  Building never
deploys: import the ZIP in Arsenal yourself.
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import lupa.luajit21 as luajit

W = Path(__file__).resolve().parent
REPO = W.parents[1]
default_out = REPO / 'dist' if W.name == 'standalone' else REPO / 'dist'
parser = argparse.ArgumentParser(description='Build HD2 Vehicle Cooldown without deploying.')
parser.add_argument('--output-dir', type=Path, default=default_out)
parser.add_argument('--validate-only', action='store_true',
                    help='compile and audit the source without packaging')
args = parser.parse_args()
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)

RESOURCE = 'mods/codex/vehicle_cooldown'
# never change this: Arsenal identifies an existing installation by its GUID,
# so a new GUID would install a second copy instead of updating 1.5.1-fixed
GUID = 'e5a9c3d5-7d02-4f38-b956-1c2d3e4f5a6b'
DISPLAY = 'HD2 Vehicle Cooldown'

src_path = REPO / 'src' / 'vehicle_cooldown.lua'
raw = src_path.read_bytes()
src = raw.decode('utf-8')

# --- rule 1: plain UTF-8 Lua, correct header ---------------------------------
if raw.startswith(b'\xef\xbb\xbf'):
    raise SystemExit('source must not start with a UTF-8 BOM')
if b'\0' in raw:
    raise SystemExit('source must not contain a NUL byte')
first = src.splitlines()[0]
if first.strip() != '-- HD2-Addon: ' + RESOURCE:
    raise SystemExit('first line must declare the resource: -- HD2-Addon: %s (got %r)'
                     % (RESOURCE, first))
print('header: OK (%s)' % RESOURCE)

ver = re.search(r"M=\{version='([\d.]+)'", src)
if not ver:
    raise SystemExit('source does not declare M={version=...}')
version = ver.group(1)
print('version: %s (%d bytes)' % (version, len(raw)))

# --- rule 2: compiles under the runtime the game uses ------------------------
try:
    luajit.LuaRuntime().compile(src)
except Exception as exc:
    raise SystemExit('LuaJIT compile failed: %s' % exc)
print('LuaJIT compile: OK')

# --- rule 3: no user32 symbol in any ffi.cdef block --------------------------
USER32 = {'GetCursorPos', 'GetClientRect', 'ScreenToClient', 'GetForegroundWindow',
          'GetAsyncKeyState', 'GetWindowThreadProcessId', 'GetCurrentProcessId',
          'SetWindowsHookEx', 'CallNextHookEx', 'GetKeyState'}
declared = set()
for block in re.findall(r'ffi\.cdef\s*\[\[(.*?)\]\]', src, re.S):
    declared.update(m.group(1) for m in
                    re.finditer(r'([A-Za-z_]\w*)\s*\([^;()]*\)\s*;', block))
clash = declared & USER32
if clash:
    raise SystemExit('refusing to build: user32 symbol(s) declared: %s'
                     % ', '.join(sorted(clash)))
print('ffi.cdef symbols: %s (no user32)' % ', '.join(sorted(declared) or ['none']))

# --- rule 4: the API the loader has to provide -------------------------------
for need in ('CowboyBingusModLoader', 'ReadProcessMemory', 'WriteProcessMemory',
             'VirtualProtect', 'rawget(_G,KEY)'):
    if need not in src:
        raise SystemExit('source no longer references %s - dormant path broken?' % need)
print('loader contract: OK')

if args.validate_only:
    print('Source validation complete; no in-game claim.')
    raise SystemExit(0)

# --- the official Bingus addon envelope -------------------------------------
vendor = str(W / 'vendor' / 'bingus')
if not os.path.exists(os.path.join(vendor, 'build_addon.py')):
    raise SystemExit('external packer missing: %s (see THIRD_PARTY_NOTICES.md)' % vendor)
sys.path.insert(0, vendor)
import build_addon as official                                    # noqa: E402

target = str(OUT / ('HD2-VehicleCooldown-%s.zip' % version))
official.build_addon(RESOURCE, raw, GUID, target, DISPLAY)

# --- the shipped guide, lifted out of the source (single source of truth) ----
r0 = src.find('-- [guide:begin]')
r1 = src.find('-- [guide:end]')
assert r0 > 0 and r1 > r0, 'guide block missing from the source'
guide = src[r0 + len('-- [guide:begin]'):r1]
lines = []
for line in guide.splitlines():
    lines.append(line[3:] if line.startswith('-- ') else line[2:] if line.startswith('--') else line)
readme_txt = '\n'.join(lines).strip() + '\n'
assert len(readme_txt) > 200, 'guide block looks empty'
tmp = target + '.tmp'
with zipfile.ZipFile(target) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename == 'manifest.json':
            manifest = json.loads(data)
            manifest['Version'] = 1
            manifest.setdefault('Options', [])
            data = (json.dumps(manifest, indent=2) + '\n').encode()
        zout.writestr(info, data)
    zout.writestr('README.txt', readme_txt.replace('\n', '\r\n'))
os.replace(tmp, target)
print('built %s: %d bytes' % (os.path.basename(target), os.path.getsize(target)))
print('import it in Arsenal; this script never writes to the game directory.')
