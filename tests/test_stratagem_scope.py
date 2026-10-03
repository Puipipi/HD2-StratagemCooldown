# -*- coding: utf-8 -*-
"""1.9.0 tests: colour scope, blue sub-choice, charges, Eagle/rearm."""
import io
import os
import unittest

from vc_sandbox import Sandbox, VANILLA

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = io.open(os.path.join(HERE, '..', 'src', 'vehicle_cooldown.lua'), encoding='utf-8').read()

# names and values taken from the live game table (2026-10-03)
WORLD = [
    {'id': 1, 'name': 'VEHICLES. BASTION(TANK)', 'cooldown': 780.0, 'uses': -1},
    {'id': 27, 'name': 'VEHICLES. COMBAT WALKER', 'cooldown': 420.0, 'uses': 3},
    {'id': 105, 'name': 'VEHICLES. FAST RECON VEHICLE (FRV)', 'cooldown': 480.0, 'uses': -1},
    {'id': 49, 'name': 'EAGLE. REARM', 'cooldown': 150.0, 'uses': -1},
    {'id': 18, 'name': 'EAGLE. AIRSTRIKE', 'cooldown': 15.0, 'uses': 2},
    {'id': 107, 'name': 'ORBITAL. LASER', 'cooldown': 300.0, 'uses': 3},
    {'id': 58, 'name': 'ORBITAL. RAILCANNON', 'cooldown': 180.0, 'uses': -1},
    {'id': 56, 'name': 'TEAM WEAPONS. RAILGUN', 'cooldown': 480.0, 'uses': -1},
    {'id': 73, 'name': 'BACKPACK. GUARD DOG (DRONE)', 'cooldown': 480.0, 'uses': -1},
    {'id': 33, 'name': 'CONSUMABLES. RESUPPLY', 'cooldown': 180.0, 'uses': -1},
    {'id': 66, 'name': 'SENTRYS. GATLING', 'cooldown': 150.0, 'uses': -1},
    {'id': 9, 'name': 'EMPLACEMENTS. ANTI TANK EMPLACEMENT', 'cooldown': 180.0, 'uses': -1},
    {'id': 7, 'name': 'MISSIONS. EXTRACTION BEACON', 'cooldown': 180.0, 'uses': -1},
    {'id': 69, 'name': 'PRESIDENT REWARDS. ROCKET SENTRY', 'cooldown': 45.0, 'uses': 1},
]


def applied(box):
    return 'cooldown applied to' in box.log_text()


def run(box, seconds=40.0):
    box.load()
    box.run_until(lambda: applied(box), max_seconds=seconds)
    return box


class TestColourScope(unittest.TestCase):
    def test_red_only_touches_orbital_and_eagle(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'red': 'yes', 'blue': 'no', 'green': 'no',
                              'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(18), 7.5, places=3)    # eagle
            self.assertAlmostEqual(box.mem.cooldown(49), 75.0, places=3)   # rearm (real cycle)
            self.assertAlmostEqual(box.mem.cooldown(107), 150.0, places=3)  # orbital
            self.assertAlmostEqual(box.mem.cooldown(58), 90.0, places=3)
            for rid in (1, 27, 105, 56, 73, 33, 66, 9, 69):
                self.assertAlmostEqual(box.mem.cooldown(rid),
                                       [r for r in WORLD if r['id'] == rid][0]['cooldown'],
                                       places=3, msg='id %d must stay untouched' % rid)
        finally:
            box.cleanup()

    def test_orbital_and_eagle_can_be_switched_individually(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'red': 'yes', 'orbital': 'no', 'eagle': 'yes',
                              'blue': 'no', 'green': 'no', 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(107), 300.0, places=3)   # orbital off
            self.assertAlmostEqual(box.mem.cooldown(18), 7.5, places=3)      # eagle on
        finally:
            box.cleanup()

    def test_green_only_touches_sentries_and_emplacements(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'red': 'no', 'blue': 'no', 'green': 'yes',
                              'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(66), 75.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(9), 90.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(69), 22.5, places=3)  # reward sentry 45 -> 22.5
            self.assertAlmostEqual(box.mem.cooldown(1), 780.0, places=3)
        finally:
            box.cleanup()

    def test_missions_are_off_by_default_and_can_be_enabled(self):
        box = Sandbox(SRC, records=WORLD, config={'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(7), 180.0, places=3)
        finally:
            box.cleanup()
        box = Sandbox(SRC, records=WORLD,
                      config={'missions': 'yes', 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(7), 90.0, places=3)
        finally:
            box.cleanup()


class TestBlueScope(unittest.TestCase):
    def helper(self, scope, expect):
        box = Sandbox(SRC, records=WORLD,
                      config={'red': 'no', 'green': 'no', 'blue': 'yes',
                              'blue_scope': scope, 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            for rid in (1, 27, 105, 56, 73, 33):
                want = expect.get(rid, [r for r in WORLD if r['id'] == rid][0]['cooldown'])
                self.assertAlmostEqual(box.mem.cooldown(rid), want, places=3,
                                       msg='scope=%s id=%d' % (scope, rid))
        finally:
            box.cleanup()

    def test_vehicles_only(self):
        self.helper('vehicles', {1: 390.0, 105: 240.0})

    def test_mechs_only(self):
        self.helper('mechs', {27: 210.0})

    def test_both(self):
        self.helper('both', {1: 390.0, 105: 240.0, 27: 210.0})

    def test_all_includes_support_weapons_and_backpacks(self):
        self.helper('all', {1: 390.0, 105: 240.0, 27: 210.0, 56: 240.0, 73: 240.0, 33: 90.0})


class TestCharges(unittest.TestCase):
    def test_uses_percent_doubles_finite_counts_and_leaves_unlimited(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'uses_percent': 200, 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertEqual(box.mem.uses(18), 4)     # eagle airstrike 2 -> 4
            self.assertEqual(box.mem.uses(107), 6)    # orbital laser 3 -> 6
            self.assertEqual(box.mem.uses(27), 6)     # mech 3 -> 6
            self.assertEqual(box.mem.uses(1), -1)     # tank unlimited stays -1
            self.assertEqual(box.mem.uses(49), -1)    # rearm unlimited stays -1
        finally:
            box.cleanup()

    def test_uses_fixed_sets_a_count_for_limited_stratagems_only(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'uses_fixed': 5, 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertEqual(box.mem.uses(18), 5)
            self.assertEqual(box.mem.uses(107), 5)
            self.assertEqual(box.mem.uses(69), 5)
            self.assertEqual(box.mem.uses(1), -1)
            self.assertEqual(box.mem.uses(56), -1)
        finally:
            box.cleanup()

    def test_charges_are_rolled_back_when_a_write_fails(self):
        box = Sandbox(SRC, records=WORLD, fail_writes=True,
                      config={'uses_percent': 200, 'uptime_s': 5, 'stable_s': 1})
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: 'ABORTED' in box.log_text(), max_seconds=60.0))
            self.assertEqual(box.mem.uses(18), 2)
            self.assertEqual(box.mem.cooldown(18), 15.0)
        finally:
            box.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
