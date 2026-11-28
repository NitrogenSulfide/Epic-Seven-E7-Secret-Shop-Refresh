# v0.2.8 (beta) — User folder, Gold budget and Brazilian Portuguese

> ⚠️ **Beta, only tested on my own PCs.** Steam (Windows 11 and Linux), the STOVE client and Google Play Games Developer Emulator work for me. Other PCs, emulators and settings may hit edge cases I haven't seen. Start with a small Skystone budget, and if something breaks, report it on [GitHub Issues](https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh/issues) or Reddit with Copy report.

**Settings and history in your user folder.** Settings and history now live in `%LOCALAPPDATA%\E7 Secret Shop Refresh` (`~/.local/share/e7-shop-refresh` on Linux; set `E7_DATA_DIR` to change it), so future updates keep them. On first start, the app checks next to the new folder, Desktop and Downloads for an older version to import, or you can pick a folder, start fresh, or import later under Settings > Advanced. The old folder is never changed. A backup stays in the `legacy-backup` folder inside the new user folder. Captures and diagnostic logs stay in the app folder. Still no auto-updater; this is the first step towards one.

**Gold budget.** Contributed by Gabriel (Fish7w7). An optional box with a gold coin icon sets the most gold to spend in one session. Leave it blank (it shows a grey "No limit") for no limit. The app stops before a purchase that would go over the budget. Before each refresh, it also checks that the cheapest item you chose to buy still fits in what is left. If not, it stops instead of refreshing. Either stop is a normal "Stopped" with the end sound.

**Brazilian Portuguese (PT-BR).** Translated by Gabriel (Fish7w7). The screens, buttons, settings, and messages are now in Brazilian Portuguese. So are the progress and pause messages in the Activity log and status line. Some stop and error messages are still in English for now. Switch languages with the globe button in the header. The app asks to restart and keeps your settings. Windows may ask for administrator permission again. Logs, Copy report, Diagnostics, and history exports stay in English, and Epic Seven must still be in English.

**Simpler budget boxes.** Skystone budget (up to 99,999) and Gold budget (up to 999,999,999) are now plain number boxes. The 150/300/1,000/3,000 presets and slider from 0.2.7 are gone. The line underneath still shows refreshes, expected Covenant and Mystic buys and gold needed.

**Restart fix.** Fixed a bug where restarting the app twice in a row (for example, changing language twice) could fail with a Python error.

**Upgrading.** Extract `E7ShopRefresh-0.2.8.zip` into a fresh folder and run it, then accept the import prompt on first start to bring over your old settings and history.
