# v0.2.2 — Recovers from a passing pointer, clearer compact tracker

**Fixes for Background runs on Steam and STOVE.** Moving the mouse across the game
for a moment could stop a run with "Refresh target was not recognized" or "The
Secret Shop did not open", or leave a Confirm click unsent. 0.2.2 recovers:

- **Refresh label covered for a moment:** the app reads it again for up to 2.5
  seconds instead of stopping. It still clicks Refresh only once.
- **Shop menu click swallowed on the home screen:** the app checks the home screen
  again and reselects the Secret Shop menu (up to 3 tries). The retry now comes
  about 2 seconds after the pointer leaves, instead of a full 8-second wait.
- **Confirm click swallowed:** if the very same dialog is still open and settled,
  the app confirms **once** more. Never twice, never without a pointer pause, and
  never on a dialog that changed.

**Compact tracker says what to do.** A short line under the bar explains what is
happening and the fix, for example *"Leave the mouse still, or park it on the
taskbar. It resumes by itself."*, *"Restore the game window."* or *"Shop didn't open
(click missed) · retrying."* It clears once the shop is recognized.

**Still the best setup:** keep the pointer off the game (another monitor or the
taskbar), never minimize the game, and start from the home screen or the Secret
Shop with no popups open. Settings and history carry over: extract
**E7ShopRefresh-0.2.2.zip** into a fresh folder and copy `runtime/ShopRefreshGUI.ini`,
`runtime/ADBconfig.ini` and `runtime/ShopRefreshHistory/` from your old folder if you
want them.
