# v0.2.3 — Waits out a refresh dialog the game ignored

**Fix for "The refresh confirmation was not recognized."** Sometimes the game ignores
a Confirm click, most often right after a purchase that followed a scroll, while
the shop is still busy. The "Use Skystone to refresh?" dialog then stays open, and
the dimmed shop behind it could be taken for the shop. The refresh was counted and
the next Refresh click went into the open dialog, stopping the run.

- The shop now has to be **fully visible**, not dimmed behind a dialog or overlay,
  before a refresh is counted or Refresh is clicked. The app waits for the overlay
  to clear instead of clicking through it.
- Saved recognition images captured while a dialog dimmed the shop are refused,
  and the built-in images are used instead.

Settings and history carry over: extract **E7ShopRefresh-0.2.3.zip** into a fresh
folder and copy `runtime/ShopRefreshGUI.ini`, `runtime/ADBconfig.ini` and
`runtime/ShopRefreshHistory/` from your old folder if you want them.
