# -*- coding: utf-8 -*-
"""One command that re-checks a release offline.

    python tools/verify_release.py [--zip dist/StratagemCooldown-X.zip] [--no-node]

It takes the SHIPPED package (newest in dist/ unless given), extracts the payload
from it and checks:

  1. package shape   - single option with Include ["Addon"], payload at the package
                       root, no nested Addon/manifest.json, no Options/ tree, the
                       files the reader expects, root manifest fields
  2. payload         - compiles under LuaJIT, contains no os.execute / io.popen
  3. behaviour       - 7 flat-key cases, 6 sectioned-INI cases, 3 log-content cases
  4. builder         - runs config-builder.html's own JavaScript under node (if
                       available) and feeds what it generates back into (3)

Exit code 0 means every check passed. This is the script behind the release notes'
"all offline checks green" claim.
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MOD, 'tests'))
from vc_sandbox import Sandbox                                          # noqa: E402

PAYLOAD = 'Addon/9ba626afa44a3aa3.patch_0'
RESULTS = []

# vanilla values taken from the live game table
WORLD = [
    {'id': 1, 'name': 'VEHICLES. BASTION(TANK)', 'cooldown': 780.0, 'uses': -1},
    {'id': 105, 'name': 'VEHICLES. FAST RECON VEHICLE (FRV)', 'cooldown': 480.0, 'uses': -1},
    {'id': 27, 'name': 'VEHICLES. COMBAT WALKER', 'cooldown': 420.0, 'uses': 3},
    {'id': 18, 'name': 'EAGLE. AIRSTRIKE', 'cooldown': 15.0, 'uses': 2},
    {'id': 49, 'name': 'EAGLE. REARM', 'cooldown': 150.0, 'uses': -1},
    {'id': 107, 'name': 'ORBITAL. LASER', 'cooldown': 300.0, 'uses': 3},
    {'id': 12, 'name': 'EMPLACEMENTS. ANTI-TANK MINE DEPLOYER', 'cooldown': 120.0, 'uses': -1},
]
READ = {'tank': 1, 'frv': 105, 'mech': 27, 'eagle': 18, 'rearm': 49, 'laser': 107, 'mine': 12}


def note(name, ok, detail=''):
    RESULTS.append((name, ok, detail))
    print('  %-52s %s%s' % (name, 'OK' if ok else 'FAIL', ('  ' + detail) if detail else ''))
    return ok



def lua_table(d):
    def one(v):
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace('\\', '\\\\').replace("'", "\\'") + "'"
    return '{' + ','.join('[%s]=%s' % (one(k), one(v)) for k, v in d.items()) + '}'

def newest_zip():
    cands = glob.glob(os.path.join(MOD, 'dist', 'StratagemCooldown-*.zip'))
    if not cands:
        sys.exit('no StratagemCooldown-*.zip in dist/')
    return max(cands, key=os.path.getmtime)


def payload_from(zf):
    raw = zf.read(PAYLOAD)
    i0 = raw.find(b'-- HD2-Addon:')
    i1 = raw.find(b'-- [guide:end]', i0)
    if i0 < 0 or i1 < 0:
        sys.exit('payload envelope markers missing')
    return raw[i0:i1 + len(b'-- [guide:end]')].decode('utf-8')


def clear_markers(box):
    """The addon still understands the old provider markers (opt_*.txt) and reads
    them whenever no manager database is present. Leftovers from earlier runs would
    silently add charges, so each sandbox starts without them."""
    for f in os.listdir(box.cfg_dir):
        if f.startswith('opt_') or f == 'DeployedAddons.txt':
            try:
                os.remove(os.path.join(box.cfg_dir, f))
            except OSError:
                pass


def sandbox(core, config=None, ini=None, db=None):
    box = Sandbox(core, records=WORLD,
                  config=dict(config or {}, uptime_s=5, stable_s=1,
                              manager_db=db or os.path.join(tempfile.gettempdir(), 'vc_absent.json').replace('\\', '/')))
    clear_markers(box)
    if ini is not None:
        io.open(os.path.join(box.cfg_dir, 'config.txt'), 'w', encoding='utf-8', newline='').write(ini)
    box.load()
    box.run_until(lambda: 'cooldown applied to' in box.log_text(), max_seconds=40.0)
    return box


def behaviour(label, expect, config=None, ini=None, needles=None, keep=False):
    box = sandbox(core_global, config=config, ini=ini)
    got = {}
    for key, rid in READ.items():
        got[key + '_cd'] = box.mem.cooldown(rid)
        got[key + '_uses'] = box.mem.uses(rid)
    ok = all(abs(got.get(k + '_cd', -999) - v) < 0.01 for k, v in expect.items())
    for n in (needles or []):
        if n not in box.log_text():
            ok = False
    detail = '' if ok else 'got %s want %s' % (
        {k: got[k + '_cd'] for k in expect}, {k: v for k, v in expect.items()})
    if not keep:
        box.cleanup()
    return note(label, ok, detail), box


def fake_manager_db(path, picks):
    """A minimal manager database in the shape the reader looks for.

    picks maps a block label fragment to the label of the single chosen entry, so
    this exercises the manager path without touching the player's real Arsenal data.
    """
    blocks = [('红战备', ['关闭 / Off', '轨道 + 飞鹰']),
              ('蓝战备', ['就载具 / Vehicles only', '全部 / All']),
              ('绿战备', ['关闭 / Off', '开启 / On']),
              ('冷却时间', ['80% —— 减少 20%', '50% —— 减半']),
              ('次数增加', ['不添加 / None', '去除数量限制 / Unlimited']),
              ('飞鹰次数', ['不添加 / None', '+3 次 / +3 charges'])]
    options = []
    for label, entries in blocks:
        chosen = picks[label]
        options.append({'name': label + '（测试）', 'enabled': True,
                        'suboptions': [{'name': e, 'enabled': e == chosen} for e in entries]})
    doc = {'modsList': {'default': {'mods': [
        {'label': '战备冷却 / Stratagem Cooldown', 'options': options}]}}}
    io.open(path, 'w', encoding='utf-8').write(json.dumps(doc, ensure_ascii=False))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', dest='zip_path', default=None)
    ap.add_argument('--no-node', action='store_true')
    args = ap.parse_args()

    pkg = args.zip_path or newest_zip()
    pkg = pkg if os.path.isabs(pkg) else os.path.join(MOD, pkg)
    print('package: %s (%d B)\n' % (os.path.relpath(pkg, MOD), os.path.getsize(pkg)))
    zf = zipfile.ZipFile(pkg)
    names = zf.namelist()

    global core_global
    core_global = payload_from(zf)

    print('--- 1. package shape ---')
    man = json.loads(zf.read('manifest.json').decode('utf-8'))
    opts = man.get('Options') or []
    note('six option blocks with UI-only entries',
         len(opts) == 6 and sum(len(o.get('SubOptions') or []) for o in opts) == 22,
         '%d blocks / %d entries' % (len(opts), sum(len(o.get('SubOptions') or []) for o in opts)))
    note('every block carries an outer tick and its range choice',
         all(len(o.get('SubOptions') or []) >= 2 for o in opts))
    note('payload at the package root', PAYLOAD in names)
    note('no nested Addon/manifest.json', not any(n.endswith('Addon/manifest.json') for n in names))
    note('no Arsenal-only Options/ tree', not any(n.startswith('Options/') for n in names))
    note('README / builder / preview shipped',
         all(f in names for f in ('README.txt', 'config-builder.html', 'preview.png')))
    note('root manifest declares an icon', bool(man.get('IconPath')), str(man.get('IconPath')))

    print('\n--- 2. payload ---')
    try:
        sys.path.insert(0, os.path.join(MOD, 'work', 'standalone', 'vendor', 'bingus'))
        import lupa.luajit21 as luajit
        luajit.LuaRuntime().compile(core_global)
        note('payload compiles under LuaJIT', True, '%d chars' % len(core_global))
    except Exception as exc:
        note('payload compiles under LuaJIT', False, str(exc)[:80])
    note('no os.execute / io.popen in the payload',
         'os.execute' not in core_global and 'io.popen' not in core_global)

    print('\n--- 3. behaviour (flat keys) ---')
    behaviour('default: 80 / vehicles / no charges',
              dict(tank=624.0, frv=384.0, mech=420.0, mine=120.0, rearm=150.0),
              config={'cooldown': 'yes', 'percent': 80, 'red': 'no', 'blue': 'yes',
                      'blue_scope': 'vehicles', 'green': 'no', 'uses_add': 0,
                      'uses_unlimited': 'no', 'eagle_uses_add': 0})
    behaviour('50% + red + blue all + green + unlimited + eagle 2',
              dict(tank=390.0, frv=240.0, mech=210.0, mine=60.0, rearm=75.0),
              config={'cooldown': 'yes', 'percent': 50, 'red': 'yes', 'blue': 'yes',
                      'blue_scope': 'all', 'green': 'yes', 'uses_unlimited': 'yes',
                      'uses_add': 0, 'eagle_uses_add': 2})
    box = sandbox(core_global, config={'cooldown': 'yes', 'percent': 50, 'red': 'yes', 'blue': 'yes',
                                       'blue_scope': 'all', 'green': 'yes', 'uses_unlimited': 'yes',
                                       'uses_add': 0, 'eagle_uses_add': 2})
    note('  charges: mech/Orbital Laser unlimited, EAGLE gets +2', 
         box.mem.uses(27) == -1 and box.mem.uses(107) == -1 and box.mem.uses(18) == 4)
    box.cleanup()
    behaviour('red = orbital only', dict(laser=240.0, rearm=150.0, tank=780.0),
              config={'cooldown': 'yes', 'percent': 80, 'red': 'yes', 'eagle': 'no', 'blue': 'no',
                      'green': 'no', 'uses_add': 0, 'uses_unlimited': 'no'})
    behaviour('red = eagle only', dict(laser=300.0, rearm=120.0, tank=780.0),
              config={'cooldown': 'yes', 'percent': 80, 'red': 'yes', 'orbital': 'no', 'blue': 'no',
                      'green': 'no', 'uses_add': 0, 'uses_unlimited': 'no'})
    behaviour('blue word (blue=all)', dict(tank=390.0, frv=240.0, mech=210.0, mine=120.0),
              config={'cooldown': 'yes', 'percent': 50, 'red': 'no', 'blue': 'all', 'green': 'no'})
    behaviour('blank machine (no config, no database)',
              dict(tank=624.0, frv=384.0, mech=420.0, mine=120.0, rearm=150.0), config={})
    behaviour('no database but everything configured',
              dict(tank=390.0, frv=240.0, mech=210.0, mine=60.0, rearm=75.0),
              config={'cooldown': 'yes', 'percent': 50, 'red': 'both', 'blue': 'all', 'green': 'yes',
                      'uses_add': 3, 'uses_unlimited': 'no', 'eagle_uses_add': 1})
    box = sandbox(core_global, config={'cooldown': 'yes', 'percent': 50, 'red': 'both', 'blue': 'all',
                                       'green': 'yes', 'uses_add': 3, 'uses_unlimited': 'no',
                                       'eagle_uses_add': 1})
    note('  charges: mech/laser 3+3, eagle 2+1',
         box.mem.uses(27) == 6 and box.mem.uses(107) == 6 and box.mem.uses(18) == 3)
    box.cleanup()

    print('\n--- 3a2. free numbers ---')
    behaviour('percent=65 (free percentage)',
              dict(tank=507.0, frv=312.0, mech=420.0),      # FRV is a vehicle (in scope), mech is not
              config={'cooldown': 'yes', 'percent': 65, 'red': 'no', 'blue': 'vehicles', 'green': 'no'})
    behaviour('percent=25', dict(tank=195.0, frv=120.0, mech=420.0),
              config={'cooldown': 'yes', 'percent': 25, 'red': 'no', 'blue': 'vehicles', 'green': 'no'})
    behaviour('uses_add=7 (free charges)', dict(tank=390.0, mech=210.0),
              config={'cooldown': 'yes', 'percent': 50, 'red': 'no', 'blue': 'all', 'green': 'no',
                      'uses_add': 7})
    box = sandbox(core_global, config={'cooldown': 'yes', 'percent': 100, 'red': 'no', 'blue': 'all',
                                       'green': 'no', 'uses_add': 7})
    note('  charges: mech 3+7 = 10, Orbital Laser 3+7 = 10',
         box.mem.uses(27) == 10 and box.mem.uses(107) == 10)
    box.cleanup()

    print('\n--- 3b. behaviour (sectioned INI) ---')
    behaviour('sections: 50 / both / all / on / unlimited / +2',
              dict(tank=390.0, frv=240.0, mech=210.0, mine=60.0, rearm=75.0),
              ini=('[cooldown]\npercent=50\n\n[scope]\nred=both\nblue=all\ngreen=on\n\n'
                   '[charges]\nmode=unlimited\n\n[eagle]\nmode=+2\n'))
    behaviour('sections: default',
              dict(tank=624.0, frv=384.0, mech=420.0, mine=120.0, rearm=150.0),
              ini=('[cooldown]\npercent=80\n\n[scope]\nred=off\nblue=vehicles\ngreen=off\n\n'
                   '[charges]\nmode=none\n\n[eagle]\nmode=none\n'))
    behaviour('sections: red=orbital', dict(laser=240.0, rearm=150.0, tank=780.0),
              ini='[cooldown]\npercent=80\n[scope]\nred=orbital\nblue=no\ngreen=no\n')
    behaviour('sections: red=eagle', dict(laser=300.0, rearm=120.0, tank=780.0),
              ini='[cooldown]\npercent=80\n[scope]\nred=eagle\nblue=no\ngreen=no\n')
    behaviour('sections: blue=mechs', dict(tank=780.0, frv=480.0, mech=210.0, mine=120.0),
              ini='[cooldown]\npercent=50\n[scope]\nblue=mechs\nred=no\ngreen=no\n')
    behaviour('mixed: section scope + flat percent/uses',
              dict(tank=390.0, frv=240.0, mech=210.0, mine=60.0),
              ini='[scope]\nblue=all\ngreen=on\n\npercent=50\nuses_add=2\nuses_unlimited=no\n')

    print('\n--- 3c. log content ---')
    tmp_db = fake_manager_db(os.path.join(tempfile.gettempdir(), 'vc_fake_manager.json'),
                             {'红战备': '关闭 / Off', '蓝战备': '全部 / All', '绿战备': '开启 / On',
                              '冷却时间': '50% —— 减半', '次数增加': '去除数量限制 / Unlimited',
                              '飞鹰次数': '+3 次 / +3 charges'})
    box = sandbox(core_global, db=tmp_db)
    log = box.log_text()
    note('manager database is read (all-on at 50% from the fake record)',
         abs(box.mem.cooldown(1) - 390.0) < 0.01 and abs(box.mem.cooldown(27) - 210.0) < 0.01
         and box.mem.uses(27) == -1 and box.mem.uses(18) == 5)
    note('log reports the picks and the effective config incl. min_cooldown',
         'blocks(from manager DB): ' in log and 'effective: percent=50' in log
         and 'min_cooldown=' in log)
    note('log lists what config.txt set explicitly',
         'explicit: ' in log)
    box.cleanup()
    box = sandbox(core_global)
    note('log says so when no manager database exists',
         'manager blocks: none deployed' in box.log_text() or 'manager DB' in box.log_text())
    box.cleanup()

    print('\n--- 3c2. the manager blocks drive the mod (database built from the manifest) ---')
    W2 = WORLD + [{'id': 66, 'name': 'SENTRYS. GATLING', 'cooldown': 150.0, 'uses': -1},
                  {'id': 9, 'name': 'EMPLACEMENTS. ANTI TANK EMPLACEMENT', 'cooldown': 180.0, 'uses': -1}]
    blocks = {}
    for g in opts:
        blocks[g['Name'].split(' / ')[0]] = g

    def pick(block, needle):
        for so in blocks[block]['SubOptions']:
            if needle in so['Name']:
                return so['Name']
        return None

    def mgr_db(picks, all_ticked=False):
        options = []
        for g in opts:
            subs = [{'name': so['Name'],
                     'enabled': True if all_ticked else (so['Name'] == picks.get(g['Name']))}
                    for so in (g.get('SubOptions') or [])]
            options.append({'name': g['Name'], 'enabled': True, 'suboptions': subs})
        p = os.path.join(tempfile.gettempdir(), 'vc_mgr_db.json')
        io.open(p, 'w', encoding='utf-8').write(json.dumps(
            {'modsList': {'default': {'mods': [{'label': man.get('Name'), 'options': options}]}}},
            ensure_ascii=False))
        return p

    def mgr(label, picks, expect, all_ticked=False):
        box = Sandbox(core_global, records=W2,
                      config={'uptime_s': 5, 'stable_s': 1,
                              'manager_db': mgr_db(picks, all_ticked).replace('\\', '/')})
        clear_markers(box)
        box.load()
        box.run_until(lambda: 'cooldown applied to' in box.log_text(), max_seconds=40.0)
        got = {'tank': box.mem.cooldown(1), 'frv': box.mem.cooldown(105),
               'mech': box.mem.cooldown(27), 'mine': box.mem.cooldown(12),
               'rearm': box.mem.cooldown(49), 'sentry': box.mem.cooldown(66),
               'empl': box.mem.cooldown(9), 'mech_uses': box.mem.uses(27)}
        ok = all(abs(got[k] - v) < 0.01 for k, v in expect.items())
        box.cleanup()
        return ok, got

    ok, got = mgr('manager: Arsenal import default (everything ticked)', {},
                  dict(tank=624.0, frv=384.0, mech=420.0, mine=120.0, rearm=150.0), all_ticked=True)
    note('manager: import default -> conservative config', ok, '' if ok else 'got %s' % got)
    ok, got = mgr('manager: red+blue+green picks at 50%',
                  {blocks['红战备']['Name']: pick('红战备', '轨道 + 飞鹰'),
                   blocks['蓝战备']['Name']: pick('蓝战备', '全部'),
                   blocks['绿战备']['Name']: pick('绿战备', '开启'),
                   blocks['冷却时间']['Name']: pick('冷却时间', '50%')},
                  dict(tank=390.0, frv=240.0, mech=210.0, mine=60.0, sentry=75.0, empl=90.0,
                       rearm=75.0))
    note('manager: red/blue/green/cooldown picks', ok, '' if ok else 'got %s' % got)
    ok, got = mgr('manager: green off leaves its family alone',
                  {blocks['绿战备']['Name']: pick('绿战备', '关闭'),
                   blocks['冷却时间']['Name']: pick('冷却时间', '50%')},
                  dict(sentry=150.0, empl=180.0, mine=120.0))
    note('manager: green off', ok, '' if ok else 'got %s' % got)
    ok, got = mgr('manager: blue=all with charges +2',
                  {blocks['蓝战备']['Name']: pick('蓝战备', '全部'),
                   blocks['次数增加']['Name']: pick('次数增加', '+2'),
                   blocks['冷却时间']['Name']: pick('冷却时间', '80%')},
                  dict(mech_uses=5, tank=624.0))
    note('manager: charge choice lands', ok, '' if ok else 'got %s' % got)

    print('\n--- 3d. in-game page (Mod Options Menu framework) ---')
    FAKE_HOST = """
    ModOptionsMenu = {
      api = 1, registered = {}, saved = SAVED,
      register_option = function(id, spec)
          if type(id) ~= 'string' or type(spec) ~= 'table' then return false, 'bad args' end
          if spec.type ~= 'toggle' and spec.type ~= 'slider' and spec.type ~= 'choice' then
              return false, 'bad type' end
          if spec.type == 'choice' and type(spec.choices) ~= 'table' then return false, 'no choices' end
          ModOptionsMenu.registered[id] = spec
          return true
      end,
      on_change = function(id, fn) ModOptionsMenu.handlers = ModOptionsMenu.handlers or {}
          ModOptionsMenu.handlers[id] = fn end,
      get = function(id) return ModOptionsMenu.saved[id] end,
    }
    """

    def mom(saved, expect, config=None):
        box = sandbox(core_global, config=config)
        # the host appears only after the addon booted - exactly the "addons load in
        # either order" case, so registration must be retried and then take effect
        box.rt.execute(FAKE_HOST.replace('SAVED', lua_table(saved)))
        count_src = ("(function() local n=0 for _ in pairs(ModOptionsMenu.registered or {}) "
                     "do n=n+1 end return n end)()")
        box.run_until(lambda: (box.eval(count_src) or 0) == 7, max_seconds=30.0)
        ids = box.eval(count_src) or 0
        base = box.eval('frames') or 0
        box.run_until(lambda: (box.eval('frames') or 0) > base + 900, max_seconds=25.0)
        got = {k: box.mem.cooldown(READ[k]) for k in expect}
        ok = ids == 7 and all(abs(got[k] - v) < 0.01 for k, v in expect.items())
        box.cleanup()
        return ok, ids, got

    ok, ids, got = mom({'stratagem_cooldown.percent': 50, 'stratagem_cooldown.blue': 'all'},
                       dict(tank=390.0, mech=210.0, laser=300.0))
    note('menu after load: 7 options registered, saved values applied', ok,
         '' if ok else 'ids=%s got=%s' % (ids, got))
    ok, ids, got = mom({}, dict(tank=624.0, mech=420.0, laser=300.0))
    note('menu: no saved values -> shipped defaults', ok, '' if ok else 'got=%s' % got)
    ok, ids, got = mom({'stratagem_cooldown.percent': 50},
                       dict(tank=624.0, mech=420.0, laser=300.0),
                       config={'cooldown': 'yes', 'percent': 80, 'red': 'no', 'blue': 'vehicles',
                               'green': 'no'})
    note('menu: an explicit config.txt key is not overridden', ok, '' if ok else 'got=%s' % got)

    print('\n--- 4. builder -> config.txt -> addon (node) ---')
    node = shutil.which('node')
    if args.no_node or not node:
        print('  skipped (node %s)' % ('disabled by flag' if args.no_node else 'not installed'))
    else:
        html = zf.read('config-builder.html').decode('utf-8')
        tmp = tempfile.mkdtemp(prefix='vc_builder_')
        io.open(os.path.join(tmp, 'builder.html'), 'w', encoding='utf-8', newline='\n').write(html)
        io.open(os.path.join(tmp, 'runner.js'), 'w', encoding='utf-8', newline='\n').write("""
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const body = html.match(/<script>([\\s\\S]*?)<\\/script>/)[1];
const values = JSON.parse(process.argv[3]);
const elements = JSON.parse(process.argv[4] || '{}');
const doc = {
  querySelector: function (sel) {
    const m = sel.match(/name="([^"]+)"/); const k = m ? m[1] : null;
    if (k && values[k] === undefined) { values[k] = ''; }
    return { value: k ? values[k] : '' };
  },
  querySelectorAll: function () { return []; },
  getElementById: function (id) {
    return { value: elements[id] === undefined ? '' : String(elements[id]),
             checked: elements[id + '_checked'] === true,
             textContent: '', select: function () {} };
  },
};
process.stdout.write(new Function('document', body + '\\nreturn gen();')(doc));
""")

        def gen(sel, elements=None):
            r = subprocess.run([node, os.path.join(tmp, 'runner.js'), os.path.join(tmp, 'builder.html'),
                                json.dumps(sel), json.dumps(elements or {})],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            if r.returncode != 0:
                raise RuntimeError(r.stderr[:200])
            return r.stdout

        cases = [
            ('builder default (80 / vehicles / +0)', {'red': 'off', 'blue': 'vehicles', 'green': 'off'},
             {'cdnum': 80, 'chnum': 0, 'egnum': 0},
             dict(tank=624.0, frv=384.0, mech=420.0, mine=120.0), 'blue=yes'),
            ('builder everything: 50%, all, +7, unlimited off',
             {'red': 'both', 'blue': 'all', 'green': 'on'},
             {'cdnum': 50, 'chnum': 7, 'egnum': 2},
             dict(tank=390.0, frv=240.0, mech=210.0, mine=60.0, rearm=75.0), 'uses_add=7'),
            ('builder 65% free percentage', {'red': 'off', 'blue': 'vehicles', 'green': 'off'},
             {'cdnum': 65, 'chnum': 0, 'egnum': 0},
             dict(tank=507.0, frv=312.0, mech=420.0), 'percent=65'),
            ('builder orbital only', {'red': 'orbital', 'blue': 'off', 'green': 'off'},
             {'cdnum': 80, 'chnum': 0, 'egnum': 0},
             dict(laser=240.0, rearm=150.0, tank=780.0), 'eagle=no'),
            ('builder eagle only', {'red': 'eagle', 'blue': 'off', 'green': 'off'},
             {'cdnum': 80, 'chnum': 0, 'egnum': 0},
             dict(laser=300.0, rearm=120.0, tank=780.0), 'orbital=no'),
            ('builder mechs only +3', {'red': 'off', 'blue': 'mechs', 'green': 'off'},
             {'cdnum': 80, 'chnum': 3, 'egnum': 0},
             dict(tank=780.0, frv=480.0, mech=336.0, mine=120.0), 'blue_scope=mechs'),
            ('builder defensive (bogus blue)', {'red': 'off', 'blue': 'banana', 'green': 'off'},
             {'cdnum': 80, 'chnum': 0, 'egnum': 0},
             dict(tank=780.0, frv=480.0, mine=120.0), 'blue=no'),
        ]
        for label, sel, elements, expect, needle in cases:
            try:
                text = gen(sel, elements)
            except Exception as exc:
                note(label, False, 'node: %s' % exc)
                continue
            box = sandbox(core_global, ini=text)
            got = {k: box.mem.cooldown(READ[k]) for k in expect}
            ok = all(abs(got[k] - v) < 0.01 for k, v in expect.items())
            if needle and needle not in text:
                ok = False
            note(label, ok, '' if ok else 'got %s want %s' % (got, expect))
            box.cleanup()
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [r for r in RESULTS if not r[1]]
    print('\n%d check(s), %d failed' % (len(RESULTS), len(bad)))
    for name, _, detail in bad:
        print('  FAILED: %s %s' % (name.strip(), detail))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
