# 多管理器兼容：结论与做法 / Multi-manager compatibility

本机实测（读取所有已装模组的文本）得到的通行做法：

1. **打包＝根目录 `Addon/9ba626afa44a3aa3.patch_0` 单一文件布局。**
   README 里写 “import into **Arsenal or HD2MM**” 的模组（Arc-Thrower、Clickable-Scrollbars、
   Bingus Shared Loader、FRV-Anti-Flip …）全都是这个结构；`Options[]` + 每个子选项一个
   目录是 Arsenal 专有用法，HD2MM/手动安装不认。
2. **效果选择＝配置文件，而不是管理器。**
   `HUD Ballistic Trajectory Overlay` 用带分节的 INI；HUDBTO 把自己的 `.ini` 放在游戏 `bin`
   旁边读。配置文件是跨管理器、跨安装方式都成立的通道。
3. **需要多套预设时，发多个独立 ZIP**（TankCooldown v2 的 `Default50` / `CustomConfig`），
   而不是把选择塞进 `Options[]`。
4. **确实要读管理器状态就分别适配**：`MDL - Mod Dynamic Loader` 里同时有
   `scan_arsenal(root)`（读 `hd2a_data.json`）和 `scan_hd2mm(root)` 两套扫描；
   `HD2 SmoothBoot` 也读 `hd2a_data.json`，同时自己写 `modlist.txt`。
5. **游戏内 UI 需要框架**：`ModBindingsMenu`（api 1, version>=2）提供的是按键绑定菜单；
   `Super-Earth-Armory-Forge` 是自绘面板（引擎 300KB+，拦截游戏 UI 绘制）＋网页生成器＋
   分节 INI。没有通用 ImGui/overlay 框架可直接挂。

## 本模组的选择

* 打包：根 `Addon/` 单文件 + 单个 `Include: ["Addon"]` 选项（Arsenal 里显示一个条目，
  HD2MM/手动安装同样能装上）；
* 选择：`config.txt`（`%LOCALAPPDATA%\CowboyBingus\Helldivers2\VehicleCooldown\config.txt`），
  键语义见 `config-keys-verified.md`；随包附带 `config-builder.html` 在浏览器里勾选生成；
* 读管理器数据库只作为**附加**来源（Arsenal 用户勾了就用勾的），读不到时用内置保守默认
  （只载具 80%、次数不添加），不会出现“空白机器上全类别 50%”那种意外；
* 不启动任何进程（目录用 kernel32 `CreateDirectoryA` 创建），空白机器也有日志。

## 踩过的坑（避免重犯）

* `Options[]` 树会让 Arsenal 的条目在下次启动时消失、删不掉，必须强制删目录再导入；
* 选项名撞词：读取器曾按“组名”全文搜索，描述里出现同名词就会截断解析（2.2.1 已改为
  锚定 `"name": "..."` 记录）；
* 哨兵值语义：`+0x50 = -1` 对载具＝无限，对飞鹰＝“次数耗尽等补给”（会让飞鹰显示不可用），
  所以飞鹰只写有限值；
* `-1` 只在游戏本身标记为无限的战备上有效，其它环境需要用有限大值（当前不提供，避免误伤）。
