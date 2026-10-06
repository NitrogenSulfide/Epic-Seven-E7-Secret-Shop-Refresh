"""Visible Windows game implementation of the shared shop refresh loop."""
import argparse
import json
import math
import random
from pathlib import Path
import subprocess
import sys
import threading
import time
import cv2
import numpy as np
from PIL import Image
from E7ADBShopRefresh import E7ADBShopRefresh, E7Inventory, E7Item
from e7_native_mouse import WindowsMouse, MouseStopped, MouseRecheckRequired
from e7_windows_capture import GameWindow, game_view
from e7_frame import normalize_game_frame
from e7_mouse_confirmation import read_confirmation_text, read_ui_text, confirmation_matches
from e7_shop_navigation import create_navigator
from e7_timing import validate_timing
from e7_session_control import listen_for_stop


from e7_shop_flow import (home_menu_target,home_icon_target,native_home_control_target,hidden_home_matches,
    reframed_home_matches,idle_home_candidate,IncompleteCurrencyRow,currency_button,green_buttons,
    confirmation_button,recheck_mouse_action)


class E7MouseShopRefresh(E7ADBShopRefresh):
    def __init__(self, target, *, transport=None, **settings):
        if settings.get('debug'):
            raise ValueError('Mouse mode uses normal settings. Debug/calibration remains available in ADB mode.')
        self._stop_requested = threading.Event()
        self.mouse = transport or WindowsMouse(target,lambda:self.loop_active and not self._stop_requested.is_set())
        self._rgb = None
        self._item = None
        self._item_name = None
        self.read_confirmation_text = read_confirmation_text
        self.read_navigation_text = lambda rgb:read_ui_text(rgb,(0,180,420,920))
        super().__init__(**settings)
        self._session_metadata['Control mode'] = 'Mouse'


    def checkScreenDimension(self):
        # Capture the actual client and normalize only the recognition frame.
        self.takeScreenshot()


    def takeScreenshot(self):
        revision = getattr(self.mouse,'pause_revision',None)
        image = self.mouse.screenshot()
        self._capture_resumed = isinstance(revision,int) and revision != self.mouse.pause_revision
        self._rgb,_ = normalize_game_frame(image,bounds=(0,0,image.width,image.height),
                                          native_stove=getattr(self.mouse,'native_stove',False) is True)
        return cv2.cvtColor(self._rgb,cv2.COLOR_RGB2GRAY)


    def tap(self,x,y):
        return self.mouse.click(x,y)


    @recheck_mouse_action
    def swipe(self,x1,y1,x2,y2):
        varied = self.random_offset
        duration = random.uniform(.28,.36) if varied else .32
        drift = random.uniform(-3,3) if varied else 0
        # Preserve the original vertical travel so page-two scanning covers the
        # same items. Only position, slight sideways drift and timing vary.
        self.mouse.drag(x1,y1,x2+drift,y2,duration=duration)


    def generateSwipeOffset(self):
        dx,dy = self.generateOffset()
        return max(-12,min(12,dx*.16)),max(-6,min(6,dy*.24))


def inspect_mouse_items(path,assets='adb-assets'):
    """Exercise the live purchase detector on a saved client image only."""
    with Image.open(path) as image:
        if image.width<640 or image.height<360:
            raise ValueError('Use a game-client screenshot at least 640 × 360 pixels.')
        image,_ = game_view(image.convert('RGB'))
        rgb = np.asarray(image.resize((1920,1080),Image.Resampling.LANCZOS))
    frame = cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    create_navigator(assets).require_shop(frame)
    app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
    app.loop_active,app._rgb,app._quiet_items = True,rgb,True
    app.storage = E7Inventory()
    for filename,name,price in (('cov.png','Covenant bookmark',184000),('mys.png','Mystic medal',280000)):
        template = cv2.imdecode(np.frombuffer((Path(assets)/filename).read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise ValueError('A currency item template is missing or unreadable.')
        app.storage.inventory[name] = E7Item(template,price)
    items = []
    for name,item in app.storage.inventory.items():
        point = app.findItemPosition(frame,item.image)
        if point is not None:
            items.append(dict(item=name,buy=list(point),method=app._item_method,price=item.price))
    return dict(read_only=True,state='shop',items=items)


def run_mouse_session(arguments):
    parser = argparse.ArgumentParser(description='Native STOVE Mouse refresh session; uses the real pointer.')
    parser.add_argument('--mouse-session',required=True,help='selected window JSON')
    parser.add_argument('--budget',type=int,required=True)
    parser.add_argument('--delay',type=float,required=True)
    parser.add_argument('--stop-key',required=True)
    parser.add_argument('--random-offset',choices=('yes','no'),required=True)
    parser.add_argument('--tap-jitter',type=float,default=None)
    parser.add_argument('--trace-input', action='store_true')
    args = parser.parse_args(arguments)
    if not math.isfinite(args.budget) or args.budget < 3:
        parser.error('Invalid budget or delay')
    try:
        validate_timing(args.delay, args.tap_jitter)
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    if args.stop_key != 'esc' and (len(args.stop_key)!=1 or args.stop_key not in "0123456789abcdefghijklmnopqrstuvwxyz/.,';[]`"):
        parser.error('Invalid Stop key')
    app = None; started = time.time()
    try:
        data = json.loads(args.mouse_session)
        target = GameWindow(int(data['handle']),int(data['pid']),str(data['title']),tuple(data['rectangle']))
        app = E7MouseShopRefresh(target,budget=args.budget,tap_sleep=args.delay,
                                stop_refresh_key=args.stop_key,random_offset=args.random_offset=='yes',debug=False,tap_jitter=args.tap_jitter,
                                trace_input=data.get('trace_input', args.trace_input))
        if sys.stdin is not None:
            threading.Thread(target=listen_for_stop,args=(sys.stdin,app),daemon=True).start()
        if app.input_trace.enabled:
            print('E7GUI_TRACE_READY', flush=True)
        print('E7GUI_STARTED',flush=True)
        app.start()
        return 0
    except MouseStopped as error:
        print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason':str(error)}),flush=True)
        if app is not None:
            app.reportLiveStats()
            app.record_session('failed', str(error))
            app.printResult()
        return 0
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as error:
        print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason':f'Mouse session stopped. {error}'}),flush=True)
        return 3
