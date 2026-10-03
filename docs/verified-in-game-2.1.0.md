# Verified in game: 战备冷却 2.1.0 works / 实机验证成功

Date: 2026-10-03. In-mission stratagem list after deploying 战备冷却 2.1.0
(design A: one manager entry, one addon, ticks read from the manager DB):

| Stratagem | Vanilla | Vanilla (s) | Observed (counting down) | Half (s) |
| --- | --- | --- | --- | --- |
| 堡垒 MK XVI / BASTION(TANK) | 13:00 | 780 | 05:56 | 390 |
| 风暴漩涡 / STORM(TANK) | 13:00 | 780 | 05:48 | 390 |
| 补给型快速侦察载具 / FRV (resupply) | 08:00 | 480 | 03:22 | 240 |
| 炮手快速侦察载具 / FRV (gunner) | 08:00 | 480 | 03:41 | 240 |
| 「解放者」外骨骼装甲 / COMBAT WALKER | 07:00 | 420 | 03:09 | 210 |
| 轨道激光炮 / ORBITAL. LASER | 05:00 | 300 | 01:40 | 150 |
| 重新补给 / CONSUMABLES. RESUPPLY | 03:00 | 180 | 01:14 | 90 |

Every entry shows roughly half of its vanilla recharge and keeps counting down,
so the in-mission timer really is driven by the record field at `+0x68` once the
write happens at load. The screenshot is kept as the mod's preview image
(`iconPath`, `dist/战备冷却-preview.png`).

## What had to be true at the same time

1. **Write at load** (`uptime_s=0`, `stable_s=1`). 1.6.0 wrote 120 s in and the
   game had already built its state - the record read 390 while the HUD still
   showed the vanilla time.
2. **One addon per mod entry.** Two attempts showed the loader executes only one
   addon per Arsenal mod (five payloads with distinct names/GUIDs -> only one
   ran; five sharing one name -> same), while 42 addons from other mods run side
   by side. Hence design A: only the cooldown block ships a payload.
3. **Flat option folders.** Arsenal only picks patch files that sit directly
   under an option's Include root (`Options/<block>/<choice>/9ba...patch_0`); an
   extra `Addon/` level produced an empty layer while the DB still said
   "deployed".
4. **Charges live at `+0x50`** (int32, `-1` = unlimited) and are never turned
   into a limit; the Eagle family is paced by `EAGLE. REARM` (150 s), not by the
   15 s strike-delay field, which `min_cooldown=60` protects.

## Manager state

One entry `战备冷却` (5 blocks / 14 choices, library `战备冷却_AR674326`), preview
image set, config overrides still live in
`%LOCALAPPDATA%\CowboyBingus\Helldivers2\VehicleCooldown\config.txt`.
