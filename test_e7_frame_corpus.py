"""Recognition regressions: synthetic cases plus the private real-frame corpus.

Never accesses a game. The corpus runs only when its private frames exist
(E7_FRAME_CORPUS or .local-state/frame-corpus); see check_frame_corpus.py.
"""
import contextlib, io, os, unittest
from pathlib import Path
import cv2
import numpy as np
import check_frame_corpus
from e7_shop_flow import TEXT_LEFT, currency_button, home_icon_target

CORPUS = Path(os.environ.get('E7_FRAME_CORPUS', '.local-state/frame-corpus'))


class TintAndFramingTests(unittest.TestCase):
    def icon_frame(self, tint):
        icon = cv2.imread('adb-assets/builtin-navigation/native-secret-shop-icon.png', cv2.IMREAD_GRAYSCALE)
        rgb = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        h, w = icon.shape
        top, left = 470-h//2, 85-w//2
        rgb[top:top+h, left:left+w][icon > 127] = 245
        return np.clip(rgb*np.array(tint), 0, 255).astype(np.uint8)

    def test_secret_shop_icon_is_found_under_a_warm_display_tint(self):
        # Caption below the icon, as on the native home menu.
        for tint in ((1, 1, 1), (1, .73, .44)):
            target = home_icon_target(self.icon_frame(tint), (85, 540))
            self.assertIsNotNone(target, tint)
            self.assertLess(abs(target[0]-85)+abs(target[1]-470), 12, tint)

    def test_currency_text_slightly_left_of_the_old_edge_still_pairs(self):
        # A client framed the list ~7px further left than the old 1010 edge.
        self.assertLess(TEXT_LEFT, 1003)
        result = dict(words=[dict(text='currency', box=[1003, 649, 1116, 681]),
                             dict(text='friendship', box=[1006, 693, 1169, 733]),
                             dict(text='points', box=[1180, 694, 1278, 725]),
                             dict(text='1/1', box=[1612, 735, 1650, 764]),
                             dict(text='18,000', box=[1718, 655, 1809, 685]),
                             dict(text='buy', box=[1729, 732, 1778, 766])])
        label = currency_button(result, [(1560, 712, 1830, 790)], 'Friendship points')
        self.assertEqual(tuple(label), (1729, 732, 1778, 766))


@unittest.skipUnless((CORPUS/'frames.json').is_file(), 'Private real-frame corpus not supplied')
class RealFrameCorpusTests(unittest.TestCase):
    def test_every_labelled_frame_including_display_tint_variants(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = check_frame_corpus.main(['--corpus', str(CORPUS), '--variants'])
        failures = [line for line in output.getvalue().splitlines() if line.startswith('FAIL')]
        self.assertEqual(code, 0, '\n'.join(failures))


if __name__ == '__main__':
    unittest.main()
