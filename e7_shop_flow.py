"""Transport-neutral recognition and observed Secret Shop action flow."""
from functools import wraps
import json,math,re,time,uuid
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from e7_native_mouse import MouseStopped,MouseRecheckRequired
from e7_mouse_confirmation import read_ui_text,confirmation_matches

def home_menu_target(result,rgb=None):
    """Locate the observed home menu text, including rescaled native layouts."""
    if not any(label in result.get('text','').lower() for label in ('sanctuary','epic pass','event')):
        return None
    words = result.get('words',[])
    choices = []
    for word in words:
        if re.sub('[^a-z0-9]','',word['text'].lower()) not in ('secretshop','secretsh0p','secretshoo','secretsh0o'):
            continue
        box=word['box']
        if 0 <= box[0] < box[2] <= 360 and 210 <= box[1] < box[3] <= 850:
            choices.append(((box[0]+box[2])/2,(box[1]+box[3])/2))
    for first,second in zip(words,words[1:]):
        # Windows OCR can read the thin descender of native Shop as Shoo.
        # The home context and observed icon are still required for Mouse input.
        if re.sub('[^a-z]','',first['text'].lower()) != 'secret' or not re.fullmatch('sh(?:[o0p]p|[o0]o)',re.sub('[^a-z0-9]','',second['text'].lower())):
            continue
        a,b = first['box'],second['box']
        box = (min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3]))
        if 0 <= box[0] < box[2] <= 360 and 210 <= box[1] < box[3] <= 850 and abs(a[1]-b[1]) < 25:
            choices.append(((box[0]+box[2])/2,(box[1]+box[3])/2))
    if len(choices)!=1:
        return None
    return home_icon_target(rgb,choices[0]) if rgb is not None else choices[0]


def white_balanced(crop):
    """Neutralize a colour cast such as f.lux, Night light or warm lobby light.

    Scales each channel so this region's brightest pixels become white. The
    white UI symbol then keeps its shape and neutral colour; an untinted
    region is essentially unchanged.
    """
    peaks=np.percentile(crop.reshape(-1,3),99.5,axis=0)
    # Only rebalance a region with a bright symbol; never lift a dark region.
    if peaks.max()<170 or peaks.min()<25:
        return crop
    return np.clip(crop.astype(np.float32)*(255/peaks),0,255).astype(np.uint8)


def home_icon_target(rgb,caption):
    # Native STOVE captions are not the icon's clickable surface. Use the OCR
    # caption only to find the observed bright icon directly above it.
    x,y=caption
    left,top=max(0,round(x-55)),max(0,round(y-90))
    crop=rgb[top:round(y-18),left:round(x+55)]
    if not crop.size:
        return None
    crop=white_balanced(crop)
    mask=np.where((crop.min(axis=2)>170)&(crop.max(axis=2).astype(int)-crop.min(axis=2)<65),255,0).astype('uint8')
    # Match only the UI symbol. Bright particles in animated wallpapers can
    # add components around it; they must not enlarge or invalidate its box.
    path=Path('adb-assets/builtin-navigation/native-secret-shop-icon.png')
    if path.is_file():
        template=cv2.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
        best=None
        if template is not None:
            for scale in np.linspace(.8,1.2,9):
                icon=cv2.resize(template,None,fx=float(scale),fy=float(scale),interpolation=cv2.INTER_NEAREST)
                h,w=icon.shape
                if h>mask.shape[0] or w>mask.shape[1]: continue
                scores=cv2.matchTemplate(mask,icon,cv2.TM_CCORR_NORMED)
                _,score,_,point=cv2.minMaxLoc(scores)
                if best is None or score>best[0]:
                    px,py=point;other=scores.copy()
                    other[max(0,py-h//2):py+h//2+1,max(0,px-w//2):px+w//2+1]=-1
                    best=(score,float(other.max()),(left+px+w/2,top+py+h/2))
        if best and best[0]>=.86 and best[1]<best[0]-.08:
            return best[2]
    count,_,stats,_=cv2.connectedComponentsWithStats(mask)
    components=[(cx,cy,width,height) for cx,cy,width,height,area in stats[1:count] if area>=12]
    if not 2<=len(components)<=8:
        return None
    x1=min(box[0] for box in components);y1=min(box[1] for box in components)
    x2=max(box[0]+box[2] for box in components);y2=max(box[1]+box[3] for box in components)
    if not (30<=x2-x1<=100 and 30<=y2-y1<=72):
        return None
    return left+(x1+x2)/2,top+(y1+y2)/2


def native_home_control_target(rgb):
    """Require three visible home symbols in their observed menu layout.

    Glyph edges tolerate artwork behind the controls; foreground brightness
    rejects dimmed/inactive home menus. The shop point is measured from its
    matched icon, not assumed from a wallpaper or fixed coordinate.
    """
    # Brightest channel, not luma: a warm display tint (f.lux) lowers green and
    # blue but keeps white symbols bright, while modal dimming lowers all three.
    gray=np.ascontiguousarray(rgb[180:920,:360].max(axis=2))
    edges=cv2.Canny(gray,45,110)
    distance=cv2.distanceTransform(255-edges,cv2.DIST_L2,3)
    proximity=np.maximum(0,1-distance/2.5).astype('float32')
    candidates={}
    # The third home control rotates between Epic Pass and Event. Require the
    # same three-symbol layout with either observed icon, without depending on
    # OCR of captions over animated artwork.
    for name in ('sanctuary','secret-shop','epic-pass','event'):
        path=Path(f'adb-assets/builtin-navigation/native-{name}-icon.png')
        if not path.is_file():continue
        mask=cv2.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
        if mask is None:continue
        if name=='secret-shop':mask=np.pad(mask,2)
        matches=[]
        for scale in np.linspace(.85,1.15,13):
            icon=cv2.resize(mask,None,fx=float(scale),fy=float(scale),interpolation=cv2.INTER_NEAREST)
            expected=(cv2.Canny(icon,45,110)>0).astype('float32')
            if expected.sum()<40:return None
            h,w=icon.shape
            scores=cv2.matchTemplate(proximity,expected,cv2.TM_CCORR)/expected.sum()
            for _ in range(5):
                _,score,_,(x,y)=cv2.minMaxLoc(scores)
                if score<.75:break
                if gray[y:y+h,x:x+w][icon>170].mean()>=170:
                    matches.append((score,float(scale),(x+w/2,180+y+h/2)))
                scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1]=-1
        candidates[name]=matches
    if not candidates.get('sanctuary') or not candidates.get('secret-shop'):return None
    third=candidates.get('epic-pass',[])+candidates.get('event',[])
    if not third:return None
    groups=[]
    for shop in candidates['secret-shop']:
        for castle in candidates['sanctuary']:
            if abs(shop[2][0]-castle[2][0])>22 or not 100<=shop[2][1]-castle[2][1]<=340:continue
            for epic in third:
                if abs(shop[2][0]-epic[2][0])>22 or not 65<=epic[2][1]-shop[2][1]<=175:continue
                if max(shop[1],castle[1],epic[1])-min(shop[1],castle[1],epic[1])>.10:continue
                groups.append(((shop[0]+castle[0]+epic[0])/3,shop[2]))
    if not groups:return None
    groups.sort(reverse=True)
    if any(math.dist(point,groups[0][1])>20 and score>=groups[0][0]-.08 for score,point in groups[1:]):return None
    return groups[0][1]


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


def idle_home_candidate(rgb, result):
    """Allow one reveal attempt when recognized game UI is absent.

    This is only a candidate, not recognition of home. After the probe the
    observed home menu and shop still have to be recognized before continuing.
    """
    text = (str(result.get('text', '')) + ' ' + ' '.join(str(word.get('text', ''))
                                                for word in result.get('words', []))).lower()
    # Wallpaper lettering and OCR noise do not establish visible game controls.
    # Recognizable dialogs/loading/action labels do: never use the reveal probe
    # as a confirmation, battle action, login or screen-dismissal shortcut.
    if re.search(r'\b(cancel|confirm|buy|purchase|refresh|connecting|loading|reconnect|'
                 r'battle|arena|summon|sanctuary|secret\s*shop|epic\s*pass|'
                 r'log\s*in|sign\s*in|tap\s+to\s+start)\b',text) or '確認' in text:
        return False
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Only reject an effectively blank capture. Dark or sparse wallpaper is
    # valid, and animated artwork need not match across consecutive frames.
    return bool(gray.std() >= 3)


# Left edge of shop item text in the normalized view. Clients frame the list a
# few pixels differently; a tight edge clipped "Currency" to ")urrency".
TEXT_LEFT = 960


class IncompleteCurrencyRow(MouseStopped):
    pass


class UnclearShopRow(MouseStopped):
    """Row text could not be verified on this capture; a fresh one may differ."""


def button_stock(result,label,button=None):
    """Read the stock inset paired with this Buy label, independent of artwork."""
    middle=lambda box:(box[1]+box[3])/2
    height=label[3]-label[1]
    ratios=[]
    for word in result.get('words',[]):
        # Keep the slash: normal name/price normalization discards it. Only
        # literal stock fractions qualify, never a lone zero or price digit.
        match=re.fullmatch(r'([01])\s*/\s*1',str(word['text']).strip())
        if match is None:continue
        box=tuple(word['box'])
        if not (1480<=box[0]<box[2]<=label[0]-8 and label[0]-box[2]<=200
                and abs(middle(box)-middle(label))<=max(12,height*.35)
                and height*.45<=box[3]-box[1]<=height*1.6):continue
        if button is not None and not (button[0]<=box[0]<box[2]<=button[2]
                and button[1]<=box[1]<box[3]<=button[3]):continue
        ratios.append(int(match[1]))
    if len(ratios)>1:
        raise UnclearShopRow('The shop button stock is ambiguous. Stopped before scrolling or refreshing.')
    return ratios[0] if ratios else None


def retain_row_stock(original,row,label):
    """Retain observed stock only when both reads agree on the Buy bounds."""
    before=button_stock(original,label)
    if before is None:return row
    labels=[tuple(word['box']) for word in row.get('words',[])
            if str(word['text']).lower()=='buy'
            and max(abs(a-b) for a,b in zip(word['box'],label))<=12]
    if len(labels)!=1:
        raise UnclearShopRow('The shop button stock is ambiguous. Stopped before scrolling or refreshing.')
    after=button_stock(row,labels[0])
    if after is not None:
        if before!=after:
            raise UnclearShopRow('The shop button stock is ambiguous. Stopped before scrolling or refreshing.')
        return row
    words=[word for word in original.get('words',[])
           if button_stock(dict(words=[word]),labels[0])==before]
    return dict(row,words=[*row.get('words',[]),*words])


def currency_button(result, boxes, item_name):
    """Associate currency category/name, gold price and Buy text on one row."""
    expected = {'Covenant bookmark':('covenant','bookmark','184000'),
                'Mystic medal':('mystic','medal','280000'),
                'Friendship points':('friendship','point','18000')}
    if item_name not in expected:
        return None
    prefix,noun,price = expected[item_name]
    words = [(re.sub(r'[^a-z0-9]','',word['text'].lower()),tuple(word['box']))
             for word in result.get('words',[])]
    middle = lambda box:(box[1]+box[3])/2
    names = [(text,box) for text,box in words if TEXT_LEFT<=box[0]<box[2]<=1480
             and text in (prefix,prefix+noun,prefix+noun+'s')]
    if not names:
        return None
    if len(names)!=1:
        raise UnclearShopRow(f'The {item_name} rows are ambiguous. Stopped before scrolling or refreshing.')
    text,name = names[0]; y = middle(name)
    suffixes = [box for word,box in words if word in (noun,noun+'s')
                and name[2]<=box[0]<=name[2]+60 and box[2]<=1480 and abs(middle(box)-y)<=20]
    complete = text!=prefix or len(suffixes)==1
    # Purchased status can replace the button on the right, rather than the
    # availability text beneath the name. Require the status on this row;
    # missing Buy/price alone must never silently discard an available item.
    row_words = [word for word,box in sorted(words,key=lambda pair:pair[1][0])
                 if TEXT_LEFT<=box[0]<box[2]<=1880 and -20<=middle(box)-y<=90]
    unavailable = complete and re.search(r'\bsold\s*out\b|\bpurchased\b|\bonly\s+0\s+available\b',' '.join(row_words))
    category = 'currency' if item_name=='Friendship points' else 'summon'
    summons = [box for word,box in words if word==category and TEXT_LEFT<=box[0]<box[2]<=1480
               and 25<=y-middle(box)<=80]
    prices = [box for word,box in words if word==price and 1480<=box[0]<box[2]<=1880
              and -80<=middle(box)-y<=10]
    labels = [label for word,label in words if word=='buy' and 1480<=label[0]<label[2]<=1880
              and 0<=middle(label)-y<=90]
    # A bought row retains "Only 1 available", its price, and a dim green Buy
    # button; the inset changes to 0/1. Require the complete item/category/price
    # association before accepting that fraction even if color detection fails.
    if complete and len(summons)==len(prices)==len(labels)==1:
        label=labels[0]
        if 40<=middle(label)-middle(prices[0])<=125 and button_stock(result,label)==0:
            return None
    buys = [(label,button) for label in labels for button in boxes
            if button[0]<=label[0]<label[2]<=button[2]
            and button[1]<=label[1]<label[3]<=button[3]]
    if unavailable and not buys:
        return None
    if complete and len(summons)==len(prices)==len(buys)==1:
        label,button = buys[0]
        if 40<=middle(label)-middle(prices[0])<=125:
            return label
    if not buys and name[3]+70>1080:
        raise IncompleteCurrencyRow(f'The {item_name} row is partly offscreen. Stopped before refreshing; expose its full Buy button.')
    raise UnclearShopRow(f'The {item_name} name was recognized, but its price and Buy button could not be verified on the same row. Stopped before scrolling or refreshing.')


def green_buttons(rgb, region, *, max_width=450):
    left,top,right,bottom = region
    hsv = cv2.cvtColor(rgb[top:bottom,left:right],cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv,np.array([30,45,25]),np.array([95,255,255]))
    count,_,stats,_ = cv2.connectedComponentsWithStats(mask)
    boxes = []
    for x,y,width,height,area in stats[1:count]:
        if 100 <= width <= max_width and 35 <= height <= 140 and width/height >= 1.4 and area >= width*height*.35:
            boxes.append((int(left+x),int(top+y),int(left+x+width),int(top+y+height)))
    return boxes


def confirmation_button(rgb, operation, before):
    # Expect the green right-hand action button in a newly opened central dialog.
    # Shop Buy buttons are excluded; a single centered acknowledgement is excluded.
    if np.mean(cv2.absdiff(rgb[300:920,550:1400],before[300:920,550:1400])) < 4:
        return None
    # STOVE's purchase button includes the gold-price inset and measures 455px
    # at the normalized size. Keep list/refresh limits unchanged; item and price
    # verification plus a fresh dialog capture still precede confirmation input.
    choices = [box for box in green_buttons(rgb,(800,400,1450,1000),
                                          max_width=500 if operation=='buy' else 450)
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


BUTTON_SETTLED = 6  # mean change of the confirm button between two captures; ~19 mid fade-in, 0 at rest


def button_settled(prior, current, box):
    """True when the confirmation button looks the same in two captures."""
    left,top,right,bottom = (int(v) for v in box)
    if right <= left or bottom <= top:
        return False
    return float(np.mean(cv2.absdiff(prior[top:bottom,left:right],current[top:bottom,left:right]))) < BUTTON_SETTLED


def recheck_mouse_action(action):
    """Retry only undelivered input, through the action's full recognition path."""
    @wraps(action)
    def checked(self,*args,**kwargs):
        for attempt in range(3):
            try:
                return action(self,*args,**kwargs)
            except MouseRecheckRequired:
                self._trace_retry()
                if not self.loop_active:
                    return False
                if attempt==2:
                    raise MouseStopped('Game visibility repeatedly changed before input. No action retried beyond three recognition attempts.')
                print('Navigation: Visibility restored; discarding the prepared action and rechecking the current screen.',flush=True)
                if action.__name__=='swipe':
                    self.navigation.require_shop(self.takeScreenshot())
    return checked


# Shop item list (normalized 1920x1080), compared at 1/8 size.
LIST_REGION = (760,110,1880,1080)
LIST_STILL = 1.5   # mean grey change between frames of a list at rest
LIST_MOVED = 4.0   # mean grey change once the list shows something new
SHOP_RETRY_AFTER_PAUSE = 2  # seconds after a pointer pause before re-selecting an unopened shop menu
SHOP_OPEN_ATTEMPTS = 3  # menu selections before 'did not open' stops the run (opening spends nothing)
REFRESH_FIND_SECONDS = 2.5  # how long to keep re-reading a covered Refresh label before stopping
LIST_REST_SECONDS = .2  # how long the list must stay unchanged to count as settled


def list_view(rgb):
    left,top,right,bottom = LIST_REGION
    grey = cv2.cvtColor(rgb[top:bottom,left:right],cv2.COLOR_RGB2GRAY)
    return cv2.resize(grey,((right-left)//8,(bottom-top)//8),interpolation=cv2.INTER_AREA).astype(np.int16)


class ObservedShopFlow:
    # Mouse and Background capture the game cheaply, so their waits end as soon
    # as the screen shows the expected state, with the old fixed time as the
    # upper bound, and the tap delay becomes the minimum gap between clicks.
    # ADB keeps its fixed waits.
    fast_waits = False
    POLL_SECONDS = .1

    def _pace_tap(self, action):
        last = getattr(self, '_last_tap', None)
        if not self.fast_waits or last is None:
            return
        delay = self.generateTapDelay()
        remaining = delay-(time.monotonic()-last)
        if remaining > 0:
            self._wait_observed(remaining, action+' pacing', baseline=self.tap_sleep)
        # The caller paced before its final check; the click itself must not wait again.
        self._paced = True

    def _poll_wait(self, action):
        """Fixed tap delay for ADB; a short poll interval for fast transports."""
        if self.fast_waits:
            self.wait(self.POLL_SECONDS)
        else:
            self._wait_tap_delay(action)

    def _settled_screenshot(self, seconds, action, *, changed_from=None):
        """Capture the shop once its item list has come to rest.

        ADB waits `seconds` and captures. Fast transports poll: when
        `changed_from` (an earlier frame) is given, the list must first differ
        from it; then it must stay unchanged for LIST_REST_SECONDS and show at
        least three Buy buttons. `seconds` stays the upper bound, and the poll
        count is capped too so a stalled clock cannot loop forever.
        """
        if not self.fast_waits:
            self._wait_observed(seconds, action)
            return self.takeScreenshot() if self.loop_active else None
        started = time.monotonic()
        deadline = started+seconds
        before = None if changed_from is None else list_view(changed_from)
        changed, previous, previous_at, still_since, settled, polls = before is None, None, None, None, False, 0
        still_steps = 0  # consecutive unchanged frames; each poll waits POLL_SECONDS, so 2 steps >= LIST_REST_SECONDS
        max_polls = math.ceil(seconds/self.POLL_SECONDS)+2
        readings = []  # (moved from changed_from, change from previous frame) per poll, for the trace
        frame = None
        while self.loop_active and polls < max_polls and time.monotonic() < deadline:
            frame = self.takeScreenshot(); polls += 1
            captured_at = time.monotonic()
            current = list_view(self._rgb)
            moved = None if before is None else float(np.mean(np.abs(current-before)))
            step = None if previous is None else float(np.mean(np.abs(current-previous)))
            readings.append([None if moved is None else round(moved,2), None if step is None else round(step,2)])
            if not changed and moved >= LIST_MOVED:
                changed = True
            if step is not None and step < LIST_STILL:
                still_since = previous_at if still_since is None else still_since
                still_steps += 1
            else:
                still_since, still_steps = None, 0
            previous, previous_at = current, captured_at
            if (changed and still_since is not None
                    and (captured_at-still_since >= LIST_REST_SECONDS or still_steps >= 2)
                    and len(green_buttons(self._rgb,(1480,110,1880,1080))) >= 3):
                settled = True
                break
            self.wait(max(0, min(self.POLL_SECONDS, deadline-time.monotonic())))
        if self.loop_active and not settled:
            frame = self.takeScreenshot()
        trace = getattr(self, 'input_trace', None)
        if trace is not None and trace.enabled:
            trace.emit('delay', action=action, baseline_ms=None, requested_ms=seconds*1000,
                       elapsed_ms=(time.monotonic()-started)*1000, interrupted=not self.loop_active,
                       settled=settled, polls=polls, readings=readings)
        return frame if self.loop_active else None

    def _tap_observed(self, x, y, *, anchor=None, action='navigation'):
        if not getattr(self, '_paced', False):
            self._pace_tap(action)
        self._paced = False
        try:
            return self._tap_traced(x, y, anchor=anchor, action=action)
        finally:
            self._last_tap = time.monotonic()

    def _tap_traced(self, x, y, *, anchor=None, action='navigation'):
        trace = getattr(self, 'input_trace', None)
        if trace is None or not trace.enabled:
            return self.tap(x, y)
        anchor = anchor or (x, y)
        values = dict(action=action, anchor=[round(float(v), 3) for v in anchor],
                      offset=[round(float(x-anchor[0]), 3), round(float(y-anchor[1]), 3)],
                      final=[round(float(x), 3), round(float(y), 3)],
                      mapped_space='screen' if hasattr(self, 'mouse') else 'device', mapped=None)
        try:
            mapped = self.tap(x, y)
        except Exception:
            trace.emit('click', **values, outcome='blocked or failed')
            raise
        if isinstance(mapped, (tuple, list)) and len(mapped) == 2:
            values['mapped'] = [int(v) for v in mapped]
        trace.emit('click', **values, outcome='input sent' if values['mapped'] is not None else 'delivery unreported')
        return mapped

    def _wait_observed(self, seconds, action, *, baseline=None):
        trace = getattr(self, 'input_trace', None)
        if trace is None or not trace.enabled:
            return self.wait(seconds)
        started = trace.clock()
        try:
            return self.wait(seconds)
        finally:
            trace.emit('delay', action=action, baseline_ms=baseline*1000 if baseline is not None else None,
                       requested_ms=seconds*1000, elapsed_ms=max(0, trace.clock()-started)*1000,
                       interrupted=not self.loop_active)

    def _wait_tap_delay(self, action):
        # Exactly one draw, used for both the wait and its diagnostic event.
        self._wait_observed(self.generateTapDelay(), action, baseline=self.tap_sleep)

    def _trace_retry(self):
        trace = getattr(self, 'input_trace', None)
        if trace is not None:
            trace.retry()

    @recheck_mouse_action
    def clickShop(self):
        deadline = time.monotonic()+30
        revealed = False
        opens = 0
        while self.loop_active and time.monotonic()<deadline:
            frame = self.takeScreenshot()
            if self.navigation.shop_visible(frame):
                print('Navigation: Secret Shop screen verified; already open.',flush=True)
                return True
            target = self._home_menu_target(frame)
            if not self.loop_active:
                return False
            if target is not None:
                # Re-recognize the actual controls, rather than comparing a
                # large area of moving wallpaper beside them.
                fresh_target = self._home_menu_target(self.takeScreenshot())
                if fresh_target is None or math.dist(target,fresh_target)>8:
                    continue
                print('Navigation: Opening the recognized Secret Shop menu.',flush=True)
                self._tap_observed(*fresh_target, action='open shop')
                opens += 1
                opened = self._wait_for_shop(final=opens>=SHOP_OPEN_ATTEMPTS)
                if opened is not None:
                    return opened
                # A pointer brushing over the game can swallow the menu click.
                # Opening the shop spends nothing: re-recognize the home screen
                # from scratch (including one reveal) and select it again.
                print('Navigation: The Secret Shop did not open; checking the home screen again.',flush=True)
                revealed = False
                deadline = max(deadline,time.monotonic()+15)
                continue
            if not revealed and hidden_home_matches(frame):
                fresh = self.takeScreenshot()
                if hidden_home_matches(fresh):
                    print('Navigation: Revealing the recognized home screen controls.',flush=True)
                    revealed = True
                    self._tap_observed(960,540, action='reveal home controls')
                    self.wait(.5)
                    continue
            elif not revealed:
                # Use one default reveal attempt, independent of wallpaper
                # text, brightness, quadrant detail or animation. Inspect the
                # full view for known UI, then recheck controls before input.
                prior = self._rgb.copy()
                candidate = read_ui_text(prior,(0,0,1920,1080))
                if idle_home_candidate(prior,candidate):
                    fresh = self.takeScreenshot()
                    if not self.loop_active:
                        return False
                    if self.navigation.shop_visible(fresh):
                        return True
                    if self._home_menu_target(fresh) is not None:
                        continue
                    fresh_candidate=read_ui_text(self._rgb,(0,0,1920,1080))
                    if self.loop_active and idle_home_candidate(self._rgb,fresh_candidate):
                        print('Navigation: No home controls recognized; clicking once to reveal them.',flush=True)
                        revealed = True
                        self._tap_observed(960,540, action='reveal home controls')
                        self.wait(.5)
                        continue
            print('Navigation: Looking for the home Secret Shop menu. No shop action sent.',flush=True)
            self.wait(.5)
        if not self.loop_active:
            return False
        saved=self._save_home_failure(revealed)
        detail=' A private menu crop was saved under mouse-failures.' if saved else ''
        raise MouseStopped('The home Secret Shop menu could not be recognized. Start from the English home screen or an already open Secret Shop.'+detail)


    def _home_menu_target(self,frame):
        target=native_home_control_target(self._rgb)
        if target is not None:return target
        caption=self.navigation.menu_target(frame)
        if caption is not None:
            target=home_icon_target(self._rgb,caption)
            if target is not None: return target
        self._last_home_ocr=self.read_navigation_text(self._rgb)
        if self._last_home_ocr.get('text','').strip():
            self._home_failure_rgb=self._rgb.copy()
            self._home_failure_ocr=self._last_home_ocr
        return home_menu_target(self._last_home_ocr,self._rgb)


    def _save_home_failure(self,revealed):
        try:
            folder=Path('mouse-failures')/uuid.uuid4().hex
            folder.mkdir(parents=True)
            rgb=getattr(self,'_home_failure_rgb',self._rgb)
            Image.fromarray(rgb[180:920,:420]).save(folder/'home-menu.png')
            (folder/'failure.json').write_text(json.dumps(dict(operation='home-entry',
                reveal_clicked=revealed,shop_clicked=False,normalized_size=[1920,1080],
                home_ocr=getattr(self,'_home_failure_ocr',getattr(self,'_last_home_ocr',{})))),encoding='utf-8')
            return True
        except OSError:
            return False


    def _wait_for_shop(self, *, final=True):
        """True once the shop shows; False if stopped; None on timeout unless final."""
        deadline = time.monotonic()+8
        while self.loop_active and time.monotonic()<deadline:
            self.wait(.25)
            if not self.loop_active:
                return False
            frame = self.takeScreenshot()
            if self._capture_resumed:
                # The pointer crossed the game, which can swallow the menu
                # click; the shop normally opens within a second. Retry soon
                # after it leaves rather than waiting out the full 8 s, except
                # on the last attempt.
                deadline = time.monotonic()+(8 if final else SHOP_RETRY_AFTER_PAUSE)
            if self.navigation.shop_visible(frame):
                print('Navigation: Secret Shop screen verified.',flush=True)
                return True
        if not self.loop_active:
            return False
        if not final:
            return None
        raise MouseStopped('The Secret Shop did not open after selecting its menu. No refresh or purchase sent.')


    def findItemPosition(self,frame,template):
        if not self.loop_active:
            return None
        # A preceding purchase may have updated _rgb since the shared loop's
        # initial grayscale frame. Always inspect the latest captured image.
        region = cv2.cvtColor(self._rgb,cv2.COLOR_RGB2GRAY)[110:1080,760:1030]
        item_name = next((name for name,item in self.storage.inventory.items() if item.image is template),None)
        best = None
        for scale in (np.linspace(.65,1.45,17) if template is not None else ()):
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
            # Apply the same observed stock guard to Covenant/Mystic's icon
            # path. Purchased icons and dim Buy buttons can still match.
            result=self._shop_text()
            if not self.loop_active:return None
            labels=[tuple(word['box']) for word in result.get('words',[])
                    if str(word['text']).lower()=='buy' and box[0]<=word['box'][0]<word['box'][2]<=box[2]
                    and box[1]<=word['box'][1]<word['box'][3]<=box[3]]
            if len(labels)!=1 or button_stock(result,labels[0],box) is None:
                result=self._stock_row_text((box[1]+box[3])/2,box[2]+15)
                if not self.loop_active:return None
                labels=[tuple(word['box']) for word in result.get('words',[])
                        if str(word['text']).lower()=='buy' and box[0]<=word['box'][0]<word['box'][2]<=box[2]
                        and box[1]<=word['box'][1]<word['box'][3]<=box[3]]
            if len(labels)==1 and button_stock(result,labels[0],box)==0:
                return None
            # The left stock-count inset can ignore clicks in the native skin.
            # Keep icon-based purchases within the observed button's right side.
            width,height = box[2]-box[0],box[3]-box[1]
            box = (box[0]+round(width*.55),box[1]+round(height*.2),
                   box[2]-round(width*.08),box[3]-round(height*.2))
            method = 'icon'
        else:
            if item_name not in ('Covenant bookmark','Mystic medal','Friendship points'):
                return None
            result=self._item_text(item_name)
            if not self.loop_active:
                return None
            try:
                box = currency_button(result,boxes,item_name)
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


    def _shop_text(self):
        if getattr(self,'_shop_ocr_source',None) is not self._rgb:
            self._shop_ocr = read_ui_text(self._rgb,(TEXT_LEFT,110,1880,1080))
            self._shop_ocr_source = self._rgb
            self._stock_rows = {}
        return self._shop_ocr


    def _stock_row_text(self,center,right=1880):
        self._shop_text()
        region=(TEXT_LEFT,max(110,round(center-120)),min(1880,round(right)),min(1080,round(center+80)))
        if region not in self._stock_rows:
            # Small dim stock text can disappear in whole-list OCR. Isolate
            # its row, enlarge/normalize contrast, and map bounds back to the
            # same view. This reads controls, never a wallpaper reference.
            self._stock_rows[region]=read_ui_text(self._rgb,region,scale=2,contrast=True)
        return self._stock_rows[region]


    def _item_text(self,item_name):
        result=self._shop_text()
        prefix={'Covenant bookmark':'covenant','Mystic medal':'mystic','Friendship points':'friendship'}[item_name]
        names=[word['box'] for word in result.get('words',[])
               if re.sub(r'[^a-z]','',word['text'].lower()).startswith(prefix)
               and TEXT_LEFT<=word['box'][0]<word['box'][2]<=1480]
        if len(names)!=1:return result
        center=(names[0][1]+names[0][3])/2
        labels=[tuple(word['box']) for word in result.get('words',[])
                if str(word['text']).lower()=='buy' and 1480<=word['box'][0]<word['box'][2]<=1880
                and -20<=(word['box'][1]+word['box'][3])/2-center<=90]
        if len(labels)==1 and button_stock(result,labels[0]) is not None:
            try:
                currency_button(result,green_buttons(self._rgb,(1480,110,1880,1080)),item_name)
                return result
            except IncompleteCurrencyRow:
                return result
            except MouseStopped as error:
                if 'could not be verified on the same row' not in str(error):raise
        if len(labels)==1:
            row=self._stock_row_text((labels[0][1]+labels[0][3])/2,labels[0][2]+70)
            return retain_row_stock(result,row,labels[0])
        return self._stock_row_text(center+40)


    def _click_button(self,box, action='buy'):
        x,y = (box[0]+box[2])/2,(box[1]+box[3])/2
        dx,dy = self.generateOffset()
        # Preserve randomized offsets, bounded well inside the observed button.
        dx = max(-(box[2]-box[0])/4,min((box[2]-box[0])/4,dx))
        dy = max(-(box[3]-box[1])/4,min((box[3]-box[1])/4,dy))
        self._tap_observed(x+dx,y+dy, anchor=(x,y), action=action)


    def _confirm(self,operation,before):
        deadline = time.monotonic()+5
        text_rejected = False
        changed = None
        visibility_rechecks = 0
        while self.loop_active and time.monotonic()<deadline:
            self._poll_wait(operation+' dialog')
            if not self.loop_active:
                return False
            self.takeScreenshot()
            if self._capture_resumed:
                deadline = time.monotonic()+5
            box = confirmation_button(self._rgb,operation,before)
            if box is not None:
                text = self.read_confirmation_text(self._rgb)
                if not confirmation_matches(text,operation,self._item_name):
                    # Buttons can become readable before the prompt finishes
                    # appearing. Re-capture within the same bounded wait; never
                    # weaken item/cost validation or reuse a rejected OCR result.
                    text_rejected = True
                    self._trace_retry()
                    continue
                if not self.loop_active:
                    return False
                # Wait out the tap delay first, so the fresh capture below is
                # the last check before the click.
                self._pace_tap(operation+' confirm')
                if not self.loop_active:
                    return False
                # Revalidate the intended action on a fresh capture. Artwork
                # behind a translucent dialog can animate, and OCR button
                # bounds can shift a few pixels without the dialog changing.
                prior = self._rgb.copy()
                self.takeScreenshot()
                if not self.loop_active:
                    return False
                current = confirmation_button(self._rgb,operation,before)
                same_button = (current is not None and all(abs(a-b)<=8 for a,b in zip(current,box))
                               and button_settled(prior,self._rgb,current))
                fresh_text = self.read_confirmation_text(self._rgb) if same_button else ''
                if not self.loop_active:
                    return False
                if not same_button:
                    # Usually the dialog is still fading in: fast captures can
                    # catch it half transparent. Read it again within the same
                    # bounded wait; only two agreeing captures lead to a click.
                    changed = prior
                    self._trace_retry()
                    continue
                if not confirmation_matches(fresh_text,operation,self._item_name):
                    # A settled button whose dialog now names another action,
                    # item or cost is not a fade: stop at once.
                    saved = self._save_confirmation_failure(operation,before,validated=prior)
                    detail = ' A private dialog crop was saved for diagnosis.' if saved else ''
                    raise MouseStopped('The confirmation changed while being read. No confirmation click sent.'+detail)
                try:
                    self._click_button(current, action=operation+' confirm')
                except MouseRecheckRequired:
                    if not self.loop_active:
                        return False
                    visibility_rechecks += 1
                    self._trace_retry()
                    if visibility_rechecks>=3:
                        raise MouseStopped('Game visibility repeatedly changed before confirmation. No confirmation click sent.')
                    print('Navigation: Visibility restored; reading the confirmation again before clicking.',flush=True)
                    deadline = time.monotonic()+5
                    continue
                break
            self._trace_retry()
        else:
            if not self.loop_active:
                return False
            saved = self._save_confirmation_failure(operation,before,validated=changed)
            detail = ' A private dialog crop was saved for diagnosis.' if saved else ''
            if changed is not None:
                raise MouseStopped('The confirmation kept changing while being read. No confirmation click sent.'+detail)
            # Diagnosis only: a dialog left open (e.g. by an earlier stopped run)
            # hides the new one from the change check above.
            if confirmation_matches(self.read_confirmation_text(before),operation,self._item_name):
                raise MouseStopped(f'A {operation} confirmation was already open before the {operation} click. '
                                   'No confirmation click sent.'+detail)
            if text_rejected:
                raise MouseStopped('The confirmation does not match the intended shop action. No confirmation click sent.'+detail)
            raise MouseStopped(f'The {operation} confirmation was not recognized. No confirmation click sent.'+detail)
        clicked, click_revision, retried = current, self._pause_revision(), False
        while True:
            deadline = time.monotonic()+5
            while self.loop_active and time.monotonic()<deadline:
                self._poll_wait(operation+' shop return')
                if not self.loop_active:
                    return False
                frame = self.takeScreenshot()
                if self._capture_resumed:
                    deadline = time.monotonic()+5
                if confirmation_button(self._rgb,operation,before) is None and self.navigation.shop_visible(frame):
                    return True
                self._trace_retry()
            if not self.loop_active:
                return False
            # A pointer passing over the game can swallow the Confirm click and
            # leave the dialog open. Confirm once more only if that happened
            # (a pause since the click) and the very same validated dialog is
            # still open: a delivered click closes it, so this cannot charge
            # twice. Anything else stops as before.
            if retried or click_revision is None or self._pause_revision() == click_revision:
                raise MouseStopped('The shop did not return after confirmation. Stopped before another action.')
            retried = True
            box = self._same_confirmation_open(operation,before,clicked)
            if not self.loop_active:
                return False
            if box is None:
                raise MouseStopped('The shop did not return after confirmation. Stopped before another action.')
            print('Navigation: The pointer passed over the game and the same confirmation is still open; confirming once more.',flush=True)
            click_revision = self._pause_revision()
            try:
                self._click_button(box, action=operation+' confirm retry')
            except MouseRecheckRequired:
                if not self.loop_active:
                    return False
                raise MouseStopped('The game paused again before the repeated confirmation. No second confirmation click sent.') from None


    def _pause_revision(self):
        """Pointer-pause counter of the Background/Mouse transport; None for ADB."""
        revision = getattr(getattr(self,'mouse',None),'pause_revision',None)
        return revision if isinstance(revision,int) else None


    def _same_confirmation_open(self,operation,before,clicked):
        """The clicked dialog, if it is still open, settled and still names the intended action."""
        self.takeScreenshot()
        prior = self._rgb.copy()
        first = confirmation_button(prior,operation,before)
        if (first is None or any(abs(a-b)>8 for a,b in zip(first,clicked))
                or not confirmation_matches(self.read_confirmation_text(prior),operation,self._item_name)):
            return None
        self._poll_wait(operation+' confirm recheck')
        if not self.loop_active:
            return None
        self.takeScreenshot()
        current = confirmation_button(self._rgb,operation,before)
        if (current is None or any(abs(a-b)>8 for a,b in zip(current,clicked))
                or not button_settled(prior,self._rgb,current)
                or not confirmation_matches(self.read_confirmation_text(self._rgb),operation,self._item_name)):
            return None
        return current


    def _save_confirmation_failure(self,operation,before,*,validated=None):
        # Keep only central game crops, excluding the account/currency header.
        # These private runtime files are never part of the release package.
        try:
            folder = Path('mouse-failures')/uuid.uuid4().hex
            folder.mkdir(parents=True)
            Image.fromarray(before[260:1000,500:1450]).save(folder/'before.png')
            Image.fromarray(self._rgb[260:1000,500:1450]).save(folder/'dialog.png')
            if validated is not None:
                Image.fromarray(validated[260:1000,500:1450]).save(folder/'validated.png')
            (folder/'failure.json').write_text(json.dumps(dict(operation=operation,
                confirmation_clicked=False,normalized_size=[1920,1080])),encoding='utf-8')
            return True
        except OSError:
            return False


    @recheck_mouse_action
    def clickBuy(self,pos):
        if pos is None or not self.loop_active or (self._item is None and self._item_name != 'Friendship points'):
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


    @recheck_mouse_action
    def clickRefresh(self):
        if not self.loop_active:
            return False
        self._item=self._item_name=None
        # After a purchase the shop can return while a toast or the sold-out
        # animation still covers the Refresh label (reported on STOVE). Full
        # shop recognition needs that label, so while it is covered only the
        # shop title is required: re-read for a bounded time, never click until
        # the full shop (title and Refresh) is verified, and stop at once on
        # any frame without the shop title.
        deadline = None
        while True:
            frame = self.takeScreenshot()
            if self.navigation.shop_visible(frame):
                self.navigation.require_shop(frame)
                points = [match['point'] for _,nav in self.navigation.navigators
                          if nav.shop_visible(frame) and (match:=nav.match(frame,'refresh-label.png'))]
                if points and all(abs(x-points[0][0])<=8 and abs(y-points[0][1])<=8 for x,y in points):
                    break
            elif not any(nav.match(frame,'shop-title.png') or nav.dimmed(frame,'shop-title.png')
                         for _,nav in self.navigation.navigators):
                self.navigation.require_shop(frame)  # Not the shop: stop with the usual details.
            if not self.loop_active:
                return False
            now = time.monotonic()
            if deadline is None:
                deadline = now+REFRESH_FIND_SECONDS
            elif now >= deadline:
                self.navigation.require_shop(frame)
                raise MouseStopped('The Refresh target was not recognized. No click sent.')
            self._trace_retry()
            self._poll_wait('refresh find')
            if not self.loop_active:
                return False
        before = self._rgb.copy()
        # The next list settle waits for the new items, not this page.
        self._list_before = before
        x,y = points[0]
        anchor = (x,y)
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
        self._tap_observed(x,y, anchor=anchor, action='refresh')
        return self._confirm('refresh',before)


