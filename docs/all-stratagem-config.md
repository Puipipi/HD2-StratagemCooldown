# HD2 Stratagem Cooldown 1.9.1 - config surface and the live field findings

Date: 2026-10-03. Everything below was read out of the **running** game
(read-only) and then reproduced in the offline sandbox.

## Config (one file, all switches)

`%LOCALAPPDATA%\CowboyBingus\Helldivers2\VehicleCooldown\config.txt`
(the directory keeps the addon's original name so the manager entry upgrades in
place):

| Key | Default | Meaning |
| --- | --- | --- |
| `percent` | 50 | cooldown preset: **100 = unchanged, 80 = 20% shorter, 50 = half**; any other value snaps to the nearest preset and is logged |
| `uses_add` | 0 | charges: 0 = unchanged, **1 / 2 / 3 = that many more** on every limited stratagem |
| `uses_unlimited` | no | **yes = remove the charge limit** (finite -> `-1` = unlimited) |
| `red` | yes | red stratagems (offensive) |
| `orbital` | yes | `ORBITAL.*` |
| `eagle` | yes | `EAGLE.*`, including `EAGLE. REARM` |
| `blue` | yes | blue stratagems (support equipment + the vehicle/mech choice) |
| `blue_scope` | all | mutually exclusive: `vehicles` 就载具 / `mechs` 就机甲 / `both` 就载具和机甲 / `all` 全部 |
| `green` | yes | `SENTRYS.*`, `SENTRIES.*`, `EMPLACEMENTS.*` |
| `missions` | no | mission stratagems (reinforce / extraction / resupply / SEAF / clan station) |
| `stable_s` | 1 | pointer-stability window before writing |
| `uptime_s` | 0 | write as soon as the records are valid (0 = at load - the timing that matters) |
| `probe` | no | opt-in diagnostic memory search (~0.45 s one-shot) |

## Category mapping (from the live table's name prefixes)

| Category | Prefixes | Count in the live table |
| --- | --- | --- |
| orbital (red) | `ORBITAL.` | 13 |
| eagle (red) | `EAGLE.` | 11 |
| support (blue) | `TEAM WEAPONS.`, `BACKPACK.`, `CONSUMABLES.` | 34 + 14 + 2 |
| vehicles (blue) | `VEHICLES.` without `COMBAT WALKER` (tanks, FRV, incl. FRV variants) | 5 |
| mechs (blue) | `VEHICLES. COMBAT WALKER*` | 4 |
| green | `SENTRYS.`, `SENTRIES.`, `EMPLACEMENTS.` | 8 + 1 + 9 |
| mission | `MISSIONS.`, `MISSIONS CLAN STATION.` | 33 + 2 |
| reward variants | `PRESIDENT REWARDS.*` mapped by keyword (MACHINEGUN/BACKPACK -> blue, SENTRY -> green) | 7 |
| ignored | `TANK.*` (tank reload actions, 6 s) | 3 |

## The charges/uses field: `+0x50` (int32)

`-1` means **unlimited**. `uses_add` raises a finite count by 1..3; `uses_unlimited`
removes the limit entirely. A record that is already unlimited is never touched, and a
limit is never invented where the game has none.

Live values (2026-10-03):

| Stratagem | uses | cooldown |
| --- | --- | --- |
| `EAGLE. 500KG BOMB` / `AIRSTRIKE` / `110MM ROCKET PODS` / `CLUSTERBOMBS` | 1 / 2 / 3 / 4 | 15 s |
| `EAGLE. AIR SUPPORT` | 4 | 15 s |
| `EAGLE. REARM` (返回补给) | -1 | 150 s |
| `ORBITAL. LASER` (激光轨道) | 3 | 300 s |
| `VEHICLES. COMBAT WALKER` + 3 variants (mechs) | 3 | 420 s |
| `VEHICLES. BASTION(TANK)`, `VEHICLES. STORM(TANK)`, FRV | -1 (unlimited) | 780 / 780 / 480 s |
| `PRESIDENT REWARDS. *` | 1 | 45-600 s |
| `MISSIONS. SOS BEACON`, clan nuke | 1 | 180 / 1200 s |

## Why the Eagle series is special

Eagle stratagems do not really run on their own cooldown: each one carries a
small number of charges (1-4) and a 15 s inter-use delay, and when the charges
are spent the player calls **`EAGLE. REARM`** (150 s) to restore **all** Eagle
stratagems at once. So the family's real pacing comes from REARM's cooldown, and
with `percent=50` REARM goes 150 s -> 75 s. Raising `uses_percent` (or
`uses_fixed`) additionally reduces how often a rearm is needed at all.

## Verified offline (37 checks)

`python -m unittest discover -s tests -v` covers, with the real record names and
values from the live table: per-stratagem halving, the red/blue/green switches,
`orbital`/`eagle` individually, all four `blue_scope` choices, the mission
opt-in, charges scaling + fixing + `-1` preservation, rollback of both fields on
a failed write, and the earlier resolver/safety/overhead regressions.

**Not verified in game yet**: the next session's
`Logs\VehicleCooldown.log` must show `v1.9.0 installed` -> `mode=red=yes(...)` ->
`records appeared` -> `patched offsets` -> `cooldown applied`, and the in-game
cooldown values must actually change.
