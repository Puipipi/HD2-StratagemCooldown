# 战备冷却 / Stratagem Cooldown / 载具冷却

**1.9.0 候选：一个模组覆盖红/蓝/绿全部战备（含次数修改）；尚未实机验证。**
**1.9.0 candidate: one addon for red/blue/green stratagems incl. charges. Not yet validated in game.**

作用：缩短所有载具战略配备（坦克、机甲、FRV）的重新部署冷却，默认 390 秒（原版 780 秒）。
依赖 Bingus Shared Loader v15+（API 1）。安装包：[`dist/HD2-VehicleCooldown-1.6.0.zip`](dist/HD2-VehicleCooldown-1.6.0.zip)。

**1.9.0：一个模组覆盖全部战备**，红/蓝/绿在配置文件里勾选，蓝战备另有
就载具/就机甲/就载具和机甲/全部 的互斥选择，次数（+0x50）也可改。配置项与实机字段取证见
[1.9.0 配置与字段说明](docs/all-stratagem-1.9.0-config.md)。

## 为什么不生效（实机取证结论）

1.5.1-fixed（内部 v1.1）在 160 次启动里：加载正常、表定位正常、99 次通过 120 秒开机门槛，
然后**一次都没有**打印扫描结果，也从未写入冷却值——`M.phase` 永久停在 `uptime 119s`。
原因是三个被 `pcall(tick_cooldown)` 吞掉的缺陷：

1. **表基址被同名局部变量遮蔽**（v1.0/v1.1 相同）：`local table_base,locate_err=locate_table()`
   新建了一个局部变量，而 `slot_ptr()` 捕获的上值 `table_base` 永远是 `nil`，第一次读槽位就抛
   `attempt to perform arithmetic on upvalue 'table_base' (a nil value)`；
2. **稳定门槛自参数签名写错**：`F.snapshot_ok=function(now,cfg)` 却用 `cd:snapshot_ok(now,cfg)` 调用，
   `now` 收到的是功能表，`now-F.last_sample` 直接报错（修好第 1 条也写不进去）；
3. **146 槽扫描跟随未校验指针**（纵深防御项，非本次崩点）：`0xFFFFFFFFFFFFFFFF` 这类填充值会变成
   ≥ 2^64 的浮点数，`ffi.cast` 无法表示而抛错，一个坏槽位就能整段中止。

完整取证、原文与离线复现命令见
[根因文档](docs/root-cause-2026-10-03-vehicle-cooldown-silent-no-op.md) 与
[证据摘要](research/evidence/silent-no-op-evidence-2026-10-03.md)。

## 修复要点

- 表基址写回既有上值，并把结果发布为 `M.table_base` 以便核对；
- 稳定门槛改为 `function(F,now,cfg)`；
- 所有指针在进入 FFI 前做范围校验，逐槽 `pcall` 隔离，坏槽位不再拖垮整段扫描；
- 任何异常都写日志并计入 `M.errors` / `M.last_error`，另有 60 秒心跳，杜绝“静默不生效”；
- 扫描结果计数（slots/records/matched/rejects/contained_faults）与候选列表写入日志；
- 表完全读不到记录时，间隔 2 分钟、最多 5 次重新解析表基址；
- 其余行为沿用已评审设计：写前稳定门槛、回读校验、失败回滚并停用、watch 循环自动补写、空集不缓存。

## 本地检查

```powershell
python -m pip install -r requirements-dev.txt
python -B work/standalone/build_vc.py --validate-only
python -m unittest discover -s tests -v
```

20 项离线检查通过，其中两项直接加载
[1.5.1 实机部署原文](research/evidence/vehicle-cooldown-1.5.1-deployed.lua)（sha256
`1c27dcaf...`）复现“通过门槛后永久沉默”，并断言 1.6.0 在同一场景下能写入。
**离线检查不等于游戏验收**：没有实机跑过任务，不宣称任何游戏内效果。

日志判定工具（只读，不改游戏）：

```powershell
python -B tools/analyze_vehicle_cooldown_log.py
```

它输出最后一次会话经历了哪些阶段与结论；健康会话应当是
`installed → gate → vehicle records appeared → cooldown applied → heartbeat`。

## 性能 / Overhead

在运行中的游戏进程上实测 `ReadProcessMemory` 单价（8B ≈ 4.8µs、176B ≈ 5.6µs、
1MB ≈ 1.09ms），再按调用次数换算：

- 每帧：**0 次内存读取**（纯 Lua 比较），约 0.002ms；
- watch 巡检（13 个目标）：每 5 秒 0.15ms；
- 空闲全表扫描（0..255，仅在没有记录时每 10 秒一次）：1.68ms；
- 加载时解析 game.dll 镜像：约 78ms（一次性，v2 也这么做）；
- 复制探针（搜索重复记录结构）：约 0.45 秒 → **1.7.3 起默认关闭**（`probe=yes` 才开）。

稳态约 **0.2ms/s**（含空闲扫描 <0.35ms/s）；同机模组链普遍 0.6–3.8ms/帧
（60–380ms/s），本模组约占其 0.1–0.5%。复测：

```powershell
python -B tools/measure_overhead.py
```

完整方法与逐项对照见 [性能审计](docs/performance-audit-2026-10-03.md)。
注意模组自报的 `HD2Perf` 数值受 `os.clock()`（Windows 约 15.6ms 分辨率）限制，
亚毫秒开销会被舍成 0.000，不能用来验收。

## 安装状态 / Install state

管理器里本模组按其 manifest GUID 记账，因此本次修复是把**已有那条库记录原地升级**，
而不是再导入一份（同 GUID 的第二份会被当成重复项）：

- 库目录沿用 `%LOCALAPPDATA%\hd2arsenal\mods\HD2-VehicleCooldown-1.5.1-fixed_AR674323`
  （目录名不改，管理器按 GUID 解析）；
- 目录内已是 1.6.0 的正式信封包，`Addon\9ba626afa44a3aa3.patch_0` 的正文与
  `src/vehicle_cooldown.lua` **逐字节一致**（已校验）；
- 记录里的 `contentHash` 已更新、`deployed=false`（游戏层里还是 1.5.1 的旧层）；
- 旧库目录与 `hd2a_data.json` 各自留了备份，见 `docs/root-cause-2026-10-03-*.md`。

**剩下一步是你在 Arsenal 里按“部署”**（先关游戏）。全过程只动文件，没有写游戏目录，
也没有自动点击你的界面。

In the manager the mod is keyed by its manifest GUID, so the fix is an in-place
upgrade of the existing library entry (a second entry with the same GUID would
be a duplicate): the folder keeps its name, its payload is now 1.6.0 and is
byte-identical to `src/vehicle_cooldown.lua`, the record's `contentHash` is
updated and it is marked as needing deployment. The previous folder and
`hd2a_data.json` are backed up. Press **Deploy** in Arsenal (game closed) to
write the new layer; no game file was touched by the import itself.

## 打包

```powershell
python -B work/standalone/build_vc.py --output-dir dist
```

需要按 `THIRD_PARTY_NOTICES.md` 提供的外部封装工具
（`work/standalone/vendor/bingus/`，按项目惯例不入库）。
GUID 固定为 `e5a9c3d5-7d02-4f38-b956-1c2d3e4f5a6b`，Arsenal 据此把它当作 1.5.1-fixed 的升级，
而不是新装一份。构建不写游戏目录、不部署；请自行在 Arsenal 导入并部署。

## 边界

- 只改本模组；第三方模组保持只读参考，署名见 `THIRD_PARTY_NOTICES.md`。
- **不要与 Tank Cooldown v2 同时启用**：两者写同一字段。
- 配置：`%LOCALAPPDATA%\CowboyBingus\Helldivers2\VehicleCooldown\config.txt`
  （`cooldown=yes|no`、`cooldown_s=390`、`stable_s=6`、`uptime_s=60`）。
  老配置里的 `uptime_s=120` 会继续生效——想更快生效就改成 60。
- 日志：`%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\VehicleCooldown.log`。

## Repository rules / 仓库约定

本仓库有独立 `.git` 与提交历史；根工作区忽略整个 `mods/`，实机证据、历史包与第三方只读参考
留在工作区，两边不自动同步。改动只在本仓库提交，部署前核对与工作区旧副本的差异。

---

## English

**Status: 1.6.0 candidate - source, tests and package complete; no in-game run
yet.**

Shortens the redeploy cooldown of every stratagem vehicle (tanks, exos, FRV),
default 390 s instead of the vanilla 780 s. Requires Bingus Shared Loader v15+
(API 1). Enable both and deploy; do not run Tank Cooldown v2 alongside it.

Why 1.5.x never worked: across 160 launches the addon loaded, resolved the
table and passed its uptime gate 99 times, yet never logged a scan result and
never wrote a value (`M.phase` frozen at `uptime 119s`). Three defects, all
swallowed by `pcall(tick_cooldown)`: the resolved table base was stored in a
shadowing local, so the `table_base` upvalue used by `slot_ptr()` stayed `nil`
and the first slot read raised; the stability gate declared
`function(now,cfg)` but was called as `cd:snapshot_ok(now,cfg)`; and the
146-slot sweep followed unvalidated pointers. See the
[root cause document](docs/root-cause-2026-10-03-vehicle-cooldown-silent-no-op.md)
and the [evidence summary](research/evidence/silent-no-op-evidence-2026-10-03.md).

1.6.0 assigns the existing upvalue, fixes the gate signature, range-checks every
pointer before it reaches the FFI, contains each slot read, logs and counts any
unexpected error, publishes scan counters and a 60 s heartbeat, and re-resolves
the table (bounded) when it yields no readable record. The reviewed safety
design is unchanged: stability gate before writing, read-back verification,
rollback and stand-down on failure, watch-and-re-apply, empty sets never
cached.

```powershell
python -m pip install -r requirements-dev.txt
python -B work/standalone/build_vc.py --validate-only
python -m unittest discover -s tests -v
python -B tools/analyze_vehicle_cooldown_log.py
```

20 offline checks pass, including two that load the byte-exact deployed 1.5.1
text and reproduce its silent failure. Offline checks are not game acceptance:
no mission has been run with 1.6.0, and no in-game effect is claimed.
