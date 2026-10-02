# HD2 Vehicle Cooldown / 载具冷却

**导入快照：1.5.1-fixed（内部 v1.1），实机确认不生效。**

本仓库按项目位置规则建立：`src/` 运行源码、`tests/` 离线检查、`tools/` 只读诊断、
`work/standalone/` 构建脚本、`docs/` 设计与根因记录、`research/evidence/` 取证与冻结样本。
本次提交只导入**实机部署原文**与仓库骨架，尚未修复。

已知事实（来自实机日志与运行快照，冻结样本见 [research/evidence](research/evidence/)）：
加载正常、`game.dll` 表定位正常、99 次通过开机门槛，但**从未**打印扫描结果、从未写入冷却值，
`M.phase` 永久停在 `uptime 119s`。日志共 165 次安装 / 99 次过门槛 / 0 次扫描结果。
诊断与修复在后续提交中给出。

## English

Import snapshot: **1.5.1-fixed (internal v1.1), confirmed ineffective in game.**

This repository follows the workspace layout rules. This commit only brings in
the **as-deployed source** and the repository skeleton: `src/` runtime source,
`tests/` offline checks, `tools/` read-only diagnostics, `work/standalone/`
build script, `docs/` design and root-cause records, `research/evidence/`
captured evidence and the frozen deployed sample.

Known from the game's own logs and runtime snapshots: the addon loads, resolves
the game.dll table and passes its uptime gate 99 times, yet never logs a scan
result, never writes a cooldown and never moves `M.phase` past `uptime 119s`.
165 installs / 99 gates / 0 scan results. The diagnosis and fix follow in later
commits.

## Repository rules / 仓库约定

独立 `.git` 与提交历史；根工作区忽略整个 `mods/`；第三方模组只读；不自动部署、不直写游戏层。
Public snapshots exclude personal configuration, raw player logs and crash dumps;
`research/private/` stays outside version control.
