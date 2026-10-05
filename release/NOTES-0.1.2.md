# v0.1.2 — Maximized STOVE Mouse fix

Fixes Mouse startup rejecting the official STOVE client when both the game and
refresh app are maximized on the same monitor. STOVE can fill a wider client area;
the app now keeps the full game view and maps clicks to that area.

Mouse focus/obstruction checks and screen-verified actions remain enabled.
Google emulator and ADB layout requirements are unchanged.

Download **E7ShopRefresh-0.1.2.zip** and extract the whole ZIP into a new folder.
Back up existing `runtime` settings/history before updating. Mouse mode still
offers an administrator restart when the selected game requires it.

Tested clients remain Google Play Games Developer Emulator and official STOVE.
Other emulators are untested.
