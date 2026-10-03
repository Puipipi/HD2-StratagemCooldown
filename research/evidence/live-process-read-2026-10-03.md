# Live process read: why the 1.6.0 write had no effect / 实机内存取证

Date: 2026-10-03. Read-only inspection of the **running** game process
(`PROCESS_VM_READ`, no writes, no input automation) while the player was in a
mission, after 1.6.0 had been deployed. The addon's own log for that session:

```text
v1.6.0 installed ... uptime gate passed (120s) ...
vehicle records appeared: 3 target(s) [1=VEHICLES. BASTION(TANK)/780,
    10=VEHICLES. COMBAT WALKER OBSIDIAN/420,
    105=VEHICLES. FAST RECON VEHICLE (FRV)/480]
cooldown applied to 3 target(s) [...]
heartbeat: state=watch phase=watch (3 target(s)) targets=3 scans=1 errors=0
```

## What the live process showed

Resolved with the same AOB resolver the addon uses
(`game.dll` base `0x7FF910530000`, table `0x7FF913CFB600`), then the slot array
(ids 0..511) was read directly:

| id | name | cooldown field (+0x68) |
| --- | --- | --- |
| 1 | `VEHICLES. BASTION(TANK)` | **390.0** (patched by 1.6.0) |
| 10 | `VEHICLES. COMBAT WALKER OBSIDIAN` | **390.0** (patched) |
| 26 | `VEHICLES. FAST RECON VEHICLE (RESUPPLY AUTO TURRET)` | 480.0 |
| 27, 88, 91 | `VEHICLES. COMBAT WALKER [BREACHER/LUMBERER]` | 420.0 |
| 50 | `VEHICLES. STORM(TANK)` (= Maelstrom) | 780.0 - missed by 1.6.0 |
| 105 | `VEHICLES. FAST RECON VEHICLE (FRV)` | **390.0** (patched) |
| 135 | `VEHICLES. FAST RECON VEHICLE (RAMMING FLAMETHROWER)` | 480.0 |

So the write itself lands and survives (no watchdog re-apply was ever needed),
which removes "the write failed" and "another mod overwrote it" from the list.

Two further searches over **all** writable committed memory (~11 GB, 1 MB chunks):

* searching for each record's 8-byte header (id + hash) found **exactly one copy**
  of every vehicle record - the definition the addon already patches, no
  per-player/per-mission duplicate;
* searching for pointers to those records and to their name strings found only
  the table itself.

Conclusion: the game does **not** keep a second, later copy of the record that we
could patch. It reads the definition cooldown once while it builds its runtime
stratagem state, and that state is what the HUD/menu shows. A write 120 s after
mod load therefore arrives after the fact - which is exactly why the original
Tank Cooldown v2 mod worked: it patched the field **at mod load** (validating
Bastion/Maelstrom by id + hash + package first), and only then did the engine
build its state.

## Consequence for this addon

1.7.1 writes at load time (`uptime_s=0`, `stable_s=1` by default) while keeping
every 1.6.0 safety property (validation, per-field readback, rollback on a failed
write, watch loop that re-observes a rebuilt table). It also keeps the v2
identity anchors as a "the table is fully built" witness
(Bastion `id=1/hash=0x7756F32C`, Storm `id=50/hash=0x1B7853AC`) and reports them
in the log; a changed hash no longer disables the feature, it is just reported.

Not yet verified: no session has run with 1.7.1, so the timing conclusion is
still a hypothesis with strong circumstantial support (v2/at-load works,
1.6.0/at-120s does not, no duplicate structure exists to patch).
