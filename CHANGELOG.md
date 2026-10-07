# 变更记录 / Changelog

4.9.24 起中英双语；更早的条目保留原文（中文）。
Bilingual from 4.9.24; earlier entries are kept as written (Chinese).

---

## 4.9.27 — 2026-10-07

**中文**
* 修复：**切换百分比后，记录里若是"我们上一档的数值"仍会被放弃**。实测日志 `adopting host value for 88 … now=84 ours=42 vanilla=420`：84 = 420×20%（上一档），42 = 420×10%（当前）。这一档我们**没写过**（值已等于目标，写入被跳过），所以它没进 `cd.ours`，被判成外人的值 → 记录被放弃。现在**本局用过的每个百分比**都记下来，`原版 × 用过的百分比` 一律算我们的值（看门循环与写入前的"外来值"检查都加了这条）。
* 顺带：额外战备槽的全部 19 个选项已逐条核对，除 4.9.26 修掉的那一条外没有别的误判；便携地狱火（`BACKPACK. HELLBOMB`）作为客机仍按规则跳过（它属于共享类，跟随主机）。

**English**
* Fix: **after changing the percentage, a record still holding the value of our previous setting was
  given up.** Measured: `adopting host value for 88 … now=84 ours=42 vanilla=420` — 84 is 420*20% (the
  previous setting), 42 is 420*10% (the current one). We had never written 84 (the field already equalled
  the target, so the write was skipped), so it was not in `cd.ours` and looked like a third party's value.
  Every percentage used this session is now remembered, and `vanilla * pct` counts as ours — in the
  watch-loop decision and in the pre-write foreign-value check.
* All 19 extra-slot choices were audited: apart from the one fixed in 4.9.26 there is no other
  misclassification; the Portable Hellbomb (`BACKPACK. HELLBOMB`) is still skipped on a client by design
  (it is squad-shared, so it follows the host).

---

## 4.9.26 — 2026-10-07

**中文**
* 修复：**额外战备槽带来的「M-103 补给小车」不生效**。额外战备槽模组里它写作 `type=26`，对应表内记录 26 = `VEHICLES. FAST RECON VEHICLE (RESUPPLY AUTO TURRET)`（原版 480 秒 ≈ 8 分）。旧代码在名字里搜到 `RESUPPLY` 就当成小队补给 → 客机时整条跳过。现在**载具 / 飞鹰 / 轨道 / 哨戒 / 固定炮台 / 团队武器 / 坦克**这些「自己的」类别不再参与共享判定。
* 顺手删掉重复了一份的共享判定，并修正共享日志的时机：以前在角色判定之前打印，客机也会写成 `host - writing our value`，现在按真实身份打印。

**English**
* Fix: **the extra-slot stratagem ("M-103 Supply FRV") was never reduced.** The extra-slot mod names it
  `type=26`, which is table record 26 = `VEHICLES. FAST RECON VEHICLE (RESUPPLY AUTO TURRET)` (480 s ≈ 8 min).
  The old test found `RESUPPLY` in the name and treated it as the squad's resupply, so a client skipped it
  entirely. Personal families (VEHICLES / EAGLE / ORBITAL / SENTRYS / EMPLACEMENTS / TEAM WEAPONS / TANK) no
  longer take part in that test.
* The duplicated copy of the shared test is gone, and the `shared …` log line now prints the real role — it
  used to be written before the role gate, so a client was logged as `host - writing our value`.

---

## 4.9.25 — 2026-10-07

**中文**
* 修复：**在游戏内改动百分比之后，还带着我们上一档数值的战备会被误判成「别的模组的值」而永久放弃**。日志实测：那一局开局是 10%（`780->78`），02:51:14 你把页面改成 60%，从 02:51:20 起每 5 秒放弃一个记录，共 **31 个**（FRV、机甲、轨道精准/激光/凝固汽油/380、迫击炮与机枪哨戒、特斯拉、补给背包…），整局都不再被修改 —— 看起来就像「模组失效」。
* 现在判定会先问「这个值是不是我们自己写过的」（`cd.ours`），是则重写而不是放弃；每次改动设置也会重新考虑曾被放弃的记录（日志 `settings changed: reconsidering N record(s)`），放弃日志会打印 `now= / ours= / vanilla=`。
* 别的模组真正占用的记录（例如补给模组的 77）仍会被放弃，这条规则不变。

**English**
* Fix: **after changing the percentage on the in-game page, every record that still carried our previous
  value was mistaken for "another addon's value" and given up for good**. Measured: the session started at
  10% (`780->78`), the page was changed to 60% at 02:51:14, and from 02:51:20 one record was dropped every
  5 s — **31 of them** (FRV, walkers, orbitals, sentries, Tesla, supply backpack …) for the rest of the
  session, which looks exactly like "the mod stopped working".
* The decision now first asks whether the value is one we wrote ourselves (`cd.ours`); if so it is rewritten
  instead of given up. A settings change also reconsiders records that were given up on
  (`settings changed: reconsidering N record(s)`), and the give-up log prints `now= / ours= / vanilla=`.
* Records genuinely owned by another addon (e.g. the supply mod's 77) are still given up — unchanged.

---

## 4.9.24 — 2026-10-07

**中文**
* 修复：**作为客机时，共享战备的冷却数字仍按我们改小的值走，没有跟主机一致**。判定不可靠（引擎表读错了位置，且把函数当值取用），客机没有进入「不写」分支；开主机时已写入的值也不会被撤销。
* 判定改照 p2p 延迟显示模组：读 `stingray.Network` / `stingray.GameSession`，`game_session()` / `peer_id()` 按**函数调用**，每 0.5 秒重算。
* 判定为客机时：不再写共享战备，并把先前写入的值**还原成游戏给的值**（实测日志：`role changed to client - re-scanning (restored the game value on 4 shared record(s))`）。非共享战备（你自己的红/蓝/绿）仍按设置生效。
* 读不到时不再默认客机：保留上次结论，从未有过则按主机。

**English**
* Fixes: **as a client, squad-shared stratagems kept counting from our reduced value instead of matching the host**. The verdict was unreliable (the engine tables were read from the wrong place and the accessors were used as values), so a client never took the "do not write" branch, and values written while hosting were never undone.
* The verdict now follows the P2P Ping mod: read `stingray.Network` / `stingray.GameSession`, **call** `game_session()` / `peer_id()`, re-derive every 0.5 s.
* On a client verdict: shared stratagems are not written, and values written earlier are **restored to the game's own numbers** (measured in game: `role changed to client - re-scanning (restored the game value on 4 shared record(s))`). Non-shared stratagems (your own red/blue/green) still follow your settings.
* An unreadable engine no longer means "client": the last verdict is kept, host until one exists.

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
