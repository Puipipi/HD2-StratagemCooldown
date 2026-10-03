# -*- coding: utf-8 -*-
"""Offline checks for HD2 Vehicle Cooldown (src/vehicle_cooldown.lua).

Run from the repository root:

    python -m unittest discover -s tests -v

These checks drive the real source through the sandbox in
``tests/vc_sandbox.py`` (synthetic game.dll image, fake kernel32 and fake ffi
cdata).  They prove the scan logic, the failure containment and the writer
state machine; they do NOT prove an in-game effect, a real memory layout or
performance.
"""
import io
import os
import unittest

import vc_sandbox
from vc_sandbox import Sandbox, VANILLA, POISON, MAX_SANE

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = io.open(os.path.join(HERE, '..', 'src', 'vehicle_cooldown.lua'), encoding='utf-8').read()

CHAIN_RUNTIMES = ('lua51', 'luajit21')


def applied(box):
    """True once a cooldown was applied. Later log lines (heartbeat, probes)
    overwrite M.status, so the log is the reliable witness."""
    if 'applied' in str(box.field('status') or ''):
        return True
    return 'cooldown applied to' in box.log_text()


class TestDormantPaths(unittest.TestCase):
    def test_no_ffi_leaves_the_chain_untouched(self):
        box = Sandbox(SRC, ffi=False)
        try:
            state = box.load()
            self.assertIn('dormant', str(state['status']))
            self.assertEqual(box.eval('update()'), 'chain')
        finally:
            box.cleanup()

    def test_no_bingus_loader_is_dormant(self):
        box = Sandbox(SRC, loader=False)
        try:
            self.assertIn('dormant', str(box.load()['status']))
        finally:
            box.cleanup()

    def test_unresolvable_game_module_stops_loudly(self):
        box = Sandbox(SRC, module=False)
        try:
            self.assertIn('locate failed', str(box.load()['status']))
            self.assertTrue(box.find('STOPPED at load'))
        finally:
            box.cleanup()

    def test_missing_update_chain_is_dormant(self):
        box = Sandbox(SRC, chain=False)
        try:
            status = str(box.load()['status'])
            self.assertIn('global update missing', status)
            self.assertTrue(box.find('global update missing - dormant'))
            self.assertIsNone(box.eval('update'))
        finally:
            box.cleanup()


class TestBackdoorUnits(unittest.TestCase):
    def test_pointer_range_and_name_classifier(self):
        for runtime in CHAIN_RUNTIMES:
            with self.subTest(runtime=runtime):
                box = Sandbox(SRC, runtime=runtime)
                try:
                    box.load_backdoor()
                    t = box.rt.globals()['HD2VehicleCooldownTest']
                    cl = t['classify']
                    self.assertEqual(cl('VEHICLES. BASTION(TANK)'), 'vehicle')
                    self.assertEqual(cl('VEHICLES. COMBAT WALKER'), 'mech')
                    self.assertEqual(cl('EAGLE. REARM'), 'eagle')
                    self.assertEqual(cl('ORBITAL. LASER'), 'orbital')
                    self.assertEqual(cl('TEAM WEAPONS. RAILGUN'), 'support')
                    self.assertEqual(cl('SENTRYS. GATLING'), 'green')
                    self.assertEqual(cl('MISSIONS. EXTRACTION BEACON'), 'mission')
                    self.assertEqual(cl('TANK. TANK RELOAD HE'), 'tank_action')
                    self.assertEqual(cl(None), None)
                    sane = t['sane_ptr']
                    self.assertTrue(sane(0x000001D500000000))
                    self.assertTrue(sane(0x00007FF900000000))
                    self.assertFalse(sane(0))
                    self.assertFalse(sane(0xFFFF))
                    self.assertFalse(box.eval('HD2VehicleCooldownTest.sane_ptr(2^64-1)'))  # -1 filler
                    self.assertFalse(box.eval('HD2VehicleCooldownTest.sane_ptr(2^64)'))
                    self.assertFalse(sane(1.5))
                    self.assertFalse(sane('0x10'))
                    self.assertAlmostEqual(t['f32_from_bits'](t['f32_bits'](390.0)), 390.0, places=3)
                finally:
                    box.cleanup()

    def test_stability_gate_opens_after_the_window(self):
        box = Sandbox(SRC)
        try:
            box.load_backdoor()
            # called exactly like the addon does it: method syntax
            box.rt.execute("""
                T = HD2VehicleCooldownTest
                F = T.make_feature('t')
                F.targets = {}
                r1 = F:snapshot_ok(1000.0, {stable_s=6})
                r2 = F:snapshot_ok(1004.0, {stable_s=6})
                r3 = F:snapshot_ok(1006.5, {stable_s=6})
            """)
            self.assertFalse(box.eval('r1'))
            self.assertFalse(box.eval('r2'))
            self.assertTrue(box.eval('r3'))
        finally:
            box.cleanup()


class TestScanRobustness(unittest.TestCase):
    """1.6.0 regression: one hostile slot must not kill the whole sweep."""

    def test_resolved_table_base_reaches_the_slot_reader(self):
        """Regression for the shadowed local: the base the resolver returns must
        be the value the record reader actually uses (1.5.x kept it in a local
        nobody read, so slot_ptr() saw nil and every scan died instantly)."""
        for runtime in CHAIN_RUNTIMES:
            with self.subTest(runtime=runtime):
                box = Sandbox(SRC, runtime=runtime)
                try:
                    box.load()
                    self.assertEqual(int(box.field('table_base')),
                                     vc_sandbox.IMAGE_BASE + vc_sandbox.TABLE_RVA)
                    self.assertTrue(box.run_until(lambda: applied(box)),
                                    'scan never applied: %s' % box.log_text())
                finally:
                    box.cleanup()

    def test_poison_slot_does_not_abort_the_scan(self):
        for runtime in CHAIN_RUNTIMES:
            with self.subTest(runtime=runtime):
                box = Sandbox(SRC, runtime=runtime)   # slot id=2 carries name ptr -1
                try:
                    box.load()
                    self.assertTrue(box.run_until(lambda: applied(box)),
                                    'scan never applied: %s' % box.log_text())
                    self.assertAlmostEqual(box.mem.cooldown(1), 390.0, places=3)
                    self.assertAlmostEqual(box.mem.cooldown(50), 390.0, places=3)
                    self.assertAlmostEqual(box.mem.cooldown(2), VANILLA, places=3)
                    self.assertAlmostEqual(box.mem.cooldown(3), 180.0, places=3)   # missions off by default
                    self.assertTrue(box.find('vehicle records appeared: 2 target'))
                    self.assertTrue(box.find('cooldown applied to 2 target'))
                    self.assertEqual(int(box.field('errors') or 0), 0)
                finally:
                    box.cleanup()

    def test_no_out_of_range_pointer_ever_reaches_the_ffi(self):
        for runtime in CHAIN_RUNTIMES:
            with self.subTest(runtime=runtime):
                box = Sandbox(SRC, runtime=runtime)
                try:
                    box.load()
                    box.run_until(lambda: applied(box))
                    self.assertTrue(box.mem.casts)
                    bad = [a for a in box.mem.casts
                           if a < 0x10000 or a > MAX_SANE or a != int(a)]
                    self.assertEqual(bad, [], 'unsafe pointer(s) reached the FFI: %r' % bad[:4])
                finally:
                    box.cleanup()

    def test_unexpected_fault_is_contained_and_reported(self):
        records, _ = Sandbox.vehicle_world(poison=False)
        hostile_id = 7
        records.append({'id': hostile_id, 'name': 'EXO-49 PATRIOT', 'cooldown': VANILLA})
        box = Sandbox(SRC, records=records,
                      hostile=vc_sandbox.HEAP_BASE + hostile_id * vc_sandbox.RECORD_STRIDE)
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)),
                            'the sweep did not survive the fault: %s' % box.log_text())
            self.assertGreaterEqual(int(box.field('errors') or 0), 1)
            self.assertIn('hostile address', str(box.field('last_error')))
            self.assertTrue(box.find('error: .*hostile address'))
            self.assertAlmostEqual(box.mem.cooldown(1), 390.0, places=3)
        finally:
            box.cleanup()

    def test_empty_table_then_records_appear(self):
        box = Sandbox(SRC, records=[], table_ids={})
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: 'no vehicle records yet' in box.log_text(),
                                          max_seconds=120.0))
            self.assertEqual(box.eval('HD2VehicleCooldown.cd.state'), 'observe')
            box.mem.inject({'id': 1, 'name': 'VEHICLES. BASTION(TANK)', 'cooldown': VANILLA})
            box.mem.inject({'id': 50, 'name': 'VEHICLES. STORM(TANK)', 'cooldown': VANILLA})
            self.assertTrue(box.run_until(lambda: applied(box)),
                            'records that appeared later were never picked up: %s' % box.log_text())
            self.assertAlmostEqual(box.mem.cooldown(1), 390.0, places=3)
        finally:
            box.cleanup()

    def test_re_resolve_is_bounded(self):
        box = Sandbox(SRC, records=[], table_ids={})
        try:
            box.load()
            box.run_for(800.0, dt=0.2)
            self.assertTrue(box.find('re-resolved table base'))
            self.assertLessEqual(int(box.field('relocates') or 0), 5)
        finally:
            box.cleanup()


class TestPercentageMode(unittest.TestCase):
    """1.7.2: every stratagem is scaled from its OWN vanilla cooldown."""

    def test_each_vehicle_is_halved_from_its_own_value(self):
        records = [
            {'id': 1, 'name': 'VEHICLES. BASTION(TANK)', 'cooldown': 780.0},
            {'id': 105, 'name': 'VEHICLES. FAST RECON VEHICLE (FRV)', 'cooldown': 480.0},
            {'id': 27, 'name': 'VEHICLES. COMBAT WALKER', 'cooldown': 420.0},          # mech (in blue scope)
            {'id': 50, 'name': 'VEHICLES. STORM(TANK)', 'cooldown': 780.0},
            {'id': 3, 'name': 'MISSIONS. EXTRACTION BEACON', 'cooldown': 180.0},
        ]
        box = Sandbox(SRC, records=records, config={'percent': 50})
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)), box.log_text())
            self.assertAlmostEqual(box.mem.cooldown(1), 390.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(105), 240.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(27), 210.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(50), 390.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(3), 180.0, places=3)   # missions off by default   # non-vehicle untouched
            self.assertTrue(box.find('780->390'))
            self.assertTrue(box.find('480->240'))
            self.assertTrue(box.find('420->210'))
        finally:
            box.cleanup()

    def test_percentage_is_taken_from_the_vanilla_value_not_the_patched_one(self):
        """A re-scan must not halve our own target again (780 -> 390 -> 195)."""
        box = Sandbox(SRC)
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)))
            self.assertAlmostEqual(box.mem.cooldown(1), 390.0, places=3)
            box.rt.execute('HD2VehicleCooldown.cd.next_scan = 0')      # force a re-scan
            box.rt.execute('HD2VehicleCooldown.cd.targets = nil')
            box.run_for(15.0)
            self.assertAlmostEqual(box.mem.cooldown(1), 390.0, places=3)
            self.assertFalse(box.find('195'))
        finally:
            box.cleanup()

    def test_percent_zero_falls_back_to_the_fixed_target(self):
        box = Sandbox(SRC, config={'percent': 0, 'cooldown_s': 300, 'uptime_s': 5, 'stable_s': 1})
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)), box.log_text())
            self.assertAlmostEqual(box.mem.cooldown(1), 300.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(50), 300.0, places=3)
        finally:
            box.cleanup()


class TestOverhead(unittest.TestCase):
    """1.7.3: keep the measured per-session cost tiny and bounded."""

    def test_sweep_is_bounded_and_documented(self):
        box = Sandbox(SRC)
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)), box.log_text())
            self.assertLessEqual(int(box.field('scan_ids') or 0), 255)
            self.assertLessEqual(int(box.field('slots') or 0), 256)
        finally:
            box.cleanup()

    def test_copy_probe_is_off_by_default(self):
        box = Sandbox(SRC)
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)), box.log_text())
            self.run_probe_off = True
            self.assertFalse(box.find('copy probe'))
        finally:
            box.cleanup()

    def test_copy_probe_still_available_on_request(self):
        box = Sandbox(SRC, config={'probe': 'yes', 'uptime_s': 5, 'stable_s': 1})
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)), box.log_text())
            box.run_for(5.0)
            self.assertTrue(box.find('copy probe'), box.log_text()[-500:])
        finally:
            box.cleanup()


class TestWriterStateMachine(unittest.TestCase):
    def test_watch_reapplies_after_an_engine_reset(self):
        box = Sandbox(SRC)
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)))
            box.mem.set_cooldown(1, VANILLA)          # engine resets the field
            box.run_for(20.0)
            self.assertAlmostEqual(box.mem.cooldown(1), 390.0, places=3)
            self.assertTrue(box.find('cooldown re-applied to record 1'))
        finally:
            box.cleanup()

    def test_failed_write_rolls_back_and_disables(self):
        box = Sandbox(SRC, fail_writes=True)
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: 'ABORTED' in box.log_text(), max_seconds=200.0))
            self.assertEqual(str(box.field('state')), 'disabled')
            self.assertAlmostEqual(box.mem.cooldown(1), VANILLA, places=3)
            self.assertAlmostEqual(box.mem.cooldown(50), VANILLA, places=3)
        finally:
            box.cleanup()

    def test_heartbeat_and_effective_config_are_published(self):
        box = Sandbox(SRC, config={'uptime_s': 10, 'stable_s': 2})
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)))
            box.run_for(70.0)
            self.assertTrue(box.find('heartbeat: state=watch'))
            self.assertIn('uptime gate passed', box.log_text())
            self.assertAlmostEqual(float(box.field('uptime_s')), 10.0, places=3)
            self.assertAlmostEqual(float(box.field('stable_s')), 2.0, places=3)
        finally:
            box.cleanup()

    def test_out_of_range_fixed_target_is_clamped_and_logged(self):
        # fixed mode (percent=0) with a nonsense target: must clamp, not write 0
        box = Sandbox(SRC, config={'uptime_s': 10, 'stable_s': 2, 'percent': 0, 'cooldown_s': 0})
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: applied(box)), box.log_text())
            self.assertAlmostEqual(box.mem.cooldown(1), 1.0, places=3)   # clamped to 1s floor
        finally:
            box.cleanup()

    def test_missing_config_file_is_created_with_defaults(self):
        box = Sandbox(SRC, config=False)
        try:
            box.load()
            cfg = os.path.join(box.cfg_dir, 'config.txt')
            self.assertTrue(os.path.exists(cfg))
            with io.open(cfg, encoding='utf-8') as fh:
                text = fh.read()
            self.assertIn('uptime_s=0', text)
            self.assertIn('cooldown=yes', text)
        finally:
            box.cleanup()

    def test_chain_passthrough_keeps_every_return_value(self):
        box = Sandbox(SRC)
        try:
            box.rt.execute("update = function() return 'a', nil, 'c' end")
            box.load()
            self.assertEqual(box.eval("select('#', update())"), 3)
            self.assertEqual(box.eval('(select(3, update()))'), 'c')
        finally:
            box.cleanup()


class TestArchivedDeployedBuild(unittest.TestCase):
    """Executable reproduction of the in-game evidence.

    ``research/evidence/vehicle-cooldown-1.5.1-deployed.lua`` is the byte-exact
    text of the addon deployed in the game layers (9ba626afa44a3aa3.patch_293,
    sha256 1c27dcaf609c1cd8523f4768279d2ba8950a0399f49dbefc3c57536c5a9ece0c).
    In 99 gated game sessions it logged exactly one line after the uptime gate
    and never applied anything.  The sandbox shows the exception that caused
    that silence.
    """

    DEPLOYED = io.open(os.path.join(HERE, '..', 'research', 'evidence',
                                    'vehicle-cooldown-1.5.1-deployed.lua'),
                       encoding='utf-8').read()
    SHADOWING = 'local table_base,locate_err=locate_table()'
    SHADOWING_FIX = ('local tb_at_load,le_at_load=locate_table()\n'
                     'table_base=tb_at_load locate_err=le_at_load')

    def test_deployed_1_5_1_stays_silent_and_the_error_is_the_nil_table_base(self):
        box = Sandbox(self.DEPLOYED, capture_pcall=True)
        try:
            box.load()
            box.run_for(200.0)
            stages = [ln.split(' ', 1)[1] for ln in box.log_lines()]
            self.assertTrue(any('uptime gate passed' in s for s in stages), stages)
            for stage in ('vehicle records appeared', 'no vehicle records yet',
                          'cooldown applied'):
                self.assertFalse([s for s in stages if stage in s], stages)
            self.assertAlmostEqual(box.mem.cooldown(1), VANILLA, places=3)
            self.assertAlmostEqual(box.mem.cooldown(50), VANILLA, places=3)
            # the phase never moves past the uptime gate - the exact field value
            # that gave the failure away in the game's runtime snapshots
            self.assertTrue(str(box.field('phase')).startswith('uptime'))
            # and here is the exception the game never showed
            errors = box.pcall_log_unique()
            self.assertTrue(errors, 'no swallowed error captured')
            self.assertIn('table_base', errors[0])
            self.assertIn('nil', errors[0])
        finally:
            box.cleanup()

    def test_shadowing_fix_alone_still_never_writes(self):
        """With only defect (1) repaired, defect (2) stops the addon anyway:
        ``snapshot_ok`` was declared ``function(now,cfg)`` but called as
        ``cd:snapshot_ok(now,cfg)``, so the feature table lands in ``now``."""
        self.assertIn(self.SHADOWING, self.DEPLOYED, 'fixture line moved')
        patched = self.DEPLOYED.replace(self.SHADOWING, self.SHADOWING_FIX, 1)
        records, _ = Sandbox.vehicle_world(poison=False)
        box = Sandbox(patched, records=records, capture_pcall=True)
        try:
            box.load()
            box.run_for(200.0)
            stages = [ln.split(' ', 1)[1] for ln in box.log_lines()]
            self.assertTrue([s for s in stages if 'vehicle records appeared' in s], stages)
            self.assertFalse([s for s in stages if 'cooldown applied' in s], stages)
            self.assertAlmostEqual(box.mem.cooldown(1), VANILLA, places=3)
            errors = box.pcall_log_unique()
            self.assertTrue(any("'now'" in e for e in errors), errors)
        finally:
            box.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
