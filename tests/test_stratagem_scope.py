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
                      config={'percent': 50, 'red': 'yes', 'blue': 'no', 'green': 'no',
                              'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(18), 15.0, places=3)  # eagle drop delay kept
            self.assertAlmostEqual(box.mem.cooldown(49), 75.0, places=3)  # rearm = the real cycle
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
                      config={'percent': 50, 'red': 'yes', 'orbital': 'no', 'eagle': 'yes',
                              'blue': 'no', 'green': 'no', 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(107), 300.0, places=3)   # orbital off
            self.assertAlmostEqual(box.mem.cooldown(49), 75.0, places=3)      # eagle on -> rearm
        finally:
            box.cleanup()

    def test_green_only_touches_sentries_and_emplacements(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'percent': 50, 'red': 'no', 'blue': 'no', 'green': 'yes',
                              'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(66), 75.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(9), 90.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(69), 45.0, places=3)  # 45s < min_cooldown, kept
            self.assertAlmostEqual(box.mem.cooldown(1), 780.0, places=3)
        finally:
            box.cleanup()

    def test_missions_are_off_by_default_and_can_be_enabled(self):
        box = Sandbox(SRC, records=WORLD, config={'percent': 50, 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(7), 180.0, places=3)
        finally:
            box.cleanup()
        box = Sandbox(SRC, records=WORLD,
                      config={'percent': 50, 'missions': 'yes', 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(7), 90.0, places=3)
        finally:
            box.cleanup()


class TestBlueScope(unittest.TestCase):
    def helper(self, scope, expect):
        box = Sandbox(SRC, records=WORLD,
                      config={'percent': 50, 'red': 'no', 'green': 'no', 'blue': 'yes',
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


class TestCooldownPresets(unittest.TestCase):
    """1.9.1: the reduction choice is one of three presets."""

    def test_100_leaves_every_cooldown_alone(self):
        box = Sandbox(SRC, records=WORLD, config={'percent': 50, 'percent': 100, 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            for rid, want in ((1, 780.0), (18, 15.0), (107, 300.0), (49, 150.0)):
                self.assertAlmostEqual(box.mem.cooldown(rid), want, places=3)
        finally:
            box.cleanup()

    def test_80_takes_a_fifth_off(self):
        box = Sandbox(SRC, records=WORLD, config={'percent': 80, 'red': 'yes', 'blue': 'all', 'green': 'yes',
                              'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(1), 624.0, places=3)     # 780 * 0.8
            self.assertAlmostEqual(box.mem.cooldown(107), 240.0, places=3)   # 300 * 0.8
            self.assertAlmostEqual(box.mem.cooldown(49), 120.0, places=3)    # 150 * 0.8
        finally:
            box.cleanup()

    def test_50_halves(self):
        box = Sandbox(SRC, records=WORLD, config={'percent': 50, 'percent': 50, 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(1), 390.0, places=3)
            self.assertAlmostEqual(box.mem.cooldown(18), 15.0, places=3)   # timing field kept
        finally:
            box.cleanup()

    def test_a_free_percentage_is_used_as_it_is(self):
        # 2.5.3 removed the 100/80/50 snapping: the player picks any percentage
        box = Sandbox(SRC, records=WORLD, config={'percent': 50, 'percent': 60, 'uptime_s': 5,
                                                  'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(1), 468.0, places=3)     # 780 * 0.60
        finally:
            box.cleanup()

    def test_an_out_of_range_percentage_is_clamped(self):
        box = Sandbox(SRC, records=WORLD, config={'percent': 50, 'percent': 0, 'uptime_s': 5,
                                                  'stable_s': 1})
        try:
            run(box)
            self.assertTrue(box.find('clamped to 1'))
            self.assertAlmostEqual(box.mem.cooldown(1), 7.8, places=3)       # 780 * 0.01
        finally:
            box.cleanup()


class TestCharges(unittest.TestCase):
    """1.9.1: +1/+2/+3 charges, or remove the limit entirely."""

    def test_uses_add_raises_finite_counts_only(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'percent': 50, 'uses_add': 2, 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertEqual(box.mem.uses(18), 4)     # eagle airstrike 2 -> 4
            self.assertEqual(box.mem.uses(107), 5)    # orbital laser 3 -> 5
            self.assertEqual(box.mem.uses(27), 5)     # mech 3 -> 5
            self.assertEqual(box.mem.uses(69), 3)     # reward sentry 1 -> 3
            self.assertEqual(box.mem.uses(1), -1)     # tank unlimited stays -1
            self.assertEqual(box.mem.uses(49), -1)    # rearm unlimited stays -1
        finally:
            box.cleanup()

    def test_uses_add_one_and_three(self):
        for add, offset in ((1, 1), (3, 3)):
            box = Sandbox(SRC, records=WORLD,
                          config={'percent': 50, 'uses_add': add, 'uptime_s': 5, 'stable_s': 1})
            try:
                run(box)
                self.assertEqual(box.mem.uses(18), 2 + offset)
                self.assertEqual(box.mem.uses(107), 3 + offset)
            finally:
                box.cleanup()

    def test_uses_unlimited_removes_the_limit(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'percent': 50, 'uses_unlimited': 'yes', 'red': 'yes', 'blue': 'all',
                              'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertEqual(box.mem.uses(18), 2)     # EAGLE keeps its count: -1 means 'spent'
            self.assertEqual(box.mem.uses(107), -1)   # orbital laser 3 -> unlimited
            self.assertEqual(box.mem.uses(27), -1)    # mech 3 -> unlimited
            self.assertEqual(box.mem.uses(1), -1)     # already unlimited
        finally:
            box.cleanup()

    def test_charges_are_rolled_back_when_a_write_fails(self):
        box = Sandbox(SRC, records=WORLD, fail_writes=True,
                      config={'percent': 50, 'uses_add': 2, 'uptime_s': 5, 'stable_s': 1})
        try:
            box.load()
            self.assertTrue(box.run_until(lambda: 'ABORTED' in box.log_text(), max_seconds=60.0))
            self.assertEqual(box.mem.uses(18), 2)
            self.assertEqual(box.mem.cooldown(18), 15.0)
        finally:
            box.cleanup()


class TestMinCooldownThreshold(unittest.TestCase):
    """1.9.2: +0x68 is only a cooldown when it is cooldown-sized."""

    def test_small_values_are_left_alone_and_reported(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'percent': 50, 'red': 'yes', 'blue': 'all', 'green': 'yes',
                              'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(18), 15.0, places=3)   # eagle drop delay
            self.assertTrue(box.find('min_cooldown'))
        finally:
            box.cleanup()

    def test_min_cooldown_one_rescales_everything(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'percent': 50, 'min_cooldown': 1, 'red': 'yes', 'blue': 'all',
                              'green': 'yes', 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(18), 7.5, places=3)
            self.assertAlmostEqual(box.mem.cooldown(69), 22.5, places=3)
            self.assertAlmostEqual(box.mem.cooldown(49), 75.0, places=3)
        finally:
            box.cleanup()

    def test_charges_are_still_handled_for_timing_only_records(self):
        box = Sandbox(SRC, records=WORLD,
                      config={'percent': 50, 'uses_add': 2, 'uptime_s': 5, 'stable_s': 1})
        try:
            run(box)
            self.assertAlmostEqual(box.mem.cooldown(18), 15.0, places=3)   # delay kept
            self.assertEqual(box.mem.uses(18), 4)                         # charges still +2
        finally:
            box.cleanup()

if __name__ == '__main__':
    unittest.main(verbosity=2)
