# Recognition testing with real frames

Fake transports prove the action logic. They cannot show whether recognition
works on what BlueStacks, Google Play Games and native STOVE actually render.
Fixes tuned on one client's screenshot repeatedly broke another, and the game,
wallpapers and display tints (f.lux, Night light) keep changing the picture.
Every candidate therefore runs against a private corpus of real frames before
any live session.

## The corpus

Private runtime evidence, never committed: `.local-state/frame-corpus/`
(or `E7_FRAME_CORPUS`). `frames.json` lists each frame with its client, kind
(`home`, `shop` or `dialog`) and the expected decision:

- `home`: `target_box` around the Secret Shop icon, `null` when the menu is
  hidden or absent, or `"any"` for a transitional frame such as a fade-in.
- `shop`: whether the shop is recognized and which currencies are bought.
  Omitted items must not be bought. `"stop"` accepts a safe stop.
- `dialog`: operation, optional item, and whether the confirmation matches.

Saved failure crops keep their source offset: home-menu crops `[0, 180]`,
dialog crops `[500, 260]`. Labels record what a person sees in the frame,
not what the current code returns.

## Running it

```powershell
.\.local-state\engine-build-venv\Scripts\python.exe check_frame_corpus.py --variants --report .local-state\frame-corpus\last.json
```

`--variants` repeats each frame with a warm night-light tint and f.lux's
strongest candle tint; decisions must not change. Uniform dimming is not a
variant: the game dims the home menu and the shop behind dialogs, and those
checks deliberately reject dimmed controls. `test_e7_frame_corpus.py` runs the same
check inside the normal suite and skips when the corpus is absent.

## Workflow

1. A live failure saves a crop under `mouse-failures/`, or the owner supplies a
   screenshot. Add it to the corpus with the correct label before fixing.
2. Confirm the new frame fails and every existing frame still passes.
3. Fix the cause, preferring measurements from observed controls over fixed
   pixel positions, colours or menu layouts.
4. The whole corpus, with variants, passes. Then build with the standard
   builder and run the package checks.
5. One live session per candidate covering every client in use, with a short
   checklist. Only then start the next candidate.

Coverage still to collect: BlueStacks full frames (home shown and hidden, both
shop pages), Google Play Games home frames, purchased Covenant/Mystic rows,
and confirmation dialogs from each client.
