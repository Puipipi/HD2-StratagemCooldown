# Root cause: 战备冷却 / Stratagem Cooldown never took effect / 载具冷却模组不生效的根因

Date: 2026-10-03. Scope: the 1.5.1-fixed build (internal v1.1) that was deployed
in the game layers, the fix shipped as 1.6.0, and the evidence behind both.
Raw player logs stay in the workspace; the derived numbers live in
[research/evidence](../../research/evidence/silent-no-op-evidence-2026-10-03.md).

## Summary / 结论

The addon loaded, resolved the stratagem table and passed its uptime gate in
every session, then died silently inside the first scan. Three defects, all
hidden by `pcall(tick_cooldown)`:

1. **The resolved table base was stored in a shadowing local** (v1.0 and v1.1
   alike). `local table_base,locate_err=locate_table()` declares a *second*
   local and leaves the `table_base` upvalue captured by `slot_ptr()` /
   `rec_info()` at `nil`, so the first slot read raised
   `attempt to perform arithmetic on upvalue 'table_base' (a nil value)`.
   This is the observed killer: 99 gated sessions, zero scan results, `phase`
   frozen at `uptime 119s`.
2. **The stability gate had the wrong self signature**: `F.snapshot_ok` was
   declared `function(now,cfg)` but called as `cd:snapshot_ok(now,cfg)`, so the
   feature table arrived in `now` and `now-F.last_sample` raised. Even with (1)
   repaired the addon could not reach a write.
3. **The 146-slot sweep followed unvalidated pointers** (defence-in-depth, not
   the observed crash): every 8-byte slot value was treated as an address and
   every record's name pointer was followed. A `0xFFFFFFFFFFFFFFFF` filler
   becomes a double ≥ 2^64 that `ffi.cast` cannot represent, and one such slot
   aborted the whole sweep.

`pcall(tick_cooldown)` turned each of them into permanent, traceless silence -
which is why 165 sessions of logs contained no symptom at all.

## Why the "empty enumeration" theory was wrong / 为什么旧结论是错的

The 1.5.1 changelog blamed a cached empty target set
(`if not cd.targets then cd.targets=cooldown_targets() end`, where `{}` is
truthy) and re-scanned every 10 s. That bug is real but irrelevant here: if the
scan had ever *returned* (empty or not), the 1.1 build would have written
`no vehicle records yet` or `vehicle records appeared: N record(s)` and moved
`M.phase`. Neither string exists anywhere in the 966-line log, and `M.phase`
never left the uptime branch in 351 runtime snapshots. The scan never returned.

The correction matters for method: **an absence of log lines after a gate is
evidence of a swallowed exception, not of a decision.** From now on every
unexpected failure is recorded (`M.errors`, `M.last_error`, rate-limited log
line) and there is a 60 s heartbeat, so "nothing happened" can always be
distinguished from "the code stopped running".

## The fix / 修复内容

| Defect | Fix in `src/vehicle_cooldown.lua` | Test |
| --- | --- | --- |
| Shadowed table base | assign the existing upvalue (`table_base=table_base_at_load`), publish `M.table_base` | `test_resolved_table_base_reaches_the_slot_reader`, `test_deployed_1_5_1_stays_silent_and_the_error_is_the_nil_table_base` |
| Wrong self signature | `F.snapshot_ok=function(F,now,cfg)` | `test_shadowing_fix_alone_still_never_writes`, `test_stability_gate_opens_after_the_window` |
| Unguarded sweep | `sane_ptr()` range check (user-mode canonical, integral, ≤ 2^47) before any FFI pointer, per-slot `pcall`, contained-fault counters | `test_poison_slot_does_not_abort_the_scan`, `test_no_out_of_range_pointer_ever_reaches_the_ffi`, `test_unexpected_fault_is_contained_and_reported` |
| Silent failure | `note_error()` writes `error: ...`, `M.errors` / `M.last_error`, 60 s heartbeat with state/targets/errors | `test_heartbeat_and_effective_config_are_published` |
| No visibility into the scan | logs `slots/records/matched/rejects/contained_faults` and the candidate list | scan-summary assertions in the regression tests |
| Stale table base can never heal | bounded re-resolve (`RE_LOCATE_MAX=5`, 2 min apart) while the table yields no readable record | `test_re_resolve_is_bounded` |

Behaviour is otherwise unchanged from the reviewed 1.5.x design: stability gate
before any write, read-back verification, rollback and stand-down on a failed
write, watch loop that re-applies when the engine resets the field, empty target
sets never cached.

## Install state (this machine) / 本机安装状态

The manager keeps one entry for this mod, keyed by the manifest GUID
`e5a9c3d5-7d02-4f38-b956-1c2d3e4f5a6b`. A second folder/entry with the same GUID
would be a duplicate, so the fix was delivered as an **in-place upgrade of that
existing library entry** instead of a second import:

| Item | Value |
| --- | --- |
| Library folder | `%LOCALAPPDATA%\hd2arsenal\mods\HD2-VehicleCooldown-1.5.1-fixed_AR674323` (name kept - the manager resolves it by GUID) |
| Payload now | 1.6.0, `Addon\9ba626afa44a3aa3.patch_0` sha256 `97b99181adcc53d4...`, byte-identical to `src/vehicle_cooldown.lua` (verified) |
| Record | `contentHash` updated, `deployed=false` (the game layer still holds the 1.5.1 build), `enabled=true` |
| Backups | the previous library folder under `outputs/archive/other/vehiclecooldown/arsenal-library-backup-*`, plus `hd2a_data.json.bak-before-vc160-<stamp>` |
| Left to do | press **Deploy** in Arsenal with the game closed - that writes the new layer; the runtime log then decides |

This was a file-level delivery: no window/input automation, and nothing was
written to the game directory or to a deployed layer. The envelope was produced
by the official packer (0x11 magic, `-- HD2-Addon:` header, same GUID), i.e. the
format Arsenal itself imports.

## Verification status / 验证状态

* Offline: 20 sandbox checks pass (`python -m unittest discover -s tests -v`),
  including a reproduction of the deployed build's silent failure and a
  check that no out-of-range pointer ever reaches the FFI layer.
* Source/build: compiles under LuaJIT (`work/standalone/build_vc.py
  --validate-only`), plain UTF-8 without BOM/NUL, no user32 symbols.
* **Not verified in game.** No mission has been run with 1.6.0 yet, so the
  release candidate claims no in-game effect. The next session should show, in
  `Logs\VehicleCooldown.log`: `table located at load` → `v1.6.0 installed` →
  `uptime gate passed` → `vehicle records appeared: N target(s)` →
  `cooldown applied to N target(s)`, then a heartbeat every 60 s. Missing
  stages name the remaining problem directly, and
  `tools/analyze_vehicle_cooldown_log.py` prints that verdict in one command.
* Minor hardening that came with the import: the offline backdoor flag moved
  from the collision-prone `_G.VC_TEST_MODE` to `_G.__HD2_VC_TEST` (any mod that
  happened to set the old global would have turned the addon into a test-only
  stub), and the workspace's backdoor-only `work/standalone/test_vc.py`
  (3 checks) is superseded by this repository's 20-check sandbox suite, which
  also drives the real state machine instead of only the exported helpers.

## Boundaries / 边界

* Only this addon changed. Third-party mods stay read-only in the workspace;
  the AOB resolver family and the record layout are used under the attribution
  recorded in `THIRD_PARTY_NOTICES.md`.
* No game file, Arsenal library entry or deployed layer was written by this
  work. Delivery is the importable ZIP in `dist/`; deployment is the user's
  Arsenal action (the 2026-10-01 black-screen incident was caused by
  hand-writing layers, and that route stays closed).
