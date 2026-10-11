English / [简体中文](https://github.com/Puipipi/HD2-StratagemCooldown/blob/main/README_cn.md)

# HD2 Vehicle Cooldown

**Imported snapshot: 1.5.1-fixed (internal v1.1); confirmed ineffective in game.**

This repository follows the project layout: `src/` contains runtime source, `tests/` offline checks, `tools/` read-only diagnostics, `work/standalone/` the build script, `docs/` design and root-cause records, and `research/evidence/` captured evidence and the frozen sample. This snapshot imports only the **as-deployed source** and repository skeleton. It does not contain a fix.

Facts from in-game logs and runtime snapshots, with frozen samples in [research/evidence](research/evidence/): the addon loads, resolves the `game.dll` table, and passes its startup gate 99 times, but never prints a scan result, never writes a cooldown value, and `M.phase` remains at `uptime 119s`. The log records 165 installs / 99 gate passes / 0 scan results. Diagnosis and repair are documented in later commits.

## Repository rules

The repository has its own `.git` history. The parent workspace ignores the entire `mods/` directory. Third-party mods are read-only references; the addon is not deployed automatically and does not write directly to the game layer. Public snapshots exclude personal configuration, raw player logs, and crash dumps. `research/private/` remains outside version control.

See [third-party notices](THIRD_PARTY_NOTICES.md) for dependencies, credits, exclusions, and licensing terms. No new license grant for this project's own code is made by this snapshot.
