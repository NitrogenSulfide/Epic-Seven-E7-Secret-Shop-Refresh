"""Windows wider than 16:9 (STOVE or Steam maximized, e.g. 3840 x 2019).

The game scales its UI with the window height, so stretching such a view into
the 1920 x 1080 recognition frame narrows every label and icon. Recognition
must try that narrower shape as well as the reference shape.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import cv2
import numpy as np
from PIL import Image

from e7_frame import FrameGeometry, frame_x_squash
from e7_mouse_refresh import E7MouseShopRefresh
from e7_shop_navigation import REFERENCE_BOXES, create_navigator, template_widths

ASSETS = 'adb-assets'


def squashed_shop(x_squash):
    """A plain 1920 x 1080 frame with the shipped shop labels narrowed by x_squash."""
    rng = np.random.default_rng(7)
    frame = rng.integers(30, 60, (1080, 1920), dtype=np.uint8)
    for name in ('shop-title.png', 'refresh-label.png'):
        reference = cv2.imread(str(Path(ASSETS)/'builtin-navigation'/name), cv2.IMREAD_GRAYSCALE)
        label = cv2.resize(reference, None, fx=x_squash, fy=1., interpolation=cv2.INTER_AREA)
        x1, y1 = REFERENCE_BOXES[name][:2]
        frame[y1:y1+label.shape[0], x1:x1+label.shape[1]] = label
    return frame


class FrameSquashTests(unittest.TestCase):
    def test_squash_follows_the_view_aspect(self):
        self.assertEqual(frame_x_squash((0, 0, 1920, 1080)), 1.)
        self.assertEqual(frame_x_squash((0, 0, 2560, 1440)), 1.)
        self.assertAlmostEqual(frame_x_squash((0, 0, 3840, 2019)), .9348, places=3)
        self.assertAlmostEqual(frame_x_squash((0, 0, 1920, 1009)), .9343, places=3)
        self.assertEqual(frame_x_squash((0, 0, 1440, 1080)), 1.)   # narrower: never widened
        self.assertEqual(frame_x_squash((5, 5, 5, 5)), 1.)          # degenerate bounds
        self.assertAlmostEqual(FrameGeometry((3840, 2019), (0, 0, 3840, 2019)).x_squash, .9348, places=3)

    def test_template_widths_keep_the_reference_shape(self):
        self.assertEqual(template_widths(1.), (1.,))
        self.assertEqual(template_widths(.995), (1.,))
        self.assertEqual(template_widths(.935), (1., .935))


class WideShopRecognitionTests(unittest.TestCase):
    def test_narrowed_shop_is_verified_only_with_the_frame_squash(self):
        frame = squashed_shop(.91)
        navigator = create_navigator(ASSETS)
        self.assertFalse(navigator.shop_visible(frame))
        navigator.x_squash = .91
        self.assertTrue(navigator.shop_visible(frame))
        self.assertTrue(all(nav.x_squash == .91 for _, nav in navigator.navigators))

    def test_reference_shape_still_matches_when_a_squash_is_set(self):
        # Saved references captured from the same wide window are already narrow.
        navigator = create_navigator(ASSETS)
        navigator.x_squash = .91
        self.assertTrue(navigator.shop_visible(squashed_shop(1.)))

    def test_empty_frame_is_not_a_shop_at_any_squash(self):
        navigator = create_navigator(ASSETS)
        navigator.x_squash = .9
        self.assertFalse(navigator.shop_visible(np.full((1080, 1920), 45, np.uint8)))

    def test_a_second_label_at_the_other_width_stays_ambiguous(self):
        reference = cv2.imread(str(Path(ASSETS)/'builtin-navigation'/'menu-secret-shop.png'), cv2.IMREAD_GRAYSCALE)
        narrow = cv2.resize(reference, None, fx=.96, fy=1., interpolation=cv2.INTER_AREA)
        def frame(labels):
            image = np.full((1080, 1920), 40, np.uint8)
            for label, y in labels:
                image[y:y+label.shape[0], 12:12+label.shape[1]] = label
            return image
        navigator = create_navigator(ASSETS)
        navigator.x_squash = .96
        self.assertIsNotNone(navigator.menu_target(frame([(narrow, 650)])))
        self.assertIsNone(navigator.menu_target(frame([(reference, 250), (reference, 450), (narrow, 650)])))
        self.assertIsNone(navigator.menu_target(frame([(reference, 250), (narrow, 650)])))

    def test_session_forwards_the_squash_to_navigation(self):
        app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        app.navigation = create_navigator(ASSETS)
        app._set_frame_squash(.93)
        self.assertEqual((app._x_squash, app.navigation.x_squash), (.93, .93))


class ShopReturnFailureTests(unittest.TestCase):
    def test_crops_and_scores_are_saved_without_the_header(self):
        app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        app._rgb = np.zeros((1080, 1920, 3), np.uint8)
        app._x_squash = .9348
        app.navigation = Mock()
        app.navigation.verification_details.return_value = 'built-in: title=0.871 (unverified); refresh=0.950 (OK)'
        with tempfile.TemporaryDirectory() as temp:
            previous = os.getcwd()
            try:
                os.chdir(temp)
                detail = E7MouseShopRefresh._shop_return_failure_detail(app, 'refresh')
                folder = next(Path('mouse-failures').iterdir())
                sizes = {}
                for path in folder.glob('*.png'):
                    with Image.open(path) as saved:
                        sizes[path.name] = saved.size
                record = json.loads((folder/'failure.json').read_text(encoding='utf-8'))
            finally:
                os.chdir(previous)
        self.assertEqual(sizes, {'refresh-label.png': (305, 150), 'dialog.png': (950, 740)})
        self.assertIn('title=0.871', detail)
        self.assertEqual((record['operation'], record['confirmation_clicked'], record['x_squash']), ('refresh shop return', True, .9348))

    def test_a_failed_save_never_hides_the_stop(self):
        app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        app._rgb = np.zeros((1080, 1920, 3), np.uint8)
        app.navigation = Mock()
        app.navigation.verification_details.return_value = 'x'
        from unittest.mock import patch
        with patch('e7_shop_flow.Path.mkdir', side_effect=OSError('read only')):
            self.assertEqual(E7MouseShopRefresh._shop_return_failure_detail(app, 'refresh'), '')


if __name__ == '__main__':
    unittest.main()
