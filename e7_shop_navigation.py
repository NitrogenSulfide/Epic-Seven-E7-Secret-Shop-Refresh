"""Recognize English Secret Shop UI from private, locally calibrated references."""
from pathlib import Path

import cv2
import numpy as np

FRAME_SIZE = (1920, 1080)
# Reference crops use stable text, avoiding artwork, account details and overlays.
REFERENCE_BOXES = {
    'menu-secret-shop.png': (12, 532, 161, 565),
    'shop-title.png': (99, 25, 305, 76),
    'refresh-label.png': (341, 973, 459, 1020),
}
SEARCH_BOXES = {
    'menu-secret-shop.png': (0, 210, 320, 800),
    'shop-title.png': (75, 0, 410, 110),
    'refresh-label.png': (250, 910, 555, 1060),
}


def prepare_references(home, shop, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Choose a new reference directory; preserve existing calibration.')
    images = {}
    for name, path in (('home', home), ('shop', shop)):
        image = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None or abs(image.shape[1] / image.shape[0] - 16/9) > .02:
            raise ValueError('Use uncropped 16:9 home/shop screenshots.')
        images[name] = cv2.resize(image, FRAME_SIZE, interpolation=cv2.INTER_AREA)
    destination.mkdir(parents=True)
    for name, (x1,y1,x2,y2) in REFERENCE_BOXES.items():
        image = images['home' if name.startswith('menu-') else 'shop']
        ok, data = cv2.imencode('.png', image[y1:y2, x1:x2])
        if not ok:
            raise ValueError('Reference encoding failed.')
        (destination/name).write_bytes(data.tobytes())
    navigator = ShopNavigator(destination)
    if navigator.menu_target(images['home']) is None or navigator.shop_visible(images['home']) or not navigator.shop_visible(images['shop']):
        raise ValueError('Reference screenshots do not match the supported English menu/shop layout.')
    return images


class ShopNavigator:
    def __init__(self, reference_directory):
        self.references = {}
        for name in REFERENCE_BOXES:
            path = Path(reference_directory)/name
            if not path.is_file():
                raise RuntimeError(f'Navigation reference missing: {name}. Prepare local shop references before starting.')
            reference = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if reference is None or reference.size == 0:
                raise RuntimeError(f'Navigation reference unreadable: {name}')
            edges = cv2.Canny(reference, 45, 110)
            if np.count_nonzero(edges) < 30:
                raise RuntimeError(f'Navigation reference has too little detail: {name}')
            self.references[name] = reference

    def match(self, screenshot, name):
        if not isinstance(screenshot, np.ndarray) or screenshot.ndim != 2 or screenshot.shape != (1080,1920):
            raise RuntimeError('Navigation needs a valid 1920 x 1080 ADB screenshot.')
        x1,y1,x2,y2 = SEARCH_BOXES[name]
        search = cv2.Canny(screenshot[y1:y2,x1:x2], 45, 110)
        reference = self.references[name]
        best = None
        for scale in (.94, .97, 1., 1.03, 1.06):
            resized = cv2.resize(reference, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            template = cv2.Canny(resized, 45, 110)
            if template.shape[0] > search.shape[0] or template.shape[1] > search.shape[1]:
                continue
            scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(scores)
            if best is None or score > best['score']:
                # A second distant match makes selection ambiguous; don't guess.
                tx,ty = location
                other = scores.copy()
                h,w = template.shape
                other[max(0,ty-h):ty+h+1,max(0,tx-w):tx+w+1] = -1
                second = float(other.max())
                best = dict(score=float(score), second=second,
                            point=(x1+tx+w//2, y1+ty+h//2))
        if best is None or best['score'] < .72 or best['second'] >= best['score']-.10:
            return None
        return best

    def shop_visible(self, screenshot):
        return bool(self.match(screenshot, 'shop-title.png') and self.match(screenshot, 'refresh-label.png'))

    def menu_target(self, screenshot):
        match = self.match(screenshot, 'menu-secret-shop.png')
        return match['point'] if match else None

    def require_shop(self, screenshot):
        if not self.shop_visible(screenshot):
            raise RuntimeError('Secret Shop screen not verified. Stopped before further shop actions; open Secret Shop and try again.')
