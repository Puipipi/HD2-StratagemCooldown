# 变更记录 / Changelog

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
