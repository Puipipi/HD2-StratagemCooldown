# 配置键（离线验证过的语义 / offline-verified semantics）

出货 payload：`dist/StratagemCooldown-2.4.2.zip` → `Addon/9ba626afa44a3aa3.patch_0`
验证方式：沙箱内存记录 + 出货 payload（`tests/vc_sandbox.py`），无管理器数据库、只给 config.txt。

| 键 | 取值 | 语义 |
|----|------|------|
| `cooldown` | yes/no | 总开关 |
| `percent` | 80 / 50 | 冷却保留百分比（按各自原值） |
| `red` | off/no, yes, both, orbital, eagle | 红战备族；`orbital=` / `eagle=` 写在**后面**可细分到某一系 |
| `orbital` | yes/no | 只控制 ORBITAL.* |
| `eagle` | yes/no | 只控制 EAGLE.*（含返回补给 REARM） |
| `blue` | off/no, yes, vehicles, mechs, both, all | 蓝战备；单词形式直接给出范围 |
| `blue_scope` | vehicles/mechs/both/all | 等价写法（与 `blue=yes` 搭配） |
| `green` | yes/no | 哨戒/炮台/地雷/特斯拉/护盾 |
| `uses_add` | 0..3 | 有限次数战备 +N（机甲、轨道激光等；飞鹰除外） |
| `uses_unlimited` | yes/no | 有限次数写成 -1（真无限） |
| `eagle_uses_add` | 0..3 | 飞鹰专用 +N（飞鹰不要设无限：-1 会被当成“次数耗尽”） |
| `min_cooldown` | 秒 | 低于该值的不改（保护飞鹰 15 秒投放间隔与坦克 6 秒装填） |

分节写法 `[cooldown] [scope] [charges] [eagle]` 与上表语义一致（`mode=none|+1|+2|+3|unlimited`）。

## 验证用例（全部通过，2026-10-04）

1. 默认（80 / 只载具 / 无次数）→ 坦克 624、FRV 384，其余不变
2. 50% + 红蓝绿全开 + 无限 + 飞鹰+2 → 坦克 390、FRV 240、机甲 210、机甲/激光 -1、飞鹰 4、地雷 60、REARM 75
3. 只轨道（`red=yes` + `eagle=no`）→ 轨道激光 240、REARM 150
4. 只飞鹰（`red=yes` + `orbital=no`）→ REARM 120、轨道激光 300
5. `blue=all`（50%）→ 坦克 390、FRV 240、机甲 210
6. 空白机器（无 config、无管理器数据库）→ 与默认一致
7. 无数据库但 INI 全开 → 坦克 390、机甲/激光次数 6、飞鹰 3、地雷 60、REARM 75

## 记录修正

`4b9db9b`（2.4.1）的提交信息声称通过验证，实际当时有两项失败；根因是配置读取器把
`red`/`blue` 当普通布尔处理（`d[k] = v=='yes' or 'true' or 'on'`），于是 `red=yes`
不会打开 orbital/eagle 子项、`blue=all` 反而把 blue 置为 false。2.4.2 已修正，本文件
记录的是修正后实测（沙箱）通过的语义。

## 分节 INI 与平铺写法一致性（2026-10-04 复验）

修好 `red`/`blue` 的组语义后，分节写法与平铺写法逐项对比，结果一致：

| 写法 | 结果 |
|------|------|
| `[cooldown] percent=50` + `[scope] red=both blue=all green=on` + `[charges] mode=unlimited` + `[eagle] mode=+2` | 与平铺写法完全相同（坦克 390、FRV 240、机甲 210、机甲/激光 -1、飞鹰 4、地雷 60、REARM 75）|
| `[scope] red=orbital` | 轨道激光 240、REARM 150 |
| `[scope] red=eagle` | REARM 120、轨道激光 300 |
| `[scope] blue=mechs` | 机甲 210，坦克/FRV 不变 |
| `[scope] blue=all` + 平铺 `percent=50 uses_add=2` | 混合写法可用（坦克 390、机甲/激光 +2、地雷 60）|

注意：同一行同时被两种写法覆盖时是“后面的行生效”，因此要把 `orbital=` / `eagle=` 写在 `red=` 之后。

## 空白机器自洽性（2026-10-04）

第一局完全没有 `config.txt`：模组用内置保守默认（只载具 80%、次数不添加）并**自动写出**一份
带注释的 config.txt；第二局读取这份自动生成的文件，结果与第一局**逐项相同**（坦克 624、FRV 384、
机甲/轨道/飞鹰/地雷/次数全部原版）。因此新装用户第一次启动与之后的启动不会漂移。

## 与旧 Arsenal 勾选的兼容（2026-10-04）

2.4.3 的包只提供一个 `Include: ["Addon"]` 选项（通用布局），但读取器是**按块名匹配数据库**的，
所以用旧包建立的六块勾选仍然生效。用玩家真实 `hd2a_data.json` 验证：把 2.4.3 payload 与那份
数据库一起跑，`blocks(from manager DB)` 正常解析出红/蓝/绿/冷却/次数/飞鹰各轴，写入结果与勾选一致；
没有 config.txt 时也不会回退成“全类别 50%”。config.txt 里未注释的键优先级更高。
