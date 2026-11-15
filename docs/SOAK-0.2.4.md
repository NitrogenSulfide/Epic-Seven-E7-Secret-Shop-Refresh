# 0.2.4 soak test

Run only after the automated checks pass. Each line is one uninterrupted
Background run with a 300-Skystone budget (100 refreshes), mouse parked off the
game. A run passes when it reaches the budget with no stop, and every purchase
in the Activity tab matches what the game shows.

| # | Platform | Client | Window | Result | Notes |
|---|----------|--------|--------|--------|-------|
| 1 | Linux Mint | Steam | windowed (as used on 2026-11-14) | Pass (short) | 2026-11-14: 20 refreshes / 60 Skystones (low on Skystones), stopped by hand; no stop, one expected "item moved before Buy" recheck; 15 Friendship bought |
| 2 | Windows 11 | Steam | fullscreen | | |
| 3 | Windows 11 | Steam | windowed | | |
| 4 | Windows 11 | STOVE | fullscreen | | |
| 5 | Windows 11 | STOVE | windowed | | |

On any stop: press Copy report and paste it, and keep the session log. The
app's own wait-and-look-again messages ("waiting for the list to settle and
checking again") are expected and not failures.

Optional after all five pass: one Mouse-mode run on STOVE (nothing may cover
the game), and one run with an item bought by hand before starting.
