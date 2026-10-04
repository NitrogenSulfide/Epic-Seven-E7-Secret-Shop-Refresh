"""Native STOVE implementation of the shared shop refresh loop."""
import argparse
import json
import math
import re
from pathlib import Path
import subprocess
import time
import cv2
import numpy as np
from PIL import Image
from E7ADBShopRefresh import E7ADBShopRefresh
from e7_native_mouse import WindowsMouse, MouseStopped
from e7_windows_capture import GameWindow
from e7_mouse_confirmation import read_confirmation_text, read_ui_text, confirmation_matches


def home_menu_target(result):
    """Locate the observed home menu text, including rescaled native layouts."""
    if not any(label in result['text'].lower() for label in ('sanctuary','epic pass','event')):
        return None
    words = result.get('words',[])
    choices = []
    for first,second in zip(words,words[1:]):
        if re.sub('[^a-z]','',first['text'].lower()) != 'secret' or not re.fullmatch('sh[o0p]p',re.sub('[^a-z0-9]','',second['text'].lower())):
            continue
        a,b = first['box'],second['box']
        box = (min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3]))
        if 0 <= box[0] < box[2] <= 360 and 210 <= box[1] < box[3] <= 850 and abs(a[1]-b[1]) < 25:
            choices.append(((box[0]+box[2])/2,(box[1]+box[3])/2))
    return choices[0] if len(choices)==1 else None


def hidden_home_matches(frame, reference=Path('adb-assets/native-home/hidden.png')):
    """A private known home view permits one click to reveal hidden controls."""
    if not reference.is_file():
        return False
    saved = cv2.imdecode(np.frombuffer(reference.read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
    if saved is None:
        return False
    saved = cv2.resize(saved,(1920,1080),interpolation=cv2.INTER_AREA)
    difference = cv2.absdiff(frame,saved)
    return float(difference.mean()) <= 10 and float(np.quantile(difference,.95)) <= 28


def green_buttons(rgb, region):
    left,top,right,bottom = region
    hsv = cv2.cvtColor(rgb[top:bottom,left:right],cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv,np.array([30,45,25]),np.array([95,255,255]))
    count,_,stats,_ = cv2.connectedComponentsWithStats(mask)
    boxes = []
    for x,y,width,height,area in stats[1:count]:
        if 100 <= width <= 450 and 35 <= height <= 140 and width/height >= 1.4 and area >= width*height*.35:
            boxes.append((int(left+x),int(top+y),int(left+x+width),int(top+y+height)))
    return boxes


def confirmation_button(rgb, operation, before):
    # Expect the green right-hand action button in a newly opened central dialog.
    # Shop Buy buttons are excluded; a single centered acknowledgement is excluded.
    if np.mean(cv2.absdiff(rgb[300:920,550:1400],before[300:920,550:1400])) < 4:
        return None
    x,y = (1090,760) if operation == 'buy' else (1119,692)
    choices = [box for box in green_buttons(rgb,(850,500,1450,930))
               if box[0] < x < box[2] and box[1] < y < box[3]
               and (box[0]+box[2])/2 >= 1020]
    return choices[0] if len(choices) == 1 else None


class E7MouseShopRefresh(E7ADBShopRefresh):
    def __init__(self, target, *, transport=None, **settings):
        if settings.get('debug'):
            raise ValueError('Mouse mode uses normal settings. Debug/calibration remains available in ADB mode.')
        self.mouse = transport or WindowsMouse(target,lambda:self.loop_active)
        self._rgb = None
        self._item = None
        self._item_name = None
        self.read_confirmation_text = read_confirmation_text
        self.read_navigation_text = lambda rgb:read_ui_text(rgb,(0,180,420,920))
        super().__init__(**settings)

    def checkScreenDimension(self):
        # Capture the actual client and normalize only the recognition frame.
        self.takeScreenshot()

    def takeScreenshot(self):
        image = self.mouse.screenshot().resize((1920,1080),Image.Resampling.LANCZOS)
        self._rgb = np.asarray(image)
        return cv2.cvtColor(self._rgb,cv2.COLOR_RGB2GRAY)

    def tap(self,x,y):
        self.mouse.click(x,y)

    def swipe(self,x1,y1,x2,y2):
        self.mouse.scroll(x1,y1)

    def clickShop(self):
        deadline = time.monotonic()+30
        revealed = moved = False
        while self.loop_active and time.monotonic()<deadline:
            frame = self.takeScreenshot()
            if self.navigation.shop_visible(frame):
                print('Navigation: Secret Shop screen verified; already open.',flush=True)
                return True
            target = self.navigation.menu_target(frame)
            if target is None:
                result = self.read_navigation_text(self._rgb)
                target = home_menu_target(result)
            else:
                result = None
            if not self.loop_active:
                return False
            if target is not None:
                prior = self._rgb.copy()
                self.takeScreenshot()
                if np.mean(cv2.absdiff(prior[180:920,:420],self._rgb[180:920,:420])) > 6:
                    continue
                print('Navigation: Opening the recognized Secret Shop menu.',flush=True)
                self.tap(*target)
                return self._wait_for_shop()
            if not moved:
                # Hover can restore a native client's idle UI without a click.
                self.mouse.move(960,540)
                moved = True
                time.sleep(.5)
                continue
            if not revealed and hidden_home_matches(frame):
                fresh = self.takeScreenshot()
                if hidden_home_matches(fresh):
                    print('Navigation: Revealing the recognized home screen controls.',flush=True)
                    self.tap(960,540)
                    revealed = True
                    time.sleep(.5)
                    continue
            print('Navigation: Looking for the home Secret Shop menu. No shop action sent.',flush=True)
            time.sleep(.5)
        if not self.loop_active:
            return False
        raise MouseStopped('The home Secret Shop menu could not be recognized. Start from the English home screen or an already open Secret Shop.')

    def _wait_for_shop(self):
        deadline = time.monotonic()+8
        while self.loop_active and time.monotonic()<deadline:
            time.sleep(.25)
            if not self.loop_active:
                return False
            if self.navigation.shop_visible(self.takeScreenshot()):
                print('Navigation: Secret Shop screen verified.',flush=True)
                return True
        if not self.loop_active:
            return False
        raise MouseStopped('The Secret Shop did not open after selecting its menu. No refresh or purchase sent.')

    def findItemPosition(self,frame,template):
        region = frame[110:1080,760:1030]
        best = None
        for scale in np.linspace(.65,1.45,17):
            item = cv2.resize(template,None,fx=float(scale),fy=float(scale),interpolation=cv2.INTER_LINEAR)
            if item.shape[0] >= region.shape[0] or item.shape[1] >= region.shape[1]:
                continue
            _,score,_,(_,y) = cv2.minMaxLoc(cv2.matchTemplate(region,item,cv2.TM_CCOEFF_NORMED))
            if score >= .90 and (best is None or score > best[0]):
                best = (score,y+110+item.shape[0]/2)
        if best is None:
            return None
        choices = sorted((abs((box[1]+box[3])/2-best[1]),box)
                         for box in green_buttons(self._rgb,(1480,110,1880,1080)))
        if not choices or choices[0][0] > 140 or (len(choices)>1 and choices[1][0]-choices[0][0] < 15):
            return None
        self._item = template
        self._item_name = next((name for name,item in self.storage.inventory.items() if item.image is template),None)
        box = choices[0][1]
        return ((box[0]+box[2])/2,(box[1]+box[3])/2)

    def _click_button(self,box):
        x,y = (box[0]+box[2])/2,(box[1]+box[3])/2
        dx,dy = self.generateOffset()
        # Preserve randomized offsets, bounded well inside the observed button.
        dx = max(-(box[2]-box[0])/4,min((box[2]-box[0])/4,dx))
        dy = max(-(box[3]-box[1])/4,min((box[3]-box[1])/4,dy))
        self.tap(x+dx,y+dy)

    def _confirm(self,operation,before):
        deadline = time.monotonic()+5
        while self.loop_active and time.monotonic()<deadline:
            time.sleep(self.tap_sleep)
            if not self.loop_active:
                return False
            self.takeScreenshot()
            box = confirmation_button(self._rgb,operation,before)
            if box is not None:
                text = self.read_confirmation_text(self._rgb)
                if not confirmation_matches(text,operation,self._item_name):
                    raise MouseStopped('The confirmation does not match the intended shop action. No confirmation click sent.')
                if not self.loop_active:
                    return False
                # OCR may take time. Re-capture and require the same dialog and
                # action button before input; guard checks Stop/focus once more.
                prior = self._rgb.copy()
                self.takeScreenshot()
                if not self.loop_active:
                    return False
                current = confirmation_button(self._rgb,operation,before)
                if current != box or np.mean(cv2.absdiff(self._rgb[260:950,500:1450],prior[260:950,500:1450])) > 3:
                    raise MouseStopped('The confirmation changed while being read. No confirmation click sent.')
                self._click_button(box)
                break
        else:
            if not self.loop_active:
                return False
            raise MouseStopped(f'The {operation} confirmation was not recognized. No confirmation click sent.')
        deadline = time.monotonic()+5
        while self.loop_active and time.monotonic()<deadline:
            time.sleep(self.tap_sleep)
            if not self.loop_active:
                return False
            frame = self.takeScreenshot()
            if confirmation_button(self._rgb,operation,before) is None and self.navigation.shop_visible(frame):
                return True
        if not self.loop_active:
            return False
        raise MouseStopped('The shop did not return after confirmation. Stopped before another action.')

    def clickBuy(self,pos):
        if pos is None or not self.loop_active or self._item is None:
            return False
        frame = self.takeScreenshot(); self.navigation.require_shop(frame)
        current = self.findItemPosition(frame,self._item)
        if current is None or abs(current[1]-pos[1]) > 20:
            raise MouseStopped('The selected item changed before Buy. No click sent.')
        boxes = [box for box in green_buttons(self._rgb,(1480,110,1880,1080))
                 if box[0] < current[0] < box[2] and box[1] < current[1] < box[3]]
        if len(boxes) != 1:
            raise MouseStopped('The Buy button was not recognized. No click sent.')
        before = self._rgb.copy()
        self._click_button(boxes[0])
        return self._confirm('buy',before)

    def clickRefresh(self):
        if not self.loop_active:
            return False
        frame = self.takeScreenshot(); self.navigation.require_shop(frame)
        points = [match['point'] for _,nav in self.navigation.navigators
                  if nav.shop_visible(frame) and (match:=nav.match(frame,'refresh-label.png'))]
        if not points or any(abs(x-points[0][0])>8 or abs(y-points[0][1])>8 for x,y in points):
            raise MouseStopped('The Refresh target was not recognized. No click sent.')
        before = self._rgb.copy()
        # The recognized label gives the point; this button is not randomized.
        self.tap(*points[0])
        return self._confirm('refresh',before)


def run_mouse_session(arguments):
    parser = argparse.ArgumentParser(description='Native STOVE Mouse refresh session; uses the real pointer.')
    parser.add_argument('--mouse-session',required=True,help='selected window JSON')
    parser.add_argument('--budget',type=float,required=True)
    parser.add_argument('--delay',type=float,required=True)
    parser.add_argument('--stop-key',required=True)
    parser.add_argument('--random-offset',choices=('yes','no'),required=True)
    args = parser.parse_args(arguments)
    if not math.isfinite(args.budget) or args.budget < 3 or not math.isfinite(args.delay) or args.delay < 0:
        parser.error('Invalid budget or delay')
    if args.stop_key != 'esc' and (len(args.stop_key)!=1 or args.stop_key not in "0123456789abcdefghijklmnopqrstuvwxyz/.,';[]`"):
        parser.error('Invalid Stop key')
    app = None; started = time.time()
    try:
        data = json.loads(args.mouse_session)
        target = GameWindow(int(data['handle']),int(data['pid']),str(data['title']),tuple(data['rectangle']))
        app = E7MouseShopRefresh(target,budget=args.budget,tap_sleep=args.delay,
                                stop_refresh_key=args.stop_key,random_offset=args.random_offset=='yes',debug=False)
        print('E7GUI_STARTED',flush=True)
        app.start()
        return 0
    except MouseStopped as error:
        print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason':str(error)}),flush=True)
        if app is not None:
            app.reportLiveStats()
            app.storage.writeToCSV(time.time()-started,app.refresh_count*3)
            app.printResult()
        return 0
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as error:
        print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason':f'Mouse session stopped. {error}'}),flush=True)
        return 3
