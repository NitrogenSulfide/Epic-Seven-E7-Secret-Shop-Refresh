"""Check saved real game frames against labelled expectations; never sends input.

The corpus is private runtime evidence kept outside Git (default
.local-state/frame-corpus). Its frames.json lists entries such as:

  {"file": "stove/home-01.png", "client": "stove", "kind": "home",
   "expect": {"target_box": [40, 470, 130, 540]}}
  {"file": "gpg/shop-01.png", "client": "gpg", "kind": "shop",
   "expect": {"shop": true, "items": {"Friendship points": "none"}}}
  {"file": "gpg/dialog-01.png", "client": "gpg", "kind": "dialog",
   "offset": [500, 260], "expect": {"operation": "buy",
   "item": "Covenant bookmark", "matches": true}}

Full frames are normalized like live captures. Saved failure crops carry the
offset they were cut from and are placed back on a blank 1920x1080 frame.
Items omitted from a shop expectation must not be bought.
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from E7ADBShopRefresh import E7Inventory, E7Item
from e7_frame import game_view
from e7_mouse_confirmation import confirmation_matches, read_confirmation_text, read_ui_text
from e7_mouse_refresh import E7MouseShopRefresh
from e7_native_mouse import MouseStopped
from e7_shop_flow import home_menu_target, native_home_control_target
from e7_shop_navigation import create_navigator

ITEMS = ('Covenant bookmark', 'Mystic medal', 'Friendship points')


def load_frame(path, offset=None):
    with Image.open(path) as image:
        image = image.convert('RGB')
        if offset is None:
            image, _ = game_view(image)
            return np.asarray(image.resize((1920, 1080), Image.Resampling.LANCZOS))
        crop = np.asarray(image)
    rgb = np.zeros((1080, 1920, 3), dtype=np.uint8)
    x, y = offset
    rgb[y:y+crop.shape[0], x:x+crop.shape[1]] = crop[:1080-y, :1920-x]
    return rgb


def home_target(rgb):
    # Live order without personal references: grouped controls, then caption.
    target = native_home_control_target(rgb)
    if target is None:
        target = home_menu_target(read_ui_text(rgb, (0, 180, 420, 920)), rgb)
    return None if target is None else [round(float(v), 1) for v in target]


def shop_outcomes(rgb, assets):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    try:
        create_navigator(assets).require_shop(gray)
        shop = True
    except Exception:
        shop = False
    app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
    app.loop_active, app._rgb, app._quiet_items, app._scan_page = True, rgb, True, 2
    app.storage = E7Inventory()
    for filename, name, price in (('cov.png', ITEMS[0], 184000), ('mys.png', ITEMS[1], 280000)):
        template = cv2.imdecode(np.frombuffer((Path(assets)/filename).read_bytes(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        app.storage.inventory[name] = E7Item(template, price)
    app.storage.inventory[ITEMS[2]] = E7Item(price=18000)
    items = {}
    for name, item in app.storage.inventory.items():
        try:
            items[name] = 'none' if app.findItemPosition(gray, item.image) is None else 'buy'
        except MouseStopped as error:
            items[name] = f'stop: {error}'
    return shop, items


# Display tints that must not change any decision: night-light warmth around
# 3400K and f.lux's strongest (candle) setting. Uniform dimming is deliberately
# not a variant: it is indistinguishable from the game's modal dimming, which
# the home and confirmation checks reject on purpose.
VARIANTS = {'original': (1, 1, 1), 'warm': (1, .8, .55), 'candle': (1, .62, .28)}


def check(entry, root, assets, variant='original'):
    rgb = load_frame(root/entry['file'], entry.get('offset'))
    rgb = np.clip(rgb*np.array(VARIANTS[variant]), 0, 255).astype(np.uint8)
    expect, kind = entry['expect'], entry['kind']
    if kind == 'home':
        target = home_target(rgb)
        box = expect.get('target_box')
        # "any": a transitional frame (e.g. menu fading in) where either is safe.
        ok = True if box == 'any' else target is None if box is None else (
            target is not None and box[0] <= target[0] <= box[2] and box[1] <= target[1] <= box[3])
        return ok, dict(target=target)
    if kind == 'shop':
        shop, items = shop_outcomes(rgb, assets)
        wanted = {name: expect.get('items', {}).get(name, 'none') for name in ITEMS}
        ok = shop == expect.get('shop', True) and all(
            items[name] == want or (want == 'stop' and items[name].startswith('stop')) for name, want in wanted.items())
        return ok, dict(shop=shop, items=items)
    if kind == 'dialog':
        text = read_confirmation_text(rgb)
        matches = confirmation_matches(text, expect['operation'], expect.get('item'))
        return matches == expect['matches'], dict(matches=matches, text=text)
    raise ValueError(f'Unknown frame kind: {kind}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--corpus', type=Path, default=Path('.local-state/frame-corpus'))
    parser.add_argument('--assets', default='adb-assets')
    parser.add_argument('--report', type=Path, help='write the JSON results here')
    parser.add_argument('--only', help='check entries whose file contains this text')
    parser.add_argument('--variants', action='store_true', help='also check night-light and candle-tinted copies')
    args = parser.parse_args(argv)
    entries = json.loads((args.corpus/'frames.json').read_text(encoding='utf-8'))
    if args.only:
        entries = [entry for entry in entries if args.only in entry['file']]
    variants = list(VARIANTS) if args.variants else ['original']
    results, failed = [], 0
    for entry in entries:
        for variant in variants:
            try:
                ok, observed = check(entry, args.corpus, args.assets, variant)
            except Exception as error:
                ok, observed = False, dict(error=''.join(traceback.format_exception_only(error)).strip())
            failed += not ok
            results.append(dict(file=entry['file'], client=entry.get('client'), kind=entry['kind'], variant=variant,
                                passed=ok, expect=entry['expect'], observed=observed))
            print(f"{'PASS' if ok else 'FAIL'}  {entry['kind']:6} {entry.get('client', '?'):10} {variant:8} {entry['file']}  {json.dumps(observed)[:150]}", flush=True)
    print(f'{len(results)-failed}/{len(results)} checks passed')
    if args.report:
        args.report.write_text(json.dumps(dict(read_only=True, no_input=True, results=results), indent=2), encoding='utf-8')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
