# v0.2.1 — Background mode for Steam, Linux and faster refreshes

**New in 0.2.1: Background for Steam and STOVE, and it is the default.** Background
mode now also drives the official **STOVE** client on Windows, and new settings start
in it. The Control mode list says who each mode is for: **Background · Steam / STOVE
(recommended)**, **Mouse · emulators, takes over your pointer** and **ADB · emulators**.
If the app finds only an emulator or Google Play Games window, the banner says so and
offers **Switch to Mouse**. If you already use Mouse mode and the app sees Epic Seven on
Steam or STOVE, it suggests **Switch to Background**; nothing changes until you click it.
If your pointer moves over the game during a Background run, a red line in the window and
the compact tracker shows that input is paused and counts down to the automatic stop.
This is the first published 0.2 release and includes everything below, which was
tagged as 0.2.0 but not released on its own.

**Background mode** is a new control mode for Epic Seven on **Steam**, on
Windows 11 and on Linux (Proton). It sends clicks to the game window directly and
reads frames from the window itself, so your mouse pointer and keyboard focus are
never used and other windows may cover the game. You can keep using your PC:
input waits while the pointer is moving over the game and resumes once it has been
still for a second. Steam's E7 runs as administrator on Windows, so the first
start offers the administrator restart. The Stop key works from any window. The
app refuses to start when more than one Epic Seven window is open.

**Linux** runs from source. `e7-shop-refresh-linux.sh` checks system packages
(it prints the install command and never runs sudo), sets up Python in `.venv`,
builds the small input helper, starts the app and can add an app-menu entry. On
Linux the app offers Background mode only. The Stop key needs an X11 session;
Wayland is refused for now.

**Faster refreshes in Background and Mouse.** Waits now end as soon as the screen
shows the expected state, and the old fixed times remain as upper limits. The tap
delay is now the minimum gap between clicks, and the final dialog check comes after
it, just before the click. Windows text recognition keeps one reader running
instead of starting one per read. Measured on Windows Steam at 2560 × 1440, a
refresh takes about 5–6.5 seconds, down from about 8.5. ADB keeps its fixed waits.

**Compact tracker.** Once the engine starts, the window shrinks in place to a small
always-on-top bar showing purchases, Skystones spent, time left and a Stop button.
The full window comes back when the session stops, finishes or needs attention, or
from the bar's expand button; Compact in the header shrinks it again. Turn it off with "Compact tracker while running".

Start and end sounds are 10 dB quieter. 0.2.x also includes every 0.1.4 trial
change (rc1–rc9): remaining-time estimates, the global Stop key, optional
Friendship Points purchases, BlueStacks fixes, pre-purchased row recognition and
warm display tint handling. See CHANGELOG.txt for the full list.

**Testing.** On Windows 11 with Steam E7, live Background sessions ran at
3840 × 2019 and 2560 × 1440 (including over Moonlight streaming) and bought
Friendship Points and, at 2560 × 1440 over Moonlight, two Covenant Bookmarks; dry runs passed at 1920 × 1080 and 1280 × 720. On Linux Mint 22
(Cinnamon, X11, Proton Experimental) a live session bought a Covenant Bookmark and
Friendship Points. A Mystic Medal purchase in Background mode, other display
scaling settings, ultrawide windows, other Linux desktops and Wayland are untested.
Mouse mode on STOVE and Google Play Games uses the faster waits too but has not
had a live run since that change, so start it with a small supervised budget.
