"""Visible Windows game implementation of the shared shop refresh loop."""
import argparse
import json
import math
import random
import re
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
import cv2
import numpy as np
from PIL import Image
from E7ADBShopRefresh import E7ADBShopRefresh, E7Inventory, E7Item
from e7_native_mouse import WindowsMouse, MouseStopped
from e7_windows_capture import GameWindow, game_view
from e7_mouse_confirmation import read_confirmation_text, read_ui_text, confirmation_matches
from e7_shop_navigation import create_navigator


def home_menu_target(result,rgb=None):
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
    if len(choices)!=1:
        return None
    return home_icon_target(rgb,choices[0]) if rgb is not None else choices[0]


def home_icon_target(rgb,caption):
    # Native STOVE captions are not the icon's clickable surface. Use the OCR
    # caption only to find the observed bright icon directly above it.
    x,y=caption
    left,top=max(0,round(x-55)),max(0,round(y-90))
    crop=rgb[top:round(y-18),left:round(x+55)]
    if not crop.size:
        return None
    mask=np.where((crop.min(axis=2)>170)&(crop.max(axis=2).astype(int)-crop.min(axis=2)<65),255,0).astype('uint8')
    count,_,stats,_=cv2.connectedComponentsWithStats(mask)
    components=[(cx,cy,width,height) for cx,cy,width,height,area in stats[1:count] if area>=12]
    if not 2<=len(components)<=8:
        return None
    x1=min(box[0] for box in components);y1=min(box[1] for box in components)
    x2=max(box[0]+box[2] for box in components);y2=max(box[1]+box[3] for box in components)
    if not (30<=x2-x1<=100 and 30<=y2-y1<=72):
        return None
    return left+(x1+x2)/2,top+(y1+y2)/2


def hidden_home_matches(frame, reference=None):
    """A private known home view permits one click to reveal hidden controls."""
    references = (reference,) if reference is not None else (
        Path('adb-assets/native-home/hidden.png'),Path('adb-assets/native-home/google-hidden.png'))
    for reference in references:
        if not reference.is_file():
            continue
        saved = cv2.imdecode(np.frombuffer(reference.read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
        if saved is None:
            continue
        saved = cv2.resize(saved,(1920,1080),interpolation=cv2.INTER_AREA)
        difference = cv2.absdiff(frame,saved)
        if float(difference.mean()) <= 10 and float(np.quantile(difference,.95)) <= 28:
            return True
        if reframed_home_matches(frame, saved):
            return True
    return False


def reframed_home_matches(frame, saved):
    """Recognize the same private home artwork after STOVE reframes its width.

    Feature agreement establishes alignment, not permission to click: most of
    the aligned image must still match in brightness, including any dialog area.
    This rejects a popup laid over otherwise recognizable home artwork.
    """
    size = (960, 540)
    current = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    reference = cv2.resize(saved, size, interpolation=cv2.INTER_AREA)
    orb = cv2.ORB_create(nfeatures=2500)
    a, da = orb.detectAndCompute(reference, None)
    b, db = orb.detectAndCompute(current, None)
    if da is None or db is None or len(a) < 60 or len(b) < 60:
        return False
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    matches = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .7*pair[1].distance]
    if len(matches) < 60:
        return False
    source = np.float32([a[match.queryIdx].pt for match in matches])
    target = np.float32([b[match.trainIdx].pt for match in matches])
    matrix, inliers = cv2.estimateAffine2D(source, target, method=cv2.RANSAC, ransacReprojThreshold=3)
    if matrix is None or inliers is None or inliers.sum() < 60 or inliers.mean() < .75:
        return False
    if not (.75 <= matrix[0,0] <= 1.35 and .85 <= matrix[1,1] <= 1.15
            and abs(matrix[0,1]) <= .01 and abs(matrix[1,0]) <= .01
            and abs(matrix[0,2]) <= size[0]*.20 and abs(matrix[1,2]) <= size[1]*.12):
        return False
    spread = np.ptp(target[inliers.ravel().astype(bool)], axis=0)
    if spread[0] < size[0]*.55 or spread[1] < size[1]*.55:
        return False
    aligned = cv2.warpAffine(reference, matrix, size)
    valid = cv2.warpAffine(np.full_like(reference, 255), matrix, size) > 254
    if valid.mean() < .85:
        return False
    difference = cv2.absdiff(current, aligned)[valid]
    return bool(difference.mean() <= 10 and np.quantile(difference, .95) <= 28)


class IncompleteCurrencyRow(MouseStopped):
    pass


def currency_button(result, boxes, item_name):
    """Associate native summon name, gold price and Buy text on one row."""
    expected = {'Covenant bookmark':('covenant','bookmark','184000'),
                'Mystic medal':('mystic','medal','280000')}
    if item_name not in expected:
        return None
    prefix,noun,price = expected[item_name]
    words = [(re.sub(r'[^a-z0-9]','',word['text'].lower()),tuple(word['box']))
             for word in result.get('words',[])]
    middle = lambda box:(box[1]+box[3])/2
    names = [(text,box) for text,box in words if 1010<=box[0]<box[2]<=1480
             and text in (prefix,prefix+noun,prefix+noun+'s')]
    if not names:
        return None
    if len(names)!=1:
        raise MouseStopped(f'The {item_name} rows are ambiguous. Stopped before scrolling or refreshing.')
    text,name = names[0]; y = middle(name)
    suffixes = [box for word,box in words if word in (noun,noun+'s')
                and name[2]<=box[0]<=name[2]+60 and box[2]<=1480 and abs(middle(box)-y)<=20]
    complete = text!=prefix or len(suffixes)==1
    row_words = [word for word,box in sorted(words,key=lambda pair:pair[1][0])
                 if 1010<=box[0]<box[2]<=1480 and y+15<middle(box)<y+85]
    unavailable = complete and re.search(r'\bsold\s*out\b|\bpurchased\b|\bonly\s+0\s+available\b',' '.join(row_words))
    summons = [box for word,box in words if word=='summon' and 1010<=box[0]<box[2]<=1480
               and 25<=y-middle(box)<=80]
    prices = [box for word,box in words if word==price and 1480<=box[0]<box[2]<=1880
              and -80<=middle(box)-y<=10]
    buys = [(label,button) for word,label in words if word=='buy'
            for button in boxes if button[0]<=label[0]<label[2]<=button[2]
            and button[1]<=label[1]<label[3]<=button[3] and 0<=middle(label)-y<=90]
    if unavailable and not buys:
        return None
    if complete and len(summons)==len(prices)==len(buys)==1:
        label,button = buys[0]
        if 40<=middle(label)-middle(prices[0])<=125:
            return label
    if not buys and name[3]+70>1080:
        raise IncompleteCurrencyRow(f'The {item_name} row is partly offscreen. Stopped before refreshing; expose its full Buy button.')
    raise MouseStopped(f'The {item_name} name was recognized, but its price and Buy button could not be verified on the same row. Stopped before scrolling or refreshing.')


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
    choices = [box for box in green_buttons(rgb,(800,400,1450,1000))
               if (box[0]+box[2])/2 >= 1020]
    if len(choices)==1:
        return choices[0]
    if choices:
        return None
    # Native STOVE uses a blue Confirm button. Locate its label rather than
    # assuming the green ADB skin; require a paired left-hand Cancel label.
    result=read_ui_text(rgb,(500,260,1450,950))
    confirms=[word['box'] for word in result.get('words',[]) if word['text'].lower()=='confirm']
    cancels=[word['box'] for word in result.get('words',[]) if word['text'].lower()=='cancel']
    if len(confirms)!=1 or len(cancels)!=1:
        return None
    confirm,cancel=confirms[0],cancels[0]
    if (1000<=confirm[0]<confirm[2]<=1350 and 500<=confirm[1]<confirm[3]<=930
            and cancel[2]<confirm[0] and abs(cancel[1]-confirm[1])<25
            and 15<=confirm[3]-confirm[1]<=60 and 50<=confirm[2]-confirm[0]<=180):
        return tuple(confirm)
    return None


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

    def request_stop(self):
        self._stop_requested.set()
        self.loop_active = False

    def start(self):
        if not self._stop_requested.is_set():
            super().start()

    def checkScreenDimension(self):
        # Capture the actual client and normalize only the recognition frame.
        self.takeScreenshot()

    def takeScreenshot(self):
        revision = getattr(self.mouse,'pause_revision',None)
        image = self.mouse.screenshot().resize((1920,1080),Image.Resampling.LANCZOS)
        self._capture_resumed = isinstance(revision,int) and revision != self.mouse.pause_revision
        self._rgb = np.asarray(image)
        return cv2.cvtColor(self._rgb,cv2.COLOR_RGB2GRAY)

    def tap(self,x,y):
        self.mouse.click(x,y)

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
                target = home_menu_target(result,self._rgb)
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
            known_home = hidden_home_matches(frame)
            if not moved and known_home:
                # Reveal idle controls only after recognizing a known home.
                self.mouse.move(960,540)
                moved = True
                time.sleep(.5)
                continue
            if not revealed and known_home:
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
            frame = self.takeScreenshot()
            if self._capture_resumed:
                deadline = time.monotonic()+8
            if self.navigation.shop_visible(frame):
                print('Navigation: Secret Shop screen verified.',flush=True)
                return True
        if not self.loop_active:
            return False
        raise MouseStopped('The Secret Shop did not open after selecting its menu. No refresh or purchase sent.')

    def findItemPosition(self,frame,template):
        if not self.loop_active:
            return None
        # A preceding purchase may have updated _rgb since the shared loop's
        # initial grayscale frame. Always inspect the latest captured image.
        region = cv2.cvtColor(self._rgb,cv2.COLOR_RGB2GRAY)[110:1080,760:1030]
        item_name = next((name for name,item in self.storage.inventory.items() if item.image is template),None)
        best = None
        for scale in np.linspace(.65,1.45,17):
            item = cv2.resize(template,None,fx=float(scale),fy=float(scale),interpolation=cv2.INTER_LINEAR)
            if item.shape[0] >= region.shape[0] or item.shape[1] >= region.shape[1]:
                continue
            _,score,_,(_,y) = cv2.minMaxLoc(cv2.matchTemplate(region,item,cv2.TM_CCOEFF_NORMED))
            if score >= .90 and (best is None or score > best[0]):
                best = (score,y+110+item.shape[0]/2)
        boxes = green_buttons(self._rgb,(1480,110,1880,1080))
        choices = [] if best is None else sorted((abs((box[1]+box[3])/2-best[1]),box) for box in boxes)
        if choices and choices[0][0]<=90 and (len(choices)==1 or choices[1][0]-choices[0][0]>=15):
            box = choices[0][1]
            # The left stock-count inset can ignore clicks in the native skin.
            # Keep icon-based purchases within the observed button's right side.
            width,height = box[2]-box[0],box[3]-box[1]
            box = (box[0]+round(width*.55),box[1]+round(height*.2),
                   box[2]-round(width*.08),box[3]-round(height*.2))
            method = 'icon'
        else:
            if item_name not in ('Covenant bookmark','Mystic medal'):
                return None
            if getattr(self,'_shop_ocr_source',None) is not self._rgb:
                self._shop_ocr = read_ui_text(self._rgb,(1010,110,1880,1080))
                self._shop_ocr_source = self._rgb
            if not self.loop_active:
                return None
            try:
                box = currency_button(self._shop_ocr,boxes,item_name)
            except IncompleteCurrencyRow:
                if getattr(self,'_scan_page',2)==1:
                    return None
                raise
            if box is None:
                return None
            method = 'name-price'
        self._item = template
        self._item_name = item_name
        self._item_button = box
        point = ((box[0]+box[2])/2,(box[1]+box[3])/2)
        self._item_method = method
        if not getattr(self,'_quiet_items',False):
            print('E7GUI_MOUSE_ITEM '+json.dumps(dict(item=item_name,method=method,buy=list(point))),flush=True)
        return point

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
            time.sleep(self.generateTapDelay())
            if not self.loop_active:
                return False
            self.takeScreenshot()
            if self._capture_resumed:
                deadline = time.monotonic()+5
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
            saved = self._save_confirmation_failure(operation,before)
            detail = ' A private dialog crop was saved for diagnosis.' if saved else ''
            raise MouseStopped(f'The {operation} confirmation was not recognized. No confirmation click sent.'+detail)
        deadline = time.monotonic()+5
        while self.loop_active and time.monotonic()<deadline:
            time.sleep(self.generateTapDelay())
            if not self.loop_active:
                return False
            frame = self.takeScreenshot()
            if self._capture_resumed:
                deadline = time.monotonic()+5
            if confirmation_button(self._rgb,operation,before) is None and self.navigation.shop_visible(frame):
                return True
        if not self.loop_active:
            return False
        raise MouseStopped('The shop did not return after confirmation. Stopped before another action.')

    def _save_confirmation_failure(self,operation,before):
        # Keep only central game crops, excluding the account/currency header.
        # These private runtime files are never part of the release package.
        try:
            folder = Path('mouse-failures')/uuid.uuid4().hex
            folder.mkdir(parents=True)
            Image.fromarray(before[260:1000,500:1450]).save(folder/'before.png')
            Image.fromarray(self._rgb[260:1000,500:1450]).save(folder/'dialog.png')
            (folder/'failure.json').write_text(json.dumps(dict(operation=operation,
                confirmation_clicked=False,normalized_size=[1920,1080])),encoding='utf-8')
            return True
        except OSError:
            return False

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
        # Name/price recognition uses the observed Buy label to keep random
        # clicks away from the native button's separate stock-count inset.
        self._click_button(self._item_button)
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
        x,y = points[0]
        # Limit the vertical search to the recognized label: native background
        # artwork can join the green mask above the actual Refresh button.
        region = (120,max(890,round(y)-55),650,min(1080,round(y)+55))
        boxes = [box for box in green_buttons(self._rgb,region)
                 if box[0] < x < box[2] and box[1] < y < box[3]]
        if len(boxes) == 1:
            dx,dy = self.generateOffset()
            # Refresh gets a smaller offset than Buy. Keep the recognized label
            # as the anchor and stay inside the observed green button.
            box = boxes[0]
            margin_x = min(14,(x-box[0])/2,(box[2]-x)/2)
            margin_y = min(7,(y-box[1])/2,(box[3]-y)/2)
            x += max(-margin_x,min(margin_x,dx*.2))
            y += max(-margin_y,min(margin_y,dy*.28))
        self.tap(x,y)
        return self._confirm('refresh',before)


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
    args = parser.parse_args(arguments)
    if not math.isfinite(args.budget) or args.budget < 3 or not math.isfinite(args.delay) or args.delay < 0:
        parser.error('Invalid budget or delay')
    if args.tap_jitter is not None and (not math.isfinite(args.tap_jitter) or not 0 <= args.tap_jitter <= .1):
        parser.error('Timing variation must be between 0 and 0.10 seconds.')
    if args.stop_key != 'esc' and (len(args.stop_key)!=1 or args.stop_key not in "0123456789abcdefghijklmnopqrstuvwxyz/.,';[]`"):
        parser.error('Invalid Stop key')
    app = None; started = time.time()
    try:
        data = json.loads(args.mouse_session)
        target = GameWindow(int(data['handle']),int(data['pid']),str(data['title']),tuple(data['rectangle']))
        app = E7MouseShopRefresh(target,budget=args.budget,tap_sleep=args.delay,
                                stop_refresh_key=args.stop_key,random_offset=args.random_offset=='yes',debug=False,tap_jitter=args.tap_jitter)
        if sys.stdin is not None:
            threading.Thread(target=listen_for_stop,args=(sys.stdin,app),daemon=True).start()
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


def listen_for_stop(stream,app):
    """The owning GUI sends STOP before falling back to job termination."""
    try:
        for line in stream:
            if line.strip() == 'STOP':
                break
        app.request_stop()  # EOF also means the controlling GUI went away.
    except (OSError,ValueError):
        app.request_stop()
