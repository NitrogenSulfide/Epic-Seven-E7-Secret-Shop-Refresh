# v0.1.1 — Administrator restart

When Mouse mode targets an elevated game, Start Refresh offers to save settings
and reopen the app through Windows' administrator prompt. Accept that prompt,
select your game and press Start Refresh again. No session starts automatically.

If you cancel the Windows prompt or restarting fails, the original app stays open
with retry instructions. ADB and non-elevated games continue to open normally.
This checks the selected process; it does not assume all STOVE installations need
administrator permission.

Extract the entire player ZIP into a new folder. Back up your existing `runtime`
settings and history before updating. Python is included. Testing remains limited
to Google Play Games on PC Developer Emulator and native STOVE, as described in
v0.1.0; this update changes startup permission handling.
