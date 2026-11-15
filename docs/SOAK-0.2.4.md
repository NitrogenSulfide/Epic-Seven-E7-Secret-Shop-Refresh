# 0.2.4 soak test

Run only after the automated checks pass. Each line is one uninterrupted
Background run with a 300-Skystone budget (100 refreshes), mouse parked off the
game. A run passes when it reaches the budget with no stop, and every purchase
in the Activity tab matches what the game shows.

| # | Platform | Client | Window | Result | Notes |
|---|----------|--------|--------|--------|-------|
| 1 | Linux Mint | Steam | windowed (as used on 2026-11-14) | Pass (short) | 2026-11-14: 20 refreshes / 60 Skystones (low on Skystones), stopped by hand; no stop, one expected "item moved before Buy" recheck; 15 Friendship bought |
| 2 | Windows 11 | Steam | fullscreen | Pass (short) | 0.2.4h, 19:49: 16 refreshes / 48 Skystones, no stop; 1 Mystic, 10 Friendship |
| 3 | Windows 11 | Steam | windowed | Pass (short) | 0.2.4h, 19:53 (1778×1000): 16 refreshes / 48 Skystones, no stop; one "list did not scroll" redrag and two pointer pauses recovered; 2 Covenant, 8 Friendship. A 19:50 start stopped because the pointer stayed on the game over 10 s (setup) |
| 4 | Windows 11 | STOVE | fullscreen | Pass (short) | 0.2.4h, 19:58: 16 refreshes / 48 Skystones, no stop; 1 Covenant, 11 Friendship |
| 5 | Windows 11 | STOVE | windowed | Pass (short) | 0.2.4h, 20:05 (1119×629): stopped at 0 refreshes, "Secret Shop screen could not be verified" (title 0.199) after a pointer pause during the page-two scroll settle; one-frame check, fixed in e6c179d (re-read). 20:08 rerun: 16 refreshes / 48 Skystones, no stop; 11 Friendship. 0.2.4i (504a995) 20:30 rerun: 16 refreshes / 48 Skystones, no stop, four pointer pauses recovered; 8 Friendship. The re-read path was not triggered in that run. A 20:27 start stopped at once with the game minimized (0×0, "window was resized"), as designed |

On any stop: press Copy report and paste it, and keep the session log. The
app's own wait-and-look-again messages ("waiting for the list to settle and
checking again") are expected and not failures.

Optional after all five pass: one Mouse-mode run on STOVE (nothing may cover
the game), and one run with an item bought by hand before starting.

Optional runs, 2026-11-14 (Orlando, STOVE windowed 1119×629, build 0.2.4i / 504a995):

- Mouse mode: bought Mystic and Friendship, then stopped at the Covenant Buy
  dialog with "The confirmation kept changing while being read" (no click).
- Background mode: same stop on the same Covenant dialog.
- Cause: the dialog differed between every two captures 70 ms apart for the
  whole 5 s, although its button never moved. Fixed in be36ea7 (a button
  held in place for 1 s counts as settled; text still checked). Rerun both
  with 0.2.4j (be36ea7) pending.
