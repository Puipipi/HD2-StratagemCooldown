# 变更记录 / Changelog

4.9.24 起中英双语；更早的条目保留原文（中文）。
Bilingual from 4.9.24; earlier entries are kept as written (Chinese).

---

## 4.9.24 — 2026-10-07

**中文**
* 修复「主机被当成客机、共享战备（增援 / 补给 / 地狱火 / 撤离 …）完全不生效」。
* 判定改为照 p2p 延迟显示模组的实现：引擎表挂在 `stingray` 上（不是 `_G`），且
  `game_session()` / `peer_id()` 是**函数**，必须调用。
* 判定每 0.5 秒重算；读不到时不再默认客机（保留上次结论，从未有过则按主机，日志标注 `assumed`）。
* 主机 → 客机中途切换时，共享战备写回游戏原值，不再显示我们改小的数字。

**English**
* Fixes "a host is judged a client, so squad-shared stratagems (reinforcement, resupply, hellbomb,
  extraction …) do nothing at all".
* Detection now follows the P2P Ping mod: the engine tables live on `stingray` (not `_G`), and
  `game_session()` / `peer_id()` are **functions** and must be called.
* Re-derived every 0.5 s; an unreadable engine no longer means "client" (the last verdict is kept,
  host until one exists, logged as `assumed`).
* On a host → client switch the shared records are written back to the game's own values.

---

## 4.9.19 — 2026-10-06

**中文**：客机不再写共享战备 —— 实测主机的数值不会传到客机，自己写只会让两边数字不一致。  
**English**: Clients no longer write squad-shared stratagems — the host's value never reaches a client,
so writing only made the two players disagree.

## 4.9.14 / 4.9.10 — 2026-10-06

**中文**：呼叫落地时间、飞鹰同时呼叫两项实验下线（实测 `0x34` 只影响面板显示、`0x64` 只对载具/驱逐舰有效），设置页不再留没有效果的选项。  
**English**: The call-in landing-time and Eagle simultaneous-call experiments were retired (`0x34` only
changes the panel display, `0x64` only applies to vehicle/destroyer call-ins), so the options page keeps
no option that does nothing.

## 4.9.1 — 2026-10-06

**中文**：安全闸 —— 记录表的 id+hash 锚点不通过就什么都不写（此前误解析到错误的表会导致 `0xC0000005` 崩溃）。  
**English**: Fail-safe — nothing is written unless the table's id+hash anchors pass (a mis-resolved table
used to crash the game with `0xC0000005`).

## 4.0 – 4.8 摘要 / Highlights

**中文**：冷却百分比为滑块（10–100，任意整数）；「最低优先级」让出规则（别的模组正在改的记录我们放弃）；
次数的镜像写入因进任务崩溃而移除，改为每次写入回读校验；游戏内设置页改为纯英文；共享/任务类战备只由主机修改。  
**English**: cooldown percentage as a slider (10–100, any integer); the lowest-priority yield rule (a record
another addon is editing is given up); the mirrored charge writes removed after a mission-entry crash, every
write read-back verified; English-only options page; squad-shared/objective stratagems modified on the host only.

---

## 更早（原文，中文）/ Earlier (as written, Chinese)

## 2.4.13
* 游戏内设置页接入 **Mod Options Menu** 框架（`_G.ModOptionsMenu`，api 1）：注册 7 项 —— 启用、
  冷却保留(80%/50%)、红战备(关闭/轨道+飞鹰/只轨道/只飞鹰)、蓝战备(载具/机甲/两者/全部/关闭)、
  绿战备(开关)、次数(无/+1/+2/+3/无限)、飞鹰次数(无/+1/+2/+3)；注册会**反复重试**（addon 加载顺序不定），
  会话开始时应用菜单上次保存的值（**config.txt 显式键优先**），点击改动会立刻重扫描生效。
* `tools/verify_release.py` 增加该集成的检查（用假宿主注入：注册 7 项、保存值生效、config.txt 优先）。
* payload 内嵌说明与包内 README 都写明了这一页。

## 工具 / Tooling（无版本变更）
* 新增 `tools/verify_release.py`：一条命令复验出货包，共 **33 项检查** —— 包结构、payload 可编译且不启动
  进程、7 组平铺键与 6 组分节 INI 行为、4 组日志与管理器读取（用**合成**数据库验证“读管理器勾选”这条
  路径，不动玩家的真实 Arsenal 数据），以及用 node 真跑 `config-builder.html` 的 JS 再喂回模组。
* 这些验证此前散落在被 gitignore 的 `work/scratch/` 下（不随仓库保存），现在固化进仓库、任何人可复现。

## 2.4.11
* 仓库自带测试从 **19 项失败改为全绿**（24 + 19 项）：原因是测试继承了旧出货默认（50%、全类别开启），
  现在每个测试都**显式声明**自己要测的档位（百分比 + 范围）；并把 2.2.2 的飞鹰规则写进断言
  （请求无限时飞鹰保持原次数，-1 对飞鹰表示“已耗尽”）。
* `effective:` 日志行增加 `min_cooldown=`，被阈值跳过的战备在日志里也能解释清楚。

## 2.4.10
* payload 自带说明（guide）与实测语义对齐：删掉已不存在的“方案 / Profile”组说明，默认值改为
  “只载具 80%”，补上 `eagle_uses_add`、分节写法与 config-builder.html。
* 仓库新增 `assets/config-builder.html` 作为生成器的唯一源文件，并断言包内副本逐字节一致。

## 2.4.9
* 生成器校验输入：未知的 blue 取值不再生成 `blue_scope=<无效词>`。

## 2.4.8
* 端到端以 node 实跑生成器 JS → config.txt → 沙箱，6 组全绿；包内 README 增加日志说明。

## 2.4.7
* 根 manifest 补 `IconPath`（与参考包一致）；`Addon/` 内不再含多余的嵌套 manifest。

## 2.4.6
* 打包结构与所有“双管理器可用”的参考包同构；保留工作层中确实存在的 `.stream`/`.gpu_resources`。

## 2.4.5
* 删除重复的 `eagle_uses` 读取块（日志曾打印两次 `eagle=+3`）。

## 2.4.4
* 日志改为打印解析结果：`blocks(from manager DB): <勾选> | explicit: <config.txt 键> | effective: <最终生效>`
  （此前因 `pcall` 返回值处理错误只打印 `true`）。

## 2.4.2
* 修正 `red` / `blue` 的组语义：`red=yes` 会同时打开 orbital/eagle；`blue=all` 直接给出范围。
  （2.4.1 的提交信息曾声称已验证，实际有两项失败——由沙箱抓出，已更正。）

## 2.4.1 / 2.4.0
* 恢复通用打包：根 `Addon/9ba…patch_0` + 单个 `Include: ["Addon"]` 选项 + `config-builder.html`
  + 分节 INI（`[cooldown] [scope] [charges] [eagle]`）。
* 去掉 Arsenal 专有的 `Options[]` 多选树（它会导致管理器条目在下次启动时消失、必须强制重装）。

## 2.3.0
* 自包含默认：读不到任何管理器数据库时使用保守默认（只载具 80%、次数不动），不再退回“全类别 50%”。
* 目录改用 kernel32 `CreateDirectoryA` 创建，空白机器也会生成日志、不再闪 cmd 窗口。

## 2.2.2
* 飞鹰永不写 -1（对飞鹰而言 -1 表示“次数耗尽等补给”，会让弹种显示不可用）。

## 2.2.1
* 组定位锚定到记录名（`"name": "…"`），修复“描述里出现同名块导致该块被整段忽略”的问题。

## 2.1.x 及更早
* 见 git 历史：单 addon 架构（一个模组只会执行一个 addon）、读取管理器勾选、写入时机改为加载时，
  以及 `+0x68`（冷却）/`+0x50`（次数）两处的实测定位过程。
