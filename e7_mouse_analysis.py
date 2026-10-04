"""Offline preview recognition only. No input, ADB calls, hooks or purchases."""
from pathlib import Path
import cv2
import numpy as np
from e7_shop_navigation import create_navigator, FRAME_SIZE


def inspect_mouse_frame(path, assets):
    frame = cv2.imdecode(np.frombuffer(Path(path).read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
    if frame is None or frame.shape[1] < 640 or frame.shape[0] < 360:
        raise ValueError('Use a valid game-client screenshot at least 640 × 360 pixels.')
    size = (frame.shape[1],frame.shape[0])
    frame = cv2.resize(frame,FRAME_SIZE,interpolation=cv2.INTER_AREA)
    navigation = create_navigator(assets)
    shop = navigation.shop_visible(frame)
    menu = None if shop else navigation.menu_target(frame)
    targets, detections = [], []
    if menu:
        targets.append(dict(label='Secret Shop menu',point=list(menu)))
    if shop:
        points = [match['point'] for _,nav in navigation.navigators
                  if nav.shop_visible(frame) and (match := nav.match(frame,'refresh-label.png'))]
        if points and all(abs(x-points[0][0])<=8 and abs(y-points[0][1])<=8 for x,y in points):
            targets.append(dict(label='Refresh button',point=list(points[0])))
        for name,label in (('cov.png','Covenant Bookmark'),('mys.png','Mystic Medal')):
            template = cv2.imdecode(np.frombuffer((Path(assets)/name).read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
            if template is None: continue
            # Limit item detection to the shop icon column, excluding balances,
            # merchant portraits, home icons and unrelated notifications.
            region = frame[110:1080,760:1030]
            for scale in (.94,1.,1.06):
                item = cv2.resize(template,None,fx=scale,fy=scale,interpolation=cv2.INTER_LINEAR)
                scores = cv2.matchTemplate(region,item,cv2.TM_CCOEFF_NORMED)
                _,score,_,(x,y) = cv2.minMaxLoc(scores)
                if score >= .90:
                    detections.append(dict(label=label,box=[x+760,y+110,x+760+item.shape[1],y+110+item.shape[0]],score=float(score)))
                    break
    return dict(read_only=True,state='shop' if shop else 'home' if menu else 'unrecognized',
                original_size=list(size),normalized_size=list(FRAME_SIZE),targets=targets,detections=detections)
