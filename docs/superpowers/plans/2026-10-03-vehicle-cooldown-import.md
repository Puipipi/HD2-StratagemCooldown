# Import 战备冷却 / Stratagem Cooldown into the mod workspace and fix the silent no-op

Date: 2026-10-03. Status: implemented (source + tests + package); no in-game run
yet.

## Request

把载具冷却模组导入项目并修复：它不生效；必须遵守项目内的 git 规则与位置规则。

## What the workspace already had

* The addon existed only as workspace scratch: `work/standalone/vehicle_cooldown.lua`
  (v1.0), `work/standalone/vehicle_overhaul.lua`, `work/standalone/test_vc.py`,
  a built package in `outputs/archive/other/vehiclecooldown/`, and the deployed
  text inside the game layer `9ba626afa44a3aa3.patch_293` (v1.1).
* Project layout rules (from `README.md` and the existing mod repositories):
  each mod lives under `mods/<name>/` with its **own** `.git`, README, dev
  requirements, third-party notices, `work/standalone/` build script, `dist/`
  packages and `docs/`; the root repository ignores `mods/` entirely; commits go
  to the mod repository; no automatic copy or deployment between the two;
  third-party references stay read-only; public snapshots exclude personal
  configuration, runtime logs and crash dumps.
* Branch convention in the existing mod repositories: work happens on a
  `codex/<topic>` branch (`codex/melee-vehicle-rescue`, `codex/smooth-runtime-repair`).

## Plan

1. Locate the exact deployed build and fingerprint it (layer, Arsenal library,
   package GUID) so the fix targets real code, not a workspace copy.
2. Establish why it never applied anything, from the game's own logs and
   runtime snapshots - not from the previous session's hypothesis.
3. Import the current source into `mods/stratagem-cooldown/` following the layout
   rules, with its own repository and branch.
4. Fix the root cause(s); keep the reviewed stability/rollback design intact.
5. Build an offline sandbox that runs the real source against a synthetic
   game.dll image + fake kernel32/ffi, and turn the diagnosis into tests -
   including a test that loads the byte-exact deployed text and reproduces the
   silent failure.
6. Add the log-analysis tool, root-cause documentation and evidence summary;
   build the installable envelope ZIP with the official packer (same GUID, so
   Arsenal treats it as an update).
7. Commit in the mod repository on `codex/vehicle-cooldown`; update the
   workspace README row. Never write to the game directory or the Arsenal
   library (the 2026-10-01 black screen came from hand-writing layers).

## Outcome

See [docs/root-cause-2026-10-03-vehicle-cooldown-silent-no-op.md](../../root-cause-2026-10-03-vehicle-cooldown-silent-no-op.md)
for the three defects and their fixes, and
[research/evidence/silent-no-op-evidence-2026-10-03.md](../../../research/evidence/silent-no-op-evidence-2026-10-03.md)
for the evidence and the reproduction. 20 offline checks pass; the in-game
verification of 1.6.0 is still outstanding and is the next step.
