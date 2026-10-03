"""Offline image tests; optional private user screenshots stay outside Git."""
import os
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from e7_shop_navigation import FRAME_SIZE, REFERENCE_BOXES, ShopNavigator


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.images = {}
        texts = {'menu-secret-shop.png':'Secret Shop','shop-title.png':'Secret Shop','refresh-label.png':'Refresh'}
        for name, (x1,y1,x2,y2) in REFERENCE_BOXES.items():
            image = np.zeros((y2-y1,x2-x1),dtype=np.uint8)
            cv2.putText(image, texts[name], (2,image.shape[0]-7),cv2.FONT_HERSHEY_SIMPLEX,.5,255,1,cv2.LINE_AA)
            cv2.imencode('.png',image)[1].tofile(str(self.directory/name))
            self.images[name] = image
        self.nav = ShopNavigator(self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def frame(self, names):
        image = np.zeros((1080,1920),dtype=np.uint8)
        for name in names:
            x1,y1,x2,y2 = REFERENCE_BOXES[name]
            image[y1:y2,x1:x2] = self.images[name]
        return image

    def test_menu_and_shop_are_distinguished(self):
        home = self.frame(['menu-secret-shop.png'])
        shop = self.frame(['shop-title.png','refresh-label.png'])
        self.assertEqual(self.nav.menu_target(home),(86,548))
        self.assertFalse(self.nav.shop_visible(home))
        self.assertTrue(self.nav.shop_visible(shop))
        self.assertIsNone(self.nav.menu_target(shop))

    def test_unknown_screen_and_partial_shop_fail(self):
        for names in ([],['shop-title.png'],['refresh-label.png']):
            image = self.frame(names)
            self.assertFalse(self.nav.shop_visible(image))
            with self.assertRaises(RuntimeError):
                self.nav.require_shop(image)

    def test_unrelated_wallpapers_without_controls_are_never_recognized(self):
        generator = np.random.default_rng(9)
        for _ in range(4):
            low_resolution = generator.integers(0,256,(54,96),dtype=np.uint8)
            wallpaper = cv2.resize(low_resolution,FRAME_SIZE,interpolation=cv2.INTER_CUBIC)
            self.assertIsNone(self.nav.menu_target(wallpaper))
            self.assertFalse(self.nav.shop_visible(wallpaper))

    def test_menu_can_move_vertically_and_tap_follows_match(self):
        home = self.frame(['menu-secret-shop.png'])
        home = np.roll(home,70,axis=0)
        self.assertEqual(self.nav.menu_target(home),(86,618))

    def test_two_menu_matches_are_rejected_as_ambiguous(self):
        home = self.frame(['menu-secret-shop.png'])
        image = self.images['menu-secret-shop.png']
        home[700:700+image.shape[0],12:12+image.shape[1]] = image
        self.assertIsNone(self.nav.menu_target(home))

    def test_duplicate_refresh_labels_do_not_verify_a_shop(self):
        shop = self.frame(['shop-title.png'])
        image = self.images['refresh-label.png']
        for x in (260, 400):
            shop[950:950+image.shape[0], x:x+image.shape[1]] = image
        self.assertIsNone(self.nav.match(shop, 'refresh-label.png'))
        self.assertFalse(self.nav.shop_visible(shop))

    def test_invalid_size_or_missing_reference_fails(self):
        with self.assertRaises(RuntimeError):
            self.nav.shop_visible(np.zeros((720,1280),dtype=np.uint8))
        with self.assertRaises(RuntimeError):
            self.nav.shop_visible(None)
        (self.directory/'shop-title.png').unlink()
        with self.assertRaises(RuntimeError):
            ShopNavigator(self.directory)


@unittest.skipUnless(os.environ.get('E7_NAV_FIXTURES'),'Private image fixtures not supplied')
class PrivateScreenshotTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('E7_NAV_LIVE_SHOP'), 'Independent raw shop screenshot not supplied')
    def test_held_out_raw_adb_shop_with_original_desktop_references(self):
        folder = Path(os.environ['E7_NAV_FIXTURES'])
        nav = ShopNavigator(folder/'references')
        path = Path(os.environ['E7_NAV_LIVE_SHOP'])
        shop = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        self.assertTrue(nav.shop_visible(shop))
        self.assertIsNone(nav.menu_target(shop))
        for name in ('shop-title.png', 'refresh-label.png'):
            match = nav.match(shop, name)
            self.assertIsNotNone(match)
            self.assertGreater(match['score'], .95)
        for factor in (.65, .85, 1.15):
            adjusted = np.clip(shop.astype(np.float32)*factor, 0, 255).astype(np.uint8)
            self.assertTrue(nav.shop_visible(adjusted))
        for name in ('shop-title.png','refresh-label.png'):
            obscured = shop.copy()
            # Suppress the whole search region so no remaining fragment can
            # accidentally stand in for the required marker.
            from e7_shop_navigation import SEARCH_BOXES
            x1,y1,x2,y2 = SEARCH_BOXES[name]
            obscured[y1:y2,x1:x2] = 0
            self.assertFalse(nav.shop_visible(obscured))

    def test_user_screenshots_and_brightness(self):
        folder = Path(os.environ['E7_NAV_FIXTURES'])
        nav = ShopNavigator(folder/'references')
        read = lambda name: cv2.imdecode(np.frombuffer((folder/name).read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
        home,shop = read('home.png'),read('shop.png')
        self.assertEqual(nav.menu_target(home),(86,548))
        self.assertFalse(nav.shop_visible(home))
        self.assertTrue(nav.shop_visible(shop))
        self.assertIsNone(nav.menu_target(shop))
        for factor in (.65,.85,1.15):
            darker = np.clip(shop.astype(np.float32)*factor,0,255).astype(np.uint8)
            self.assertTrue(nav.shop_visible(darker),factor)
        for name in ('shop-title.png','refresh-label.png'):
            obscured = shop.copy()
            x1,y1,x2,y2 = REFERENCE_BOXES[name]
            obscured[y1:y2,x1:x2] = 0
            self.assertFalse(nav.shop_visible(obscured),name)
        # With the Secret Shop target obscured, other home-menu items must not
        # cause a fallback tap (including the visible Milestone of Radiance).
        unknown = home.copy()
        x1,y1,x2,y2 = REFERENCE_BOXES['menu-secret-shop.png']
        unknown[y1:y2,x1:x2] = 0
        self.assertIsNone(nav.menu_target(unknown))


if __name__ == '__main__':
    unittest.main()
