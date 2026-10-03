# Silent no-op evidence / 不生效取证（2026-10-03）

Scope: why 战备冷却 / Stratagem Cooldown 1.5.1-fixed (internal v1.1, and v1.0 before it)
never applied a cooldown in the real game, and how that was turned into an
executable reproduction.  Raw player logs stay outside this repository; only
derived counts and short quoted lines are recorded here.

范围：说明载具冷却 1.5.1-fixed（内部 v1.1，以及更早的 v1.0）为何在实机中从未生效，
以及如何把它变成可离线复现的证据。原始玩家日志不入库，这里只记录统计结果与少量原文。

## 1. Artefacts / 现场物证

| Item | Value |
| --- | --- |
| Game layer (deployed addon) | `Helldivers 2\data\9ba626afa44a3aa3.patch_293` |
| Layer sha256 | `B873B2ECFCA68B54E17467A4A24E0D425FFA08D610310045690617980E5C25E6` |
| Addon text sha256 | `1c27dcaf609c1cd8523f4768279d2ba8950a0399f49dbefc3c57536c5a9ece0c` (427 lines) |
| Addon text copy | [`vehicle-cooldown-1.5.1-deployed.lua`](vehicle-cooldown-1.5.1-deployed.lua) |
| Arsenal library entry | `%LOCALAPPDATA%\hd2arsenal\mods\HD2-VehicleCooldown-1.5.1-fixed_AR674323\` |
| Package GUID | `e5a9c3d5-7d02-4f38-b956-1c2d3e4f5a6b` |
| Former package | `outputs/archive/other/vehiclecooldown/HD2-VehicleCooldown-1.5.1-fixed.zip`, sha256 `1F3DD826D23678EDB792B884F32041A86EE417006E6BB23515B8AA7961216E08` |
| Loader report | `BingusSharedLoader.log`: `mods/codex/vehicle_cooldown: loaded` (loads fine, no load-time error) |

The layer text is byte-identical to the Arsenal library payload, so the deployed
build is unambiguous: `v1.1` as reproduced in the fixture above.

## 2. What the log shows / 日志事实

`%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\VehicleCooldown.log`, read with
[`tools/analyze_vehicle_cooldown_log.py`](../../tools/analyze_vehicle_cooldown_log.py):

```text
913 lines, 160 session(s), versions {'1.0': 39, '1.1': 126}
  locate failed 8      (2026-09-29 early builds: "base anchor missing")
  located      159
  installed    165
  gate         99
  records       0      <- never
  no-records    0      <- never
  applied       0      <- never
  rollback      0
  error         0
last session stages: installed, gate
verdict: reached the uptime gate and produced no scan result
    | 2026-10-02T17:31:49Z v1.1 installed: all-vehicle cooldown, uptime gate 120s, stable gate 6s
    | 2026-10-02T17:32:18Z waiting uptime: uptime 29s
    | 2026-10-02T17:33:29Z waiting uptime: uptime 99s
    | 2026-10-02T17:33:49Z uptime gate passed - observing table stability
```

Two conclusions follow directly:

* the addon loaded, resolved the table **and** passed the uptime gate, so the
  load path, the AOB resolver and the timing gate all work;
* after the gate it never logged anything again - not "records appeared", not
  "no vehicle records yet", not an error. The state machine died inside the
  first scan while `pcall(tick_cooldown)` swallowed the reason. 39 sessions of
  v1.0 and 126 of v1.1 behaved identically, so the v1.1 "re-scan empty set" fix
  could not have helped: the failure is upstream of it.

SmoothBoot publishes `_G.HD2VehicleCooldown` scalar fields in its runtime
snapshot (`runtime state HD2VehicleCooldown: ...`). Across the whole log:

```text
351 snapshots
  status=uptime gate passed - observing table stability   268
  status=v1.1 installed ...                                36
  status=waiting uptime: ...                            (rest)
  phase=uptime 119s                                       (frozen, forever)
```

`phase` is only ever written by the uptime branch and by the "no vehicle
records yet" branch. It stays at the *last uptime value* in every snapshot, so
the "empty enumeration was cached" theory is falsified: the scan never returned
at all, neither empty nor populated.

## 3. Executable reproduction / 可执行的复现

`tests/vc_sandbox.py` runs the addon against a synthetic `game.dll` image (real
AOB pair, `lea r15` anchor, PE header, chunked reads) plus a fake kernel32 and
fake ffi cdata.  `tests/test_vehicle_cooldown.py::TestArchivedDeployedBuild`
loads the byte-exact deployed text and captures what `pcall` swallowed:

```text
--- deployed 1.5.1, clean table, swallowed error(s): 14
    [.../vehicle_cooldown...]:222: attempt to perform arithmetic on
    upvalue 'table_base' (a nil value)
    log: ['table located at load (single pass)',
          'v1.1 installed: ...',
          'uptime gate passed - observing table stability']
```

Line 222 is the first statement of `slot_ptr()`:

```lua
local function slot_ptr(id)
    local b=read_at(table_base+id*8,8)      -- table_base is nil for this closure
```

and the reason it is nil is the load-time assignment in v1.0/v1.1:

```lua
local table_base=nil                        -- upvalue captured by slot_ptr/rec_info
local function locate_table() ... end
...
local table_base,locate_err=locate_table()  -- *new* local: shadows the upvalue
```

The resolver's result lands in a local that nothing reads, while every reader
keeps the original `nil` upvalue.  The first slot read of the first post-gate
scan therefore raises, `pcall(tick_cooldown)` hides it, and the session ends
with a live-looking addon that does nothing.  This is reproduced exactly -
including the frozen `phase` - by the archived-build test.

Repairing only that line is not enough: the same test suite shows the second
defect (`F.snapshot_ok=function(now,cfg)` called as `cd:snapshot_ok(now,cfg)`,
so `now` becomes the feature table and the arithmetic raises).  Both are fixed
in 1.6.0, and both fixes are asserted by tests that fail on the archived text.

## 4. Not yet proven / 尚未证明

* No in-game run of 1.6.0 yet: the offline sandbox proves the decision logic,
  the failure containment and the write/verify/rollback path, not the real
  memory layout, the actual stratagem ids or the game's own behaviour.
* The synthetic table is built from the layout validated by Tank Cooldown v2
  (id at +0x00, name pointer at +0x10, cooldown at +0x68, record read 0xB0).
  If a game patch moves those fields, the log's counters
  (`slots/records/matched/rejects`) will show it instead of staying silent.
