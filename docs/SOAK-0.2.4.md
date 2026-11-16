# 0.2.4 soak test

Run only after the automated checks pass. Each line is one uninterrupted
Background run with a 300-Skystone budget (100 refreshes), mouse parked off the
game. A run passes when it reaches the budget with no stop, and every purchase
in the Activity tab matches what the game shows.

Purchase counts, Skystone and gold totals and start times of live runs are kept
in the local session logs only, not here.

| # | Platform | Client | Window | Result | Notes |
|---|----------|--------|--------|--------|-------|
| 1 | Linux Mint | Steam | windowed | Pass (short) | Low on Skystones, stopped by hand; no stop, one expected "item moved before Buy" recheck; Friendship bought |
| 2 | Windows 11 | Steam | fullscreen | Pass (short) | 0.2.4h: no stop; Mystic and Friendship bought |
| 3 | Windows 11 | Steam | windowed | Pass (short) | 0.2.4h (1778×1000): no stop; one "list did not scroll" redrag and two pointer pauses recovered; Covenant and Friendship bought. An earlier start stopped because the pointer stayed on the game over 10 s (setup) |
| 4 | Windows 11 | STOVE | fullscreen | Pass (short) | 0.2.4h: no stop; Covenant and Friendship bought |
| 5 | Windows 11 | STOVE | windowed | Pass (short) | 0.2.4h (1119×629): first start stopped at 0 refreshes, "Secret Shop screen could not be verified" (title 0.199) after a pointer pause during the page-two scroll settle; one-frame check, fixed in e6c179d (re-read). Rerun: no stop; Friendship bought. 0.2.4i (504a995) rerun: no stop, four pointer pauses recovered. The re-read path was not triggered in that run. A start with the game minimized stopped at once (0×0, "window was resized"), as designed |

On any stop: press Copy report and paste it, and keep the session log. The
app's own wait-and-look-again messages ("waiting for the list to settle and
checking again") are expected and not failures.

Optional after all five pass: one Mouse-mode run on STOVE (nothing may cover
the game), and one run with an item bought by hand before starting.

Optional runs (STOVE windowed 1119×629, build 0.2.4i / 504a995):

- Mouse mode: bought Mystic and Friendship, then stopped at the Covenant Buy
  dialog with "The confirmation kept changing while being read" (no click).
- Background mode: same stop on the same Covenant dialog.
- Cause: the dialog differed between every two captures 70 ms apart for the
  whole 5 s, although its button never moved. Fixed in be36ea7 (a button
  held in place for 1 s counts as settled; text still checked).

Low-budget runs (build 0.2.4l / 27791e7, which has the be36ea7 confirm hold,
the f9d4eaf verified-scroll check and the 27791e7 numeric price compare).
All eight reached their Skystone budget with no stop and no Stop key:

- One Mouse run; Covenant bought.
- One Background run, 1778×1000 windowed; Covenant bought; one "list did not
  scroll" redrag recovered.
- Five Background runs, STOVE 1119×629 windowed; Covenant bought in four;
  one redrag recovered in each of the three longest runs.
- One Background run, 1122×631 windowed; Covenant bought.

This covers the optional Mouse rerun and confirms the Covenant Buy dialog
now reaches Confirm on STOVE windowed.

Full run (0.2.4l, Background, maximized 1920×1009, the size that earlier
stopped at the shop title check): full 300-Skystone budget reached, no stop,
no Stop key, no recovery messages; Covenant and Mystic bought, gold spent
matching the listed prices. Shop title verified on the first look. Whether any
Covenant or Mystic was skipped could only be judged by watching the game; none
was reported. The title match at this size is still marginal (0.873 against
0.90 in the earlier stop), so maximized STOVE stays a known risk, not a fix.
