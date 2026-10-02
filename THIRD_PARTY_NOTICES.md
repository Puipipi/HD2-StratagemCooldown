# External dependencies / 外部依赖

## Runtime / 运行期

* **Bingus Shared Loader v15+ (API 1)** - required by the addon; not
  redistributed here.
* **Tank Cooldown v2** (third-party, by its original author) - this addon is a
  safe rewrite of that family for all vehicles. The AOB resolver family
  (`49 8B 84 C7 ...` consumer pattern plus the `lea r15` base anchor), the
  StratagemInfo record layout (id at `+0x00`, name pointer at `+0x10`,
  cooldown at `+0x68`, 0xB0-byte record read) and the vehicle identity
  constants used for cross-checking were taken from the third-party build kept
  read-only in the workspace. The third-party source is **not** redistributed
  here; obtain it from its original distribution under its own terms. This
  repository contains no part of it.

## Development / 开发期

* **Lupa / LuaJIT** (`requirements-dev.txt`) - used by the offline sandbox and
  the build validator. Upstream licenses apply.
* **Bingus addon packer** - `work/standalone/build_vc.py` needs the externally
  supplied `build_addon.py` and `archive.py` in
  `work/standalone/vendor/bingus/`. Those third-party implementations are not
  redistributed in this repository (the directory is ignored on purpose);
  obtain them with the appropriate upstream permission. They encode the addon
  envelope format used by the loader.

## Not included / 不包含

This repository contains no game binaries, no other installed mods, no personal
configuration, no raw player logs and no crash dumps. `research/evidence/`
holds derived analysis and the project's **own** previously deployed Lua text
(an artefact of this mod, kept so the failure can be reproduced offline);
`research/private/` is ignored and may hold raw logs and captured evidence
outside version control.

No new license grant for this project's own code is made by this snapshot.
