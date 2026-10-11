[English](https://github.com/Puipipi/HD2-StratagemCooldown/blob/main/README.md) / 简体中文

# HD2 Vehicle Cooldown / 载具冷却

**导入快照：1.5.1-fixed（内部 v1.1），实机确认不生效。**

本仓库按项目位置规则建立：`src/` 运行源码、`tests/` 离线检查、`tools/` 只读诊断、`work/standalone/` 构建脚本、`docs/` 设计与根因记录、`research/evidence/` 取证与冻结样本。本次提交只导入**实机部署原文**与仓库骨架，尚未修复。

已知事实（来自实机日志与运行快照，冻结样本见 [research/evidence](research/evidence/)）：加载正常、`game.dll` 表定位正常、99 次通过开机门槛，但**从未**打印扫描结果、从未写入冷却值，`M.phase` 永久停在 `uptime 119s`。日志共 165 次安装 / 99 次过门槛 / 0 次扫描结果。诊断与修复在后续提交中给出。

## 仓库约定

本仓库有独立 `.git` 与提交历史；根工作区忽略整个 `mods/`；第三方模组只读；不自动部署、不直写游戏层。公开快照不包含个人配置、原始玩家日志和崩溃转储；`research/private/` 保持在版本控制之外。

依赖、致谢、排除内容与许可条款见[第三方声明](THIRD_PARTY_NOTICES.md)。本快照未对本项目自身代码授予新的许可。
