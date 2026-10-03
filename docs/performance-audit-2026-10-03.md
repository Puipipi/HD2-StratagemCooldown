# Overhead audit - 战备冷却 / Stratagem Cooldown 1.7.3 / 性能开销核对

Date: 2026-10-03. Method: measure the real cost of the three
`ReadProcessMemory` shapes this addon uses on the **live game process**
(see [`tools/measure_overhead.py`](../../tools/measure_overhead.py), read-only),
then multiply by the addon's own call counts. The game's Lua-side self-report
(`HD2Perf['vehicle_cooldown']`, shown by the watchdog as
`self-reported: vehicle_cooldown=X ms`) cannot be trusted for this: it is built
from `os.clock()`, whose Windows resolution is ~15.6 ms, so sub-millisecond work
is rounded away.

## Measured unit costs (same machine, game in a mission)

| Call shape | Calls timed | Cost |
| --- | --- | --- |
| `ReadProcessMemory` 8 B (slot pointer) | 3000 | **5.0 us** |
| `ReadProcessMemory` 176 B (record) | 800 | **4.5 us** |
| `ReadProcessMemory` 64 B (name string) | 1500 | 2.4 us |
| `ReadProcessMemory` 1 MB (image chunks) | 48 | **0.99 ms** (~1.0 GB/s) |

## Cost of each component (derived)

| Component | Frequency | Cost | Average |
| --- | --- | --- | --- |
| Per frame (steady state) | 85 fps | 0 FFI calls, pure Lua (`os.clock` + compares) | ~0.17 ms/s |
| Watch pass (13 targets, 2 reads each) | every 5 s | 0.12 ms | 0.023 ms/s |
| Idle sweep, ids 0..255 (1.7.3) | every 10 s **while no records** | 1.63 ms | 0.16 ms/s |
| Idle sweep, ids 0..511 (1.7.2 and earlier) | every 10 s | 3.21 ms | 0.32 ms/s |
| Field map, one log line per record | once per session | ~0.06 ms | - |
| Resolver over the game.dll image | once at load | **~70 ms** | - |
| Copy probe (memory search for duplicate records) | once per session, was default | **~411 ms** | - |

Steady state after the first write (the normal case: the sweep stops and only
the watch loop runs) is **~0.2 ms/s**; with the periodic idle sweep it stays
**below 0.35 ms/s**. For scale, the managed mod chain on this machine reports
0.6-3.8 ms per frame (60-380 ms/s), so this addon is roughly 0.1-0.5% of it, and
0.02-0.05% of one core.

## What 1.7.3 changed because of this audit

| Finding | Change |
| --- | --- |
| The diagnostic copy probe cost ~0.4 s of `ReadProcessMemory` per session (2 x 16 MB per target) | now **opt-in** (`probe=no` by default). It already answered its question: no duplicate record structure exists |
| Sweep 0..511 was 2x more than needed (the table holds 149 named records, highest vehicle id 147) | sweep narrowed to **0..255** (1.63 ms every 10 s) |
| `M.phase` was rebuilt with a string concat + pairs loop **every frame** during the observe window | only rebuilt when the value actually changes |
| The self-reported cost cannot show sub-millisecond work | documented here; use the external measurement instead |

## Reference point: the v2 mod it replaces

Tank Cooldown v2 also scanned the whole game.dll image once at load (comparable
~70 ms) but then re-validated and re-applied its two records **every 120
frames** (~1.4 s), including a `read_at` + hash/package comparison per record,
and it wrote at load without a stability gate. Its cost is not the complaint
here - its two-record loop is small - but it had no bound on repeated writes and
no rollback, which is where its crash reports come from. This addon keeps the
same one-shot load-time resolver, checks records once per 5 s (read-only) and
only writes when a value actually differs.
