"""Fake native input and synthetic shop/dialog tests. Never operate the desktop."""
import contextlib
import ctypes
import io
import json
import unittest
from unittest.mock import Mock, patch
import numpy as np
from PIL import Image, ImageDraw
import E7ADBShopRefresh as adb_engine
from e7_windows_capture import GameWindow
from e7_native_mouse import WindowsMouse, MouseStopped, Input, verify_native_target
from e7_mouse_refresh import E7MouseShopRefresh, confirmation_button, green_buttons
from e7_mouse_confirmation import confirmation_matches


def shop():
    return np.full((1080,1920,3),30,dtype=np.uint8)


def dialog(operation='refresh',centered=False):
    frame = shop()
    frame[300:920,550:1400] = 90
    top = 720 if operation == 'buy' else 650
    left = 830 if centered else 1040
    frame[top:top+90,left:left+250] = (20,110,40)
    return frame


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.target = GameWindow(123,456,'Epic Seven',(-3840,20,0,2039))
        self.backend = Mock()
        self.backend.inspect.return_value = self.target
        self.backend.unobstructed.return_value = True
        self.image = Image.new('RGB',(3840,2019),'#202020')
        ImageDraw.Draw(self.image).rectangle((50,50,300,300),fill='white')
        self.sender = Mock()
        self.active = True
        self.mouse = WindowsMouse(self.target,lambda:self.active,backend=self.backend,
                                  lookup=lambda _:'EpicSeven.exe',sender=self.sender,
                                  grabber=Mock(return_value=self.image))

    def test_wide_negative_monitor_coordinates_map_to_actual_client(self):
        self.mouse.screenshot(); self.mouse.click(960,540)
        self.sender.assert_called_once_with((-1920,1030),'click',0)
        self.assertEqual(self.mouse.view,self.target.rectangle)

    def test_clear_black_bars_map_back_to_cropped_client(self):
        image = Image.new('RGB',(3840,2019),'black')
        image.paste(Image.new('RGB',(3590,2019),'#808080'),(125,0))
        self.mouse.grabber.return_value = image
        self.mouse.screenshot(); self.mouse.click(0,0)
        self.sender.assert_called_once_with((-3715,20),'click',0)

    def test_focus_loss_stops_before_pointer_input(self):
        self.mouse.screenshot(); self.backend.unobstructed.return_value = False
        with self.assertRaisesRegex(MouseStopped,'focus'):
            self.mouse.click(960,540)
        self.sender.assert_not_called()

    def test_stop_key_state_stops_click_and_scroll(self):
        self.mouse.screenshot(); self.active = False
        for action in (self.mouse.click,self.mouse.scroll):
            with self.assertRaises(MouseStopped): action(960,540)
        self.sender.assert_not_called()

    def test_changed_pid_title_or_geometry_stops(self):
        self.mouse.screenshot()
        for current in (GameWindow(123,999,'Epic Seven',self.target.rectangle),
                        GameWindow(123,456,'Other title',self.target.rectangle),
                        GameWindow(123,456,'Epic Seven',(0,0,3840,2019))):
            self.backend.inspect.return_value = current
            with self.assertRaises(MouseStopped): self.mouse.click(960,540)
        self.sender.assert_not_called()

    def test_lost_focus_during_capture_discards_frame(self):
        self.backend.unobstructed.side_effect = [True,False]
        with self.assertRaises(MouseStopped): self.mouse.screenshot()
        self.assertIsNone(self.mouse.view)
        self.sender.assert_not_called()

    def test_blank_wrong_size_and_invalid_target_never_send(self):
        for image in (Image.new('RGB',(3840,2019)),Image.new('RGB',(640,360))):
            self.mouse.grabber.return_value = image
            with self.assertRaises(MouseStopped): self.mouse.screenshot()
        self.mouse.grabber.return_value = self.image; self.mouse.screenshot()
        for x,y in ((1920,1),(-1,1),(1,1080),(float('nan'),1)):
            with self.assertRaises(MouseStopped): self.mouse.click(x,y)
        self.sender.assert_not_called()

    def test_process_validation_rejects_title_spoof_and_changed_identity(self):
        with self.assertRaisesRegex(ValueError,'native STOVE'):
            verify_native_target(self.target,backend=self.backend,lookup=lambda _:'chrome.exe')
        self.backend.inspect.return_value = GameWindow(123,999,'Epic Seven',self.target.rectangle)
        with self.assertRaisesRegex(ValueError,'changed'):
            verify_native_target(self.target,backend=self.backend,lookup=lambda _:'EpicSeven.exe')

    def test_click_is_one_move_down_up_batch_and_partial_send_releases(self):
        self.mouse.screenshot()
        api = self.backend.user
        api.GetSystemMetrics.side_effect = [-3840,0,7680,2160]
        api.SendInput.return_value = 3
        self.mouse._send((-1920,1030),'click',0)
        args = api.SendInput.call_args.args
        self.assertEqual((args[0],args[2]),(3,ctypes.sizeof(Input)))
        self.assertEqual([event.value.mouse.flags for event in args[1]],[0xC001,2,4])
        api.GetSystemMetrics.side_effect = [-3840,0,7680,2160]
        api.SendInput.side_effect = [2,1]
        with self.assertRaises(MouseStopped): self.mouse._send((-1920,1030),'click',0)
        self.assertEqual(api.SendInput.call_args.args[0],1)

    def test_scroll_sends_wheel_without_held_button(self):
        self.mouse.screenshot(); self.mouse.scroll(1200,800)
        self.assertEqual(self.sender.call_args.args[1:],('wheel',-1200))


class NativeEngineTests(unittest.TestCase):
    def make_engine(self):
        app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        app.loop_active,app.end_of_refresh = True,False
        app.budget,app.tap_sleep,app.debug = 12,.3,False
        app.screenwidth,app.screenheight = 1920,1080
        app.refresh_count = 0; app.stop_refresh_key = '`'
        app.generateOffset = lambda:(0,0)
        app._rgb = shop(); app._item = None; app._item_name = None
        app.read_confirmation_text = lambda _:'Cancel Confirm Refresh Secret Shop 3 Skystone Covenant bookmark 184,000 Mystic medal 280,000'
        app.mouse = Mock()
        app.mouse.screenshot.return_value = Image.fromarray(shop())
        app.navigation = Mock()
        app.navigation.shop_visible.return_value = True
        marker = Mock(); marker.shop_visible.return_value = True
        marker.match.return_value = dict(point=(436,994))
        app.navigation.navigators = [('builtin',marker)]
        app.storage = adb_engine.E7Inventory()
        app.storage.inventory = {}
        app.storage.writeToCSV = Mock()
        return app

    def test_constructor_uses_mouse_capture_without_adb(self):
        mouse = Mock(); mouse.screenshot.return_value = Image.fromarray(shop())
        with patch.object(adb_engine.subprocess,'run') as adb:
            app = E7MouseShopRefresh(GameWindow(123,456,'Epic Seven',(0,0,3840,2019)),transport=mouse,
                                    budget=12,tap_sleep=.3,stop_refresh_key='`',random_offset=True)
        adb.assert_not_called()
        self.assertEqual((app.screenwidth,app.screenheight),(1920,1080))

    def test_normal_shop_buttons_and_centered_ack_are_not_confirmation(self):
        frame = shop(); frame[700:790,1550:1800] = (20,110,40)
        self.assertIsNone(confirmation_button(frame,'refresh',shop()))
        self.assertIsNone(confirmation_button(dialog(centered=True),'refresh',shop()))
        self.assertIsNotNone(confirmation_button(dialog(),'refresh',shop()))
        self.assertIsNotNone(confirmation_button(dialog('buy'),'buy',shop()))

    def test_refresh_uses_recognized_label_then_observed_confirmation(self):
        app = self.make_engine()
        app.mouse.screenshot.side_effect = [Image.fromarray(frame) for frame in (shop(),dialog(),dialog(),shop())]
        with patch('e7_mouse_refresh.time.sleep'),patch.object(adb_engine.subprocess,'run') as adb:
            self.assertTrue(app.clickRefresh())
        adb.assert_not_called()
        self.assertEqual(app.mouse.click.call_args_list[0].args,(436,994))
        self.assertEqual(app.mouse.click.call_args_list[1].args,(1165,695))
        self.assertEqual(app.refresh_count,0)  # Only the shared loop increments.

    def test_missing_confirmation_stops_after_one_refresh_click(self):
        app = self.make_engine()
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,6]):
            with self.assertRaisesRegex(MouseStopped,'No confirmation click'):
                app.clickRefresh()
        self.assertEqual(app.mouse.click.call_count,1)
        self.assertEqual(app.refresh_count,0)

    def test_stop_between_click_and_confirmation_sends_no_second_click(self):
        app = self.make_engine()
        app.mouse.click.side_effect = lambda *_:setattr(app,'loop_active',False)
        self.assertFalse(app.clickRefresh())
        self.assertEqual(app.mouse.click.call_count,1)

    def test_random_offsets_are_clamped_inside_observed_button(self):
        app = self.make_engine(); app.generateOffset = lambda:(500,-500)
        app._click_button((1000,650,1200,730))
        self.assertEqual(app.mouse.click.call_args.args,(1150,670))

    def test_native_buy_matches_item_and_observed_button(self):
        app = self.make_engine()
        template = np.random.default_rng(7).integers(20,240,(40,40),dtype=np.uint8)
        app.storage.inventory['Covenant bookmark'] = adb_engine.E7Item(template,184000)
        frame = shop(); frame[200:240,800:840] = template[:,:,None]
        frame[220:300,1550:1810] = (20,110,40)
        app._rgb = frame
        pos = app.findItemPosition(cv_gray(frame),template)
        self.assertEqual(pos,(1680,260))
        app.mouse.screenshot.side_effect = [Image.fromarray(image) for image in (frame,dialog('buy'),dialog('buy'),shop())]
        with patch('e7_mouse_refresh.time.sleep'),patch.object(adb_engine.subprocess,'run') as adb:
            self.assertTrue(app.clickBuy(pos))
        adb.assert_not_called()
        self.assertEqual(app.mouse.click.call_args_list[0].args,pos)

    def test_shared_loop_enforces_four_refreshes_for_twelve_skystones(self):
        app = self.make_engine()
        state = ['shop']
        def screenshot(): return Image.fromarray(dialog() if state[0]=='confirm' else shop())
        def click(x,y): state[0] = 'confirm' if y>900 else 'shop'
        app.mouse.screenshot.side_effect = screenshot
        app.mouse.click.side_effect = click
        with patch.object(adb_engine.time,'sleep'),patch.object(adb_engine.subprocess,'run') as adb, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            app.refreshShop()
        adb.assert_not_called()
        self.assertEqual(app.refresh_count,4)
        self.assertEqual(app.mouse.click.call_count,8)
        self.assertEqual(app.mouse.scroll.call_count,5)
        stats = [json.loads(line.split(' ',1)[1]) for line in output.getvalue().splitlines() if line.startswith('E7GUI_STATS ')]
        self.assertEqual(stats[-1]['skystone_spent'],12)
        app.storage.writeToCSV.assert_called_once()

    def test_insufficient_currency_or_wrong_confirmation_never_receives_second_click(self):
        for text in ('Not enough Skystone. Cancel Confirm Refresh 3 Skystone',
                     'Cancel Confirm Purchase Skystone', 'Cancel Confirm Covenant 184,000', ''):
            app = self.make_engine()
            app.read_confirmation_text = lambda _,text=text:text
            app.mouse.screenshot.side_effect = [Image.fromarray(shop()),Image.fromarray(dialog())]
            with patch('e7_mouse_refresh.time.sleep'):
                with self.assertRaisesRegex(MouseStopped,'does not match'):
                    app.clickRefresh()
            self.assertEqual(app.mouse.click.call_count,1)

    def test_confirmation_changing_during_ocr_is_not_clicked(self):
        app = self.make_engine()
        app.mouse.screenshot.side_effect = [Image.fromarray(image) for image in (shop(),dialog(),shop())]
        with patch('e7_mouse_refresh.time.sleep'):
            with self.assertRaisesRegex(MouseStopped,'changed while'):
                app.clickRefresh()
        self.assertEqual(app.mouse.click.call_count,1)

    def test_stop_during_ocr_prevents_another_capture_and_click(self):
        app = self.make_engine()
        app.mouse.screenshot.side_effect = [Image.fromarray(shop()),Image.fromarray(dialog())]
        def read(_):
            app.loop_active = False
            return 'Cancel Confirm Refresh 3 Skystone'
        app.read_confirmation_text = read
        with patch('e7_mouse_refresh.time.sleep'):
            self.assertFalse(app.clickRefresh())
        self.assertEqual(app.mouse.screenshot.call_count,2)
        self.assertEqual(app.mouse.click.call_count,1)

    def test_confirmation_text_requires_matching_item_price_and_currency(self):
        self.assertTrue(confirmation_matches('Cancel Confirm Refresh 3 Skystone','refresh'))
        self.assertFalse(confirmation_matches('Cancel Confirm Refresh 30 Skystone','refresh'))
        self.assertTrue(confirmation_matches('Cancel Confirm Covenant Bookmark 184,000','buy','Covenant bookmark'))
        self.assertFalse(confirmation_matches('Cancel Confirm Mystic Medal 184,000','buy','Covenant bookmark'))
        self.assertFalse(confirmation_matches('Cancel Confirm Covenant Bookmark 280,000','buy','Covenant bookmark'))


def cv_gray(rgb):
    import cv2
    return cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)


if __name__ == '__main__':
    unittest.main()
