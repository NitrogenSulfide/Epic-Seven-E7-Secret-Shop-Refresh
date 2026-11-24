import os
"""Fake native input and synthetic shop/dialog tests. Never operate the desktop."""
import contextlib
import gc
import ctypes
import io
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
import cv2
from PIL import Image, ImageDraw
import E7ADBShopRefresh as adb_engine
from e7_windows_capture import GameWindow
from e7_native_mouse import WindowsMouse, MouseStopped, MouseRecheckRequired, Input, verify_native_target, physical_pixel_coordinates, process_is_elevated, require_mouse_permissions, pointer_glide
from e7_mouse_refresh import E7MouseShopRefresh, confirmation_button, green_buttons, home_menu_target, home_icon_target, native_home_control_target, hidden_home_matches, reframed_home_matches, idle_home_candidate, currency_button, IncompleteCurrencyRow, inspect_mouse_items
from e7_mouse_confirmation import confirmation_matches


class FriendshipSessionTests(unittest.TestCase):
    def test_mouse_cli_passes_friendship_selection_to_shared_engine(self):
        from e7_mouse_refresh import run_mouse_session
        window=json.dumps(dict(handle=123,pid=456,title='fake',rectangle=[0,0,1920,1080]))
        arguments=['--mouse-session',window,'--budget','3','--delay','.3','--stop-key','esc','--random-offset','no','--buy-friendship']
        with patch('e7_mouse_refresh.E7MouseShopRefresh') as engine,patch('e7_mouse_refresh.threading.Thread'),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_mouse_session(arguments),0)
        self.assertTrue(engine.call_args.kwargs['buy_friendship'])
        engine.return_value.start.assert_called_once()


def shop():
    return np.full((1080,1920,3),30,dtype=np.uint8)


def scrolled(frame=None):
    """The shop after a drag: the item list shows other rows."""
    frame = shop() if frame is None else frame.copy()
    frame[110:1080,760:1480] = 60
    return frame


def dialog(operation='refresh',centered=False):
    frame = shop()
    frame[300:920,550:1400] = 90
    top = 720 if operation == 'buy' else 650
    left = 830 if centered else 1040
    frame[top:top+90,left:left+250] = (20,110,40)
    return frame


def currency_words(name,offset=0,price=None):
    prefix,noun,normal_price = {'Covenant bookmark':('covenant','bookmarks','184,000'),
                              'Mystic medal':('mystic','medals','280,000'),
                              'Friendship points':('friendship','points','18,000')}[name]
    category='currency' if name=='Friendship points' else 'summon'
    fields = [(category,[1035,155,1135,180]),(prefix,[1035,205,1160,237]),
              (noun,[1170,205,1335,237]),(price or normal_price,[1684,168,1786,199]),
              ('buy',[1711,244,1757,276]),('only',[1035,255,1085,285]),
              ('1',[1094,255,1103,285]),('available',[1114,255,1220,285])]
    return [dict(text=text,box=[box[0],box[1]+offset,box[2],box[3]+offset]) for text,box in fields]


class CurrencyRowTests(unittest.TestCase):
    def test_each_currency_requires_its_own_name_price_category_and_buy(self):
        for name in ('Covenant bookmark','Mystic medal','Friendship points'):
            words=currency_words(name)
            self.assertEqual(currency_button(dict(words=words),[(1550,220,1810,300)],name),(1711,244,1757,276))
            for omitted in ('currency' if name=='Friendship points' else 'summon','buy'):
                with self.subTest(name=name,omitted=omitted),self.assertRaises(MouseStopped):
                    currency_button(dict(words=[word for word in words if word['text']!=omitted]),[(1550,220,1810,300)],name)

    def test_friendship_wrong_price_and_incomplete_lower_row_are_rejected(self):
        with self.assertRaisesRegex(MouseStopped,'same row'):
            currency_button(dict(words=currency_words('Friendship points',price='184,000')),[(1550,220,1810,300)],'Friendship points')
        with self.assertRaises(IncompleteCurrencyRow):
            currency_button(dict(words=currency_words('Friendship points',offset=820)),[],'Friendship points')

    def test_wrong_price_or_price_on_another_row_is_rejected(self):
        for price,shift in (('184,000',0),('280,000',430)):
            words=currency_words('Mystic medal',price=price)
            for word in words:
                if word['text']==price:word['box'][1]+=shift;word['box'][3]+=shift
            with self.assertRaisesRegex(MouseStopped,'same row'):
                currency_button(dict(words=words),[(1550,220,1810,300)],'Mystic medal')

    def test_ambiguous_or_incomplete_name_is_rejected(self):
        words=currency_words('Mystic medal')
        for altered in (words+currency_words('Mystic medal',430),[word for word in words if word['text']!='medals']):
            with self.assertRaises(MouseStopped):currency_button(dict(words=altered),[(1550,220,1810,300)],'Mystic medal')

    def test_names_outside_item_column_and_other_currencies_are_ignored(self):
        words=currency_words('Mystic medal')
        for word in words:word['box'][0]-=600;word['box'][2]-=600
        self.assertIsNone(currency_button(dict(words=words),[(1550,220,1810,300)],'Mystic medal'))
        self.assertIsNone(currency_button(dict(words=currency_words('Mystic medal')),[(1550,220,1810,300)],'Covenant bookmark'))

    def test_sold_out_row_is_ignored_only_when_no_active_buy_is_observed(self):
        for name in ('Covenant bookmark','Mystic medal','Friendship points'):
            words=currency_words(name)
            for word in words:
                if word['text']=='1':word['text']='0'
            with self.subTest(name=name):
                self.assertIsNone(currency_button(dict(words=words),[],name))
                self.assertIsNotNone(currency_button(dict(words=words),[(1550,220,1810,300)],name))

    def test_available_buy_wins_over_purchased_text_for_every_currency(self):
        for name in ('Covenant bookmark','Mystic medal','Friendship points'):
            for status in ('Purchased','Sold Out'):
                words=currency_words(name)+[dict(text=status,box=[1370,255,1470,285])]
                with self.subTest(name=name,status=status):
                    self.assertEqual(currency_button(dict(words=words),[(1550,220,1810,300)],name),(1711,244,1757,276))

    def test_observed_zero_stock_overrides_retained_buy_and_only_one_available(self):
        for name in ('Covenant bookmark','Mystic medal','Friendship points'):
            for buttons in ([],[(1550,220,1810,300)]):
                words=currency_words(name)+[dict(text='0/1',box=[1580,243,1628,276])]
                with self.subTest(name=name,buttons=buttons):
                    self.assertIsNone(currency_button(dict(words=words),buttons,name))
                words[-1]['text']='1/1'
                if buttons:self.assertIsNotNone(currency_button(dict(words=words),buttons,name))
                else:
                    with self.assertRaises(MouseStopped):currency_button(dict(words=words),buttons,name)

    def test_zero_stock_requires_full_same_row_name_category_price_and_buy(self):
        for name in ('Covenant bookmark','Mystic medal','Friendship points'):
            words=currency_words(name)+[dict(text='0/1',box=[1580,243,1628,276])]
            for omit in ('buy','currency' if name=='Friendship points' else 'summon',{'Covenant bookmark':'184,000','Mystic medal':'280,000','Friendship points':'18,000'}[name]):
                with self.subTest(name=name,omit=omit),self.assertRaises(MouseStopped):
                    currency_button(dict(words=[word for word in words if word['text']!=omit]),[(1550,220,1810,300)],name)

    def test_unrelated_zero_and_other_row_stock_do_not_hide_available_currencies(self):
        for name in ('Covenant bookmark','Mystic medal','Friendship points'):
            for text,box in [('0',[1580,243,1628,276]),('01',[1580,243,1628,276]),('0/2',[1580,243,1628,276]),('10/1',[1580,243,1628,276]),('0/1',[1580,673,1628,706]),('0/1',[1050,243,1098,276]),('0/1',[1580,165,1628,198])]:
                words=currency_words(name)+[dict(text=text,box=box)]
                with self.subTest(name=name,text=text,box=box):
                    self.assertIsNotNone(currency_button(dict(words=words),[(1550,220,1810,300)],name))

    def test_conflicting_stock_insets_stop_instead_of_discarding_an_available_row(self):
        for name in ('Covenant bookmark','Mystic medal','Friendship points'):
            words=currency_words(name)+[dict(text='0/1',box=[1530,243,1578,276]),dict(text='1/1',box=[1600,243,1648,276])]
            with self.subTest(name=name),self.assertRaisesRegex(MouseStopped,'stock is ambiguous'):
                currency_button(dict(words=words),[(1500,220,1810,300)],name)

    def test_stock_split_into_touching_pieces_is_read_as_one_fraction(self):
        from e7_shop_flow import button_stock
        label=(1711,244,1757,276)
        splits={'1':[('1',[1580,243,1592,276]),('/1',[1594,243,1628,276])],
                '1 three':[('1',[1580,243,1592,276]),('/',[1594,243,1604,276]),('1',[1606,243,1628,276])],
                '0':[('0',[1580,243,1592,276]),('/1',[1594,243,1628,276])],
                '0 trailing':[('0/',[1580,243,1606,276]),('1',[1608,243,1628,276])],
                '1 near buy':[('1',[1660,243,1672,276]),('/1',[1674,243,1701,276])]}  # 10 px from Buy
        for key,pieces in splits.items():
            stock=int(key[0])
            for name in ('Covenant bookmark','Mystic medal','Friendship points'):
                words=currency_words(name)+[dict(text=text,box=box) for text,box in pieces]
                with self.subTest(split=key,name=name):
                    self.assertEqual(button_stock(dict(words=words),label),stock)
                    result=currency_button(dict(words=words),[(1550,220,1810,300)],name)
                    self.assertEqual(result,None if stock==0 else label)

    def test_stock_pieces_that_do_not_touch_on_one_line_are_not_joined(self):
        from e7_shop_flow import button_stock
        label=(1711,244,1757,276)
        for pieces in ([('1',[1520,243,1532,276]),('/1',[1594,243,1628,276])],   # wide gap
                       [('1',[1580,213,1592,246]),('/1',[1594,243,1628,276])],   # other line
                       [('1',[1580,243,1592,276]),('/2',[1594,243,1628,276])],   # not x/1
                       [('1',[1580,243,1592,276]),('/1',[1594,243,1628,276]),('1',[1630,243,1640,276])],  # "1/11"
                       [('0',[1580,225,1592,258]),('/',[1594,234,1604,267]),('1',[1606,243,1618,276])]):  # drifts off one line
            words=currency_words('Friendship points')+[dict(text=text,box=box) for text,box in pieces]
            with self.subTest(pieces=pieces):
                self.assertIsNone(button_stock(dict(words=words),label))

    def test_row_retry_keeps_a_split_zero_stock_from_the_whole_list(self):
        from e7_shop_flow import retain_row_stock
        original=dict(words=[*currency_words('Friendship points'),dict(text='0',box=[1580,243,1592,276]),
                             dict(text='/1',box=[1594,243,1628,276])])
        merged=retain_row_stock(original,dict(words=currency_words('Friendship points')),(1711,244,1757,276))
        self.assertIsNone(currency_button(merged,[(1550,220,1810,300)],'Friendship points'))

    def test_row_retry_retains_stock_only_for_matching_buy_and_rejects_conflicts(self):
        from e7_shop_flow import retain_row_stock
        for name in ('Covenant bookmark','Mystic medal','Friendship points'):
            original=dict(words=[*currency_words(name),dict(text='0/1',box=[1580,243,1628,276])])
            row=dict(words=currency_words(name))
            merged=retain_row_stock(original,row,(1711,244,1757,276))
            self.assertIsNone(currency_button(merged,[(1550,220,1810,300)],name))
            conflicting=dict(words=[*row['words'],dict(text='1/1',box=[1580,243,1628,276])])
            with self.assertRaisesRegex(MouseStopped,'stock is ambiguous'):
                retain_row_stock(original,conflicting,(1711,244,1757,276))
            moved=dict(words=[dict(text=word['text'],box=[v+15 if i%2==0 else v for i,v in enumerate(word['box'])]) for word in row['words']])
            with self.assertRaisesRegex(MouseStopped,'stock is ambiguous'):
                retain_row_stock(original,moved,(1711,244,1757,276))
            self.assertEqual(len(row['words']),len(currency_words(name)))

    def test_purchased_button_area_is_ignored_for_all_currencies_in_a_new_session(self):
        for name in ('Friendship points','Covenant bookmark','Mystic medal'):
            for label in ('Purchased','Sold Out','SoldOut'):
                with self.subTest(name=name,label=label):
                    words=[word for word in currency_words(name) if word['text'] not in ('buy','18,000','184,000','280,000','only','1','available')]
                    words.append(dict(text=label,box=[1590,245,1790,277]))
                    self.assertIsNone(currency_button(dict(words=words),[],name))

    def test_purchased_label_on_other_row_or_unknown_missing_buy_is_not_ignored(self):
        words=[word for word in currency_words('Friendship points') if word['text']!='buy']
        for status in ([],[dict(text='Purchased',box=[1590,675,1790,707])]):
            with self.subTest(status=status),self.assertRaisesRegex(MouseStopped,'same row'):
                currency_button(dict(words=words+status),[],'Friendship points')


class PointerGlideTests(unittest.TestCase):
    def test_path_eases_without_overshooting_and_reaches_exact_target(self):
        path = pointer_glide((-1920,200),(-200,1000))
        points = [(-1920,200)]+[point for point,_ in path]
        self.assertEqual(points[-1],(-200,1000))
        distances = [np.linalg.norm(np.subtract(b,a)) for a,b in zip(points,points[1:])]
        self.assertLess(distances[0],max(distances)/4)
        self.assertLess(distances[-1],max(distances)/4)
        self.assertLess(max(distances),200)
        self.assertTrue(all(a[0]<=b[0] and a[1]<=b[1] for a,b in zip(points,points[1:])))
        self.assertTrue(all(0<t<=.38 for _,t in path))

    def test_display_scale_preserves_duration_and_stationary_target_is_immediate(self):
        normal = pointer_glide((0,0),(1200,800))
        large = pointer_glide((0,0),(2400,1600),2)
        self.assertEqual([t for _,t in normal],[t for _,t in large])
        self.assertEqual(pointer_glide((-200,100),(-200,100)),[((-200,100),0)])


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

    def test_maximized_native_client_passes_full_mouse_recognition_capture(self):
        app=E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        app.mouse=self.mouse
        self.assertEqual(app.takeScreenshot().shape,(1080,1920))
        self.assertEqual(self.mouse.view,self.target.rectangle)
        app.tap(960,540)
        self.sender.assert_called_once_with((-1920,1030),'click',0)

    def test_wide_client_opt_in_uses_process_identity_not_title(self):
        mouse=WindowsMouse(self.target,lambda:True,backend=self.backend,
                           lookup=lambda _:'crosvm.exe',sender=self.sender,
                           grabber=Mock(return_value=self.image))
        app=E7MouseShopRefresh.__new__(E7MouseShopRefresh);app.mouse=mouse
        with self.assertRaises(MouseStopped):app.takeScreenshot()
        self.sender.assert_not_called()

    def test_clear_black_bars_map_back_to_cropped_client(self):
        image = Image.new('RGB',(3840,2019),'black')
        image.paste(Image.new('RGB',(3590,2019),'#808080'),(125,0))
        self.mouse.grabber.return_value = image
        self.mouse.screenshot(); self.mouse.click(0,0)
        self.sender.assert_called_once_with((-3715,20),'click',0)

    def test_focus_loss_stops_before_pointer_input(self):
        self.mouse.screenshot(); self.backend.unobstructed.return_value = False
        with patch('e7_native_mouse.time.sleep'),patch('e7_native_mouse.time.monotonic',side_effect=[0,0,11]):
            with self.assertRaisesRegex(MouseStopped,'focus'):
                self.mouse.click(960,540)
        self.sender.assert_not_called()

    def test_stop_key_state_stops_click_and_scroll(self):
        self.mouse.screenshot(); self.active = False
        for action in (lambda:self.mouse.click(960,540),lambda:self.mouse.drag(1200,800,1200,390)):
            with self.assertRaises(MouseStopped): action()
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
        self.backend.unobstructed.side_effect = [True,False,False]
        with patch('e7_native_mouse.time.sleep'),patch('e7_native_mouse.time.monotonic',side_effect=[0,0,11]):
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

    def test_one_blank_capture_is_taken_again_before_stopping(self):
        # A fade or loading frame can be blank for a moment.
        self.mouse.grabber.side_effect = [Image.new('RGB',(3840,2019)),self.image]
        with patch('e7_native_mouse.time.sleep') as slept:
            self.mouse.screenshot()
        slept.assert_called_once_with(.5)
        self.assertEqual(self.mouse.grabber.call_count,2)
        self.sender.assert_not_called()

    def test_selected_client_is_not_restricted_to_stove_but_identity_is_verified(self):
        for process in ('EpicSeven.exe','crosvm.exe','HD-Player.exe','MuMuPlayer.exe'):
            self.assertEqual(verify_native_target(self.target,backend=self.backend,lookup=lambda _:process),self.target)
        with self.assertRaisesRegex(ValueError,'verify'):
            verify_native_target(self.target,backend=self.backend,lookup=lambda _:'')
        self.backend.inspect.return_value = GameWindow(123,999,'Epic Seven',self.target.rectangle)
        with self.assertRaisesRegex(ValueError,'changed'):
            verify_native_target(self.target,backend=self.backend,lookup=lambda _:'EpicSeven.exe')

    def test_google_custom_title_bar_is_excluded_from_physical_click_mapping(self):
        target=GameWindow(123,456,'Google Play Games on PC Emulator',(150,0,2710,1512))
        self.backend.inspect.return_value=target
        frame=Image.new('RGB',(2560,1512),(0,0,0))
        ImageDraw.Draw(frame).rectangle((20,20,380,40),fill='white')
        frame.paste(Image.new('RGB',(2560,1440),(80,90,100)),(0,72))
        mouse=WindowsMouse(target,lambda:True,backend=self.backend,grabber=Mock(return_value=frame),lookup=lambda _:'crosvm.exe',sender=self.sender)
        self.assertEqual(mouse.screenshot().size,(2560,1440))
        mouse.click(960,540)
        self.sender.assert_called_once_with((1430,792),'click',0)

    def test_google_dialog_dimming_keeps_startup_crop_and_resize_still_stops(self):
        target=GameWindow(123,456,'Google Play Games on PC Emulator',(150,0,2710,1512))
        self.backend.inspect.return_value=target
        frame=Image.new('RGB',(2560,1512))
        ImageDraw.Draw(frame).rectangle((20,20,380,40),fill='white')
        frame.paste(Image.new('RGB',(2560,1440),(80,90,100)),(0,72))
        grabber=Mock(return_value=frame)
        mouse=WindowsMouse(target,lambda:True,backend=self.backend,grabber=grabber,lookup=lambda _:'crosvm.exe',sender=self.sender)
        self.assertEqual(mouse.screenshot().size,(2560,1440))
        dark=frame.copy();dark.paste(Image.new('RGB',(2560,1440),(12,16,20)),(0,72))
        ImageDraw.Draw(dark).rectangle((1400,920,1800,1040),fill=(30,80,130))
        grabber.return_value=dark
        self.assertEqual(mouse.screenshot().size,(2560,1440))
        self.assertEqual(mouse.view,(150,72,2710,1512))
        mouse.click(960,540)
        self.sender.assert_called_once_with((1430,792),'click',0)
        self.sender.reset_mock()
        self.backend.inspect.return_value=GameWindow(123,456,target.title,(150,0,2610,1512))
        with self.assertRaisesRegex(MouseStopped,'resized'):
            mouse.screenshot()
        self.sender.assert_not_called()

    def test_elevated_game_requires_matching_app_permissions_before_input(self):
        with patch('e7_native_mouse.process_is_elevated',side_effect=[True,False]),self.assertRaisesRegex(ValueError,'Run as administrator'):
            require_mouse_permissions(self.target)
        with patch('e7_native_mouse.process_is_elevated',side_effect=[True,True]):
            require_mouse_permissions(self.target)
        with patch('e7_native_mouse.process_is_elevated',return_value=False) as check:
            require_mouse_permissions(self.target)
            check.assert_called_once_with(self.target.pid)
        self.sender.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows API test')

    def test_permission_token_handles_close_on_success_and_failure(self):
        kernel,security=Mock(),Mock();kernel.OpenProcess.return_value=789
        def open_token(process,access,token):
            token._obj.value=321
            return True
        def information(token,kind,flag,size,result):
            flag._obj.value=1
            return True
        security.OpenProcessToken.side_effect=open_token
        security.GetTokenInformation.side_effect=information
        self.assertTrue(process_is_elevated(456,kernel=kernel,security=security))
        self.assertEqual(kernel.CloseHandle.call_count,2)
        kernel.reset_mock();security.GetTokenInformation.side_effect=None;security.GetTokenInformation.return_value=False
        with self.assertRaisesRegex(ValueError,'Could not verify'):
            process_is_elevated(456,kernel=kernel,security=security)
        self.assertEqual(kernel.CloseHandle.call_count,2)

    def prepare_input_api(self):
        self.mouse.screenshot()
        api = self.backend.user
        api.GetSystemMetrics.side_effect = [-3840,0,7680,2160]
        api.SendInput.return_value = 1
        def position(pointer):
            pointer._obj.x,pointer._obj.y=-1920,1030
            return True
        api.GetCursorPos.side_effect=position
        return api

    def test_click_moves_verifies_then_holds_across_frames_and_releases(self):
        api=self.prepare_input_api()
        flags=[]
        api.SendInput.side_effect=lambda count,event,size:flags.append(event._obj.value.mouse.flags) or 1
        with patch('e7_native_mouse.time.sleep') as sleep:
            self.mouse._send((-1920,1030),'click',0)
        self.assertEqual(flags,[0xC001,2,4])
        self.assertEqual([call.args[0] for call in sleep.call_args_list],[.05,.08])
        api.SetCursorPos.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows API test')

    def test_failed_movement_blocks_down_and_confirmation(self):
        api=self.prepare_input_api();position=api.GetCursorPos.side_effect
        reads=iter((True,False))
        api.GetCursorPos.side_effect=lambda pointer:position(pointer) if next(reads) else False
        api.SetCursorPos.return_value=False
        with patch('e7_native_mouse.time.sleep'),self.assertRaisesRegex(MouseStopped,'No click sent'):
            self.mouse._send((-1920,1030),'click',0)
        self.assertEqual(api.SendInput.call_count,1)

    def test_direct_position_fallback_must_reach_the_target(self):
        api=self.prepare_input_api();position=api.GetCursorPos.side_effect
        reads=iter((True,False,False))
        api.GetCursorPos.side_effect=lambda pointer:position(pointer) if next(reads) else False
        with patch('e7_native_mouse.time.sleep'),self.assertRaisesRegex(MouseStopped,'place the pointer'):
            self.mouse._send((-1920,1030),'click',0)
        api.SetCursorPos.assert_called_once_with(-1920,1030)
        self.assertEqual(api.SendInput.call_count,1)
        api.reset_mock();api.GetSystemMetrics.side_effect=[-3840,0,7680,2160]
        reads=iter((True,False,True))
        api.GetCursorPos.side_effect=lambda pointer:position(pointer) if next(reads) else False
        with patch('e7_native_mouse.time.sleep'):
            self.mouse._send((-1920,1030),'click',0)
        self.assertEqual(api.SendInput.call_count,3)

    def test_stop_or_exception_while_held_always_releases(self):
        for failure in (False,True):
            self.active=True
            api=self.prepare_input_api();flags=[]
            api.SendInput.side_effect=lambda count,event,size:flags.append(event._obj.value.mouse.flags) or 1
            def sleep(delay):
                if delay==.08:
                    self.active=False
                    if failure: raise RuntimeError('interrupted')
            self.active=True
            with patch('e7_native_mouse.time.sleep',side_effect=sleep),self.assertRaises((MouseStopped,RuntimeError)):
                self.mouse._send((-1920,1030),'click',0)
            self.assertEqual(flags[-1],4)
            api.SendInput.side_effect=None

    def test_failed_down_still_sends_release(self):
        api=self.prepare_input_api();api.SendInput.side_effect=[1,0,1]
        with patch('e7_native_mouse.time.sleep'),self.assertRaisesRegex(MouseStopped,'mouse-down'):
            self.mouse._send((-1920,1030),'click',0)
        self.assertEqual(api.SendInput.call_count,3)

    def test_click_glides_before_down_and_stop_during_glide_sends_no_click(self):
        for stop in (False,True):
            self.active=True
            api=self.prepare_input_api();target_position=api.GetCursorPos.side_effect
            calls=[]
            def position(pointer):
                if not calls:
                    pointer._obj.x,pointer._obj.y=-3700,100
                    return True
                return target_position(pointer)
            def send(count,event,size):
                value=event._obj.value.mouse
                calls.append((value.flags,value.dx,value.dy))
                if stop and len(calls)==3: self.active=False
                return 1
            api.GetCursorPos.side_effect=position;api.SendInput.side_effect=send
            with patch('e7_native_mouse.time.sleep'):
                if stop:
                    with self.assertRaises(MouseStopped): self.mouse._send((-1920,1030),'click',0)
                    self.assertEqual([flag for flag,_,_ in calls],[0xC001]*3)
                else:
                    self.mouse._send((-1920,1030),'click',0)
                    self.assertGreater(len(calls),10)
                    self.assertEqual([flag for flag,_,_ in calls[-2:]],[2,4])
                    self.assertTrue(all(flag==0xC001 for flag,_,_ in calls[:-2]))
                    self.assertLess(calls[0][1],calls[-3][1])

    def test_unreadable_initial_cursor_sends_no_input(self):
        api=self.prepare_input_api();api.GetCursorPos.side_effect=None;api.GetCursorPos.return_value=False
        with self.assertRaisesRegex(MouseStopped,'read the pointer'):
            self.mouse._send((-1920,1030),'click',0)
        api.SendInput.assert_not_called()

    def test_failed_release_is_retried_before_returning(self):
        api=self.prepare_input_api();api.SendInput.side_effect=[1,1,0,1]
        with patch('e7_native_mouse.time.sleep'):
            self.mouse._send((-1920,1030),'click',0)
        self.assertEqual(api.SendInput.call_count,4)

    def test_capture_after_post_grab_pause_is_fresh(self):
        fresh=self.image.copy();ImageDraw.Draw(fresh).rectangle((400,400,500,500),fill='red')
        self.mouse.grabber.side_effect=[self.image,fresh]
        self.backend.unobstructed.side_effect=[True,False,True,True,True]
        with patch('e7_native_mouse.time.sleep'):
            result=self.mouse.screenshot()
        self.assertEqual(result.getpixel((450,450)),(255,0,0))
        self.assertEqual(self.mouse.grabber.call_count,2)
        self.sender.assert_not_called()

    def test_drag_maps_both_endpoints_on_negative_monitor(self):
        self.mouse.screenshot();self.mouse.drag(1200,800,1202,390,duration=.3)
        self.sender.assert_called_once_with(self.mouse._point(1200,800),'drag',(self.mouse._point(1202,390),.3))

    def test_invalid_drag_endpoint_duration_or_covered_destination_sends_nothing(self):
        self.mouse.screenshot()
        for args,delay in (((1200,800,1200,-1),.3),((1200,800,1200,390),0),((1200,800,1200,390),float('nan'))):
            with self.assertRaises(MouseStopped):self.mouse.drag(*args,duration=delay)
        self.backend.point_visible.return_value=False
        with patch('e7_native_mouse.time.monotonic',side_effect=[0,11]),patch('e7_native_mouse.time.sleep'):
            with self.assertRaises(MouseStopped):self.mouse.drag(1200,800,1200,390)
        self.sender.assert_not_called()

    def drag_api(self):
        api=self.prepare_input_api()
        state=dict(pointer=(-1920,1030),held=False,moves=[],flags=[])
        def position(pointer):
            pointer._obj.x,pointer._obj.y=state['pointer']
            return True
        def send(count,event,size):
            value=event._obj.value.mouse
            state['flags'].append(value.flags)
            if value.flags==2:state['held']=True
            elif value.flags==4:state['held']=False
            else:
                state['pointer']=(round(-3840+value.dx*7679/65535),round(value.dy*2159/65535))
                if state['held']:state['moves'].append(state['pointer'])
            return 1
        api.GetCursorPos.side_effect=position;api.SendInput.side_effect=send
        return api,state,send

    def test_drag_holds_during_eased_travel_then_releases_without_wheel(self):
        api,state,_=self.drag_api()
        with patch('e7_native_mouse.time.sleep'):
            self.mouse._send((-1920,1030),'drag',((-1914,400),.32))
        self.assertEqual(state['flags'].count(2),1)
        self.assertEqual(state['flags'].count(4),1)
        self.assertEqual(state['flags'][-1],4)
        self.assertNotIn(0x800,state['flags'])
        self.assertFalse(state['held'])
        self.assertGreater(len(state['moves']),10)
        self.assertLessEqual(max(abs(a-b) for a,b in zip(state['moves'][-1],(-1914,400))),1)
        self.assertTrue(all(a[1]>=b[1] for a,b in zip(state['moves'],state['moves'][1:])))
        api.SetCursorPos.assert_not_called()

    def test_drag_stop_focus_geometry_or_input_failure_releases_immediately(self):
        for failure in ('stop','focus','geometry','rejected','exception'):
            with self.subTest(failure=failure):
                self.active=True;self.backend.inspect.return_value=self.target;self.backend.unobstructed.return_value=True
                api,state,send=self.drag_api()
                def interrupted(count,event,size):
                    accepted=send(count,event,size)
                    if state['held'] and len(state['moves'])==3:
                        if failure=='stop':self.active=False
                        elif failure=='focus':self.backend.unobstructed.return_value=False
                        elif failure=='geometry':self.backend.inspect.return_value=GameWindow(123,456,'Epic Seven',(0,0,3840,2019))
                        elif failure=='rejected':return 0
                        else:raise RuntimeError('interrupted')
                    return accepted
                api.SendInput.side_effect=interrupted
                with patch('e7_native_mouse.time.sleep') as sleep,self.assertRaises((MouseStopped,RuntimeError)):
                    self.mouse._send((-1920,1030),'drag',((-1914,400),.32))
                self.assertEqual(state['flags'][-1],4)
                self.assertFalse(state['held'])
                self.assertEqual(len(state['moves']),3)
                self.assertNotIn(.1,[call.args[0] for call in sleep.call_args_list])

    def test_failed_drag_endpoint_verification_releases_without_teleport(self):
        api,state,_=self.drag_api();position=api.GetCursorPos.side_effect
        api.GetCursorPos.side_effect=lambda pointer:False if state['held'] else position(pointer)
        with patch('e7_native_mouse.time.sleep'),self.assertRaisesRegex(MouseStopped,'endpoint'):
            self.mouse._send((-1920,1030),'drag',((-1914,400),.32))
        self.assertEqual(state['flags'][-1],4)
        self.assertFalse(state['held'])
        api.SetCursorPos.assert_not_called()

    def test_physical_pixel_context_failure_blocks_native_input(self):
        api = Mock(); api.SetThreadDpiAwarenessContext.return_value = None
        with self.assertRaisesRegex(ValueError,'No Mouse input'):
            physical_pixel_coordinates(api=api)
        api.SetThreadDpiAwarenessContext.return_value = 1
        physical_pixel_coordinates(api=api)

    def test_transient_capture_focus_loss_pauses_then_recaptures_without_input(self):
        self.backend.unobstructed.side_effect = [False,True,True]
        with patch('e7_native_mouse.time.sleep'),patch('e7_native_mouse.time.monotonic',side_effect=[0,0]),contextlib.redirect_stdout(io.StringIO()) as output:
            self.mouse.screenshot()
        self.assertIn('E7GUI_MOUSE_PAUSED',output.getvalue())
        self.assertIn('E7GUI_MOUSE_RESUMED',output.getvalue())
        self.sender.assert_not_called()

    def test_covered_exact_click_target_never_receives_input(self):
        self.mouse.screenshot(); self.backend.point_visible.return_value = False
        with patch('e7_native_mouse.time.sleep'),patch('e7_native_mouse.time.monotonic',side_effect=[0,0,11]):
            with self.assertRaisesRegex(MouseStopped,'target is covered'):
                self.mouse.click(436,994)
        self.sender.assert_not_called()

    def test_stop_during_focus_pause_is_immediate(self):
        self.backend.unobstructed.return_value = False
        with patch('e7_native_mouse.time.sleep',side_effect=lambda _:setattr(self,'active',False)):
            with self.assertRaisesRegex(MouseStopped,'session stopped'):
                self.mouse.screenshot()
        self.sender.assert_not_called()

    def test_resumed_focus_cannot_send_a_previously_prepared_click(self):
        self.mouse.screenshot(); self.backend.unobstructed.side_effect = [False,True]
        with patch('e7_native_mouse.time.sleep'):
            with self.assertRaisesRegex(MouseRecheckRequired,'Rechecking'):
                self.mouse.click(436,994)
        self.sender.assert_not_called()

    def test_visibility_failure_after_mouse_down_is_terminal_not_retryable(self):
        api=self.prepare_input_api();flags=[]
        def send(count,event,size):
            flag=event._obj.value.mouse.flags;flags.append(flag)
            if flag==2:self.backend.unobstructed.return_value=False
            return 1
        api.SendInput.side_effect=send
        with patch('e7_native_mouse.time.sleep') as sleep:
            with self.assertRaises(MouseStopped) as caught:
                self.mouse._send((-1920,1030),'click',0)
        self.assertNotIsInstance(caught.exception,MouseRecheckRequired)
        self.assertEqual(flags[-2:],[2,4])
        self.assertNotIn(.1,[call.args[0] for call in sleep.call_args_list])

    def test_native_interior_sampling_ignores_border_coverage_and_checks_real_target(self):
        from e7_windows_capture import WindowsCapture
        backend=WindowsCapture.__new__(WindowsCapture); backend.user=Mock()
        backend.user.GetForegroundWindow.return_value=self.target.handle
        backend.user.GetAncestor.side_effect=lambda handle,_:handle
        left,top,right,bottom=self.target.rectangle
        backend.user.WindowFromPoint.side_effect=lambda point:self.target.handle if left+50<point.x<right-50 and top+50<point.y<bottom-50 else 789
        self.assertFalse(backend.unobstructed(self.target))
        self.assertTrue(backend.unobstructed(self.target,margin=.06))
        self.assertFalse(backend.point_visible(self.target,(left+8,top+8)))


class NativeEngineTests(unittest.TestCase):
    def setUp(self):
        self.ocr_patch=patch('e7_shop_flow.read_ui_text',return_value=dict(text='',words=[]))
        self.ui_ocr=self.ocr_patch.start();self.addCleanup(self.ocr_patch.stop)
        # Mocks record every full frame passed to them; drop those records
        # after each test so the module stays within the capped test memory.
        self.addCleanup(self.ui_ocr.reset_mock)
        self.addCleanup(gc.collect)

    def make_engine(self):
        app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        app.loop_active,app.end_of_refresh = True,False
        app.budget,app.tap_sleep,app.debug = 12,.3,False
        app.random_offset=False
        app.screenwidth,app.screenheight = 1920,1080
        app.refresh_count = 0; app.stop_refresh_key = '`'
        app.generateOffset = lambda:(0,0)
        app._rgb = shop(); app._item = None; app._item_name = None
        app.read_confirmation_text = lambda _: ('Use Skystone to refresh? Cancel Confirm' if app._item_name is None else
            'Cancel Buy Covenant Bookmarks 184,000' if app._item_name=='Covenant bookmark' else 'Cancel Buy Mystic Medals 280,000')
        app.read_navigation_text = Mock(return_value=dict(text='',words=[]))
        app.mouse = Mock()
        app._save_confirmation_failure=Mock(return_value=False)
        app._save_home_failure=Mock(return_value=False)
        app._shop_return_failure_detail=Mock(return_value='')
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

    def test_home_ocr_menu_requires_home_labels_and_unambiguous_observed_text(self):
        result=dict(text='Sanctuary Secret Shop Epic Pass',words=[dict(text='secret',box=[20,620,100,650]),dict(text='shop',box=[110,620,175,650])])
        self.assertEqual(home_menu_target(result),(97.5,635))
        self.assertIsNone(home_menu_target(dict(result,text='Secret Shop')))
        self.assertIsNone(home_menu_target(dict(result,words=result['words']*2)))
        result['words'][1]['text']='shpp'
        self.assertEqual(home_menu_target(result),(97.5,635))

    def test_home_ocr_accepts_joined_secret_shop_words(self):
        for text in ('SecretShop','Secret Sh0p','Secret.Shop','SecretShoo'):
            result=dict(text='Sanctuary '+text,words=[dict(text=text,box=[20,620,175,650])])
            self.assertEqual(home_menu_target(result),(97.5,635))
        self.assertIsNone(home_menu_target(dict(text='Sanctuary',words=[dict(text='SecretShop',box=[600,620,775,650])])))

    def test_native_shop_ocr_descender_error_still_requires_home_context_and_icon(self):
        result=dict(text='sanctuary secr.et shoo epic pas',words=[dict(text='secr.et',box=[17,534,89,564]),dict(text='shoo',box=[97,533,152,557])])
        icon=np.asarray(Image.open('adb-assets/builtin-navigation/native-secret-shop-icon.png'))
        frame=shop();frame[475:523,54:115][icon>0]=230
        self.assertIsNotNone(home_menu_target(result,frame))
        self.assertIsNone(home_menu_target(result,shop()))
        self.assertIsNone(home_menu_target(dict(result,text='secr.et shoo'),frame))

    def home_controls_frame(self,background,*,omitted=None,epic_shift=0):
        frame=np.full((1080,1920,3),background,dtype=np.uint8)
        positions={'sanctuary':(84,267),'secret-shop':(84,498),'epic-pass':(84,615+epic_shift)}
        for name,(x,y) in positions.items():
            if name==omitted:continue
            icon=np.asarray(Image.open(f'adb-assets/builtin-navigation/native-{name}-icon.png'))
            h,w=icon.shape;crop=frame[round(y-h/2):round(y-h/2)+h,round(x-w/2):round(x-w/2)+w]
            outline=cv2.dilate(icon,np.ones((3,3),dtype=np.uint8))>0
            crop[outline]=35;crop[icon>0]=240
        return frame

    def test_native_home_controls_match_both_bright_and_dark_artwork_without_ocr(self):
        for background in (40,220):
            frame=self.home_controls_frame(background)
            point=native_home_control_target(frame)
            self.assertIsNotNone(point);self.assertLess(math.dist(point,(84,498)),5)
            app=self.make_engine();app._rgb=frame
            self.assertIsNotNone(app._home_menu_target(np.zeros((1080,1920),dtype=np.uint8)))
            app.read_navigation_text.assert_not_called()

    def test_native_home_controls_require_all_three_correctly_arranged_visible_icons(self):
        for name in ('sanctuary','secret-shop','epic-pass'):
            self.assertIsNone(native_home_control_target(self.home_controls_frame(220,omitted=name)))
        self.assertIsNone(native_home_control_target(self.home_controls_frame(220,epic_shift=250)))
        self.assertIsNone(native_home_control_target((self.home_controls_frame(220)*.4).astype('uint8')))
        self.assertIsNone(native_home_control_target(np.full((1080,1920,3),220,dtype=np.uint8)))

    def test_native_home_controls_reject_two_equally_plausible_menu_columns(self):
        frame=self.home_controls_frame(40)
        frame[:,176:336]=frame[:,:160]
        self.assertIsNone(native_home_control_target(frame))

    def test_session_errors_emit_actual_reason_instead_of_stop_key_message(self):
        from e7_mouse_refresh import run_mouse_session
        app=Mock(); app.start.side_effect=ValueError('Unreadable home text')
        args=['--mouse-session',json.dumps(dict(handle=123,pid=456,title='Epic Seven',rectangle=[0,0,1920,1080])),
              '--budget','12','--delay','.3','--stop-key','`','--random-offset','yes']
        with patch('e7_mouse_refresh.E7MouseShopRefresh',return_value=app),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run_mouse_session(args),3)
        self.assertIn('E7GUI_MOUSE_STOPPED',output.getvalue())
        self.assertIn('Unreadable home text',output.getvalue())
        self.assertNotIn('Shop refresh terminated!',output.getvalue())

    def test_mouse_cli_passes_selected_timing_without_adb_or_input(self):
        from e7_mouse_refresh import run_mouse_session
        args=['--mouse-session',json.dumps(dict(handle=123,pid=456,title='Epic Seven',rectangle=[0,0,1920,1080])),
              '--budget','100','--delay','.3','--stop-key','esc','--random-offset','yes','--tap-jitter','.1']
        with patch('e7_mouse_refresh.E7MouseShopRefresh') as factory,patch('e7_mouse_refresh.sys.stdin',None),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_mouse_session(args),0)
        self.assertEqual((factory.call_args.kwargs['budget'],factory.call_args.kwargs['tap_jitter']),(100,.1))
        factory.return_value.start.assert_called_once()

    def test_home_ocr_opens_shop_without_manual_entry_or_refresh(self):
        app=self.make_engine()
        app.navigation.shop_visible.side_effect=[False,True]
        app.navigation.menu_target.return_value=None
        app.read_navigation_text.return_value=dict(text='Sanctuary Secret Shop',words=[dict(text='secret',box=[20,620,100,650]),dict(text='shop',box=[110,620,175,650])])
        frame=shop();frame[561:590,75:95]=230;frame[565:600,105:125]=230
        app.mouse.screenshot.return_value=Image.fromarray(frame)
        with patch('e7_mouse_refresh.time.sleep'),patch.object(adb_engine.subprocess,'run') as adb:
            self.assertTrue(app.clickShop())
        app.mouse.click.assert_called_once_with(100,580.5)
        adb.assert_not_called(); self.assertEqual(app.refresh_count,0)

    def test_native_home_click_targets_observed_icon_and_rejects_missing_icon(self):
        frame=shop();frame[475:510,51:73]=230;frame[480:523,79:108]=230
        self.assertEqual(home_icon_target(frame,(79.5,549)),(79.5,499))
        self.assertIsNone(home_icon_target(shop(),(79.5,549)))

    def test_hidden_known_home_is_revealed_once_then_menu_selected(self):
        app=self.make_engine()
        app.navigation.shop_visible.side_effect=[False,False,True]
        app.navigation.menu_target.side_effect=[None,(97,635),(97,635)]
        visible=shop();visible[561:590,75:95]=230;visible[565:600,105:125]=230
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (shop(),shop(),visible,visible,shop())]
        with patch('e7_shop_flow.hidden_home_matches',return_value=True),patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickShop())
        app.mouse.move.assert_not_called()
        self.assertEqual([call.args for call in app.mouse.click.call_args_list],[(960,540),(100,580.5)])

    def test_unfamiliar_idle_artwork_reveals_once_then_requires_observed_shop_menu(self):
        app=self.make_engine()
        artwork=np.random.default_rng(42).integers(0,255,(1080,1920,3),dtype=np.uint8)
        visible=shop();visible[561:590,75:95]=230;visible[565:600,105:125]=230
        animated=255-artwork
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (artwork,animated,visible,visible,shop())]
        app.navigation.shop_visible.side_effect=[False,False,False,True]
        app.navigation.menu_target.side_effect=[None,None,(97,635),(97,635)]
        self.ui_ocr.return_value=dict(text='eii -._nr.or decorative wallpaper',words=[])
        with patch('e7_shop_flow.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickShop())
        self.assertEqual([call.args for call in app.mouse.click.call_args_list],[(960,540),(100,580.5)])
        app.mouse.move.assert_not_called()
        self.assertEqual(app.refresh_count,0)

    def test_idle_artwork_probe_does_not_repeat_or_refresh_without_home_controls(self):
        app=self.make_engine()
        app.mouse.screenshot.return_value=Image.fromarray(np.random.default_rng(42).integers(0,255,(1080,1920,3),dtype=np.uint8))
        app.navigation.shop_visible.return_value=False
        app.navigation.menu_target.return_value=None
        self.ui_ocr.return_value=dict(text='',words=[])
        with patch('e7_shop_flow.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,0,31]):
            with self.assertRaises(MouseStopped): app.clickShop()
        app.mouse.click.assert_called_once_with(960,540)
        self.assertEqual(app.refresh_count,0)

    def test_idle_reveal_rejects_dialog_text_and_blank_loading_frames(self):
        artwork=np.random.default_rng(42).integers(0,255,(1080,1920,3),dtype=np.uint8)
        self.assertTrue(idle_home_candidate(artwork,dict(text='',words=[])))
        for text in ('Cancel Confirm','Connecting','Buy','Battle','Secret Shop','確認'):
            self.assertFalse(idle_home_candidate(artwork,dict(text=text,words=[])))
            self.assertFalse(idle_home_candidate(artwork,dict(words=[dict(text=text)])))
        self.assertFalse(idle_home_candidate(shop(),dict(text='',words=[])))

    def test_idle_reveal_accepts_dark_sparse_and_lettered_wallpaper(self):
        artwork=np.full((1080,1920,3),12,dtype=np.uint8)
        artwork[300:700,600:1200]=40
        self.assertTrue(idle_home_candidate(artwork,dict(text='eii -._nr.or',words=[])))
        self.assertTrue(idle_home_candidate(artwork,dict(text='Winter memories',words=[dict(text='2026')])))
        for text in ('SecretShop','Log in','Tap to start','Purchase','Loading'):
            self.assertFalse(idle_home_candidate(artwork,dict(text=text,words=[])))

    def test_controls_appearing_before_reveal_are_used_without_extra_center_click(self):
        app=self.make_engine()
        artwork=np.random.default_rng(42).integers(0,255,(1080,1920,3),dtype=np.uint8)
        visible=shop();visible[561:590,75:95]=230;visible[565:600,105:125]=230
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (artwork,visible,visible,visible,shop())]
        app.navigation.shop_visible.side_effect=[False,False,False,True]
        app.navigation.menu_target.side_effect=[None,(97,635),(97,635),(97,635)]
        with patch('e7_shop_flow.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickShop())
        app.mouse.click.assert_called_once_with(100,580.5)

    def test_idle_reveal_rechecks_full_screen_for_new_dialog_before_click(self):
        app=self.make_engine()
        app.mouse.screenshot.return_value=Image.fromarray(np.random.default_rng(42).integers(0,255,(1080,1920,3),dtype=np.uint8))
        app.navigation.shop_visible.return_value=False
        app.navigation.menu_target.return_value=None
        self.ui_ocr.side_effect=[dict(text='',words=[]),dict(text='Cancel Confirm',words=[])]
        with patch('e7_shop_flow.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,31]):
            with self.assertRaises(MouseStopped): app.clickShop()
        app.mouse.click.assert_not_called()

    def test_home_entry_ignores_animated_wallpaper_but_rechecks_icon(self):
        app=self.make_engine();app.navigation.shop_visible.side_effect=[False,True]
        app.navigation.menu_target.return_value=(97,635)
        first=shop();first[561:590,75:95]=230;first[565:600,105:125]=230
        second=first.copy();second[180:920,160:420]=190
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (first,second,shop())]
        with patch('e7_mouse_refresh.time.sleep'): self.assertTrue(app.clickShop())
        app.mouse.click.assert_called_once_with(100,580.5)

    def test_swallowed_shop_menu_click_is_retried_from_fresh_recognition(self):
        # Live 2026-11-14: the pointer brushed the game right after the menu
        # click and the shop never opened. Opening spends nothing: retry.
        import itertools
        app=self.make_engine();clock=itertools.count(0,.5)
        app.navigation.menu_target.return_value=(97,635)
        visible=shop();visible[561:590,75:95]=230;visible[565:600,105:125]=230
        app.mouse.screenshot.return_value=Image.fromarray(visible)
        opened=[False]
        app.navigation.shop_visible.side_effect=lambda _:opened[0]
        app.mouse.click.side_effect=lambda *_:opened.__setitem__(0,app.mouse.click.call_count>=2)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(app.clickShop())
        self.assertEqual([call.args for call in app.mouse.click.call_args_list],[(100,580.5)]*2)
        self.assertEqual(app.refresh_count,0)

    def test_menu_retry_comes_soon_after_a_pointer_pause(self):
        # Live STOVE 2026-11-14: repeated hovers each restarted the full 8 s wait.
        from e7_shop_flow import SHOP_RETRY_AFTER_PAUSE
        app=self.make_engine();app.mouse.pause_revision=0;clock=[0.]
        app.navigation.shop_visible.return_value=False
        def capture():
            if len(app.mouse.screenshot.call_args_list)==3:app.mouse.pause_revision+=1
            return Image.fromarray(shop())
        app.mouse.screenshot.side_effect=capture
        def tick():clock[0]+=.25;return clock[0]
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=tick):
            self.assertIsNone(app._wait_for_shop(final=False))
        self.assertLess(clock[0],8)
        self.assertGreaterEqual(clock[0],SHOP_RETRY_AFTER_PAUSE)
        # The last attempt still allows the full wait after a pause.
        app=self.make_engine();app.mouse.pause_revision=0;clock[0]=0.
        app.navigation.shop_visible.return_value=False
        app.mouse.screenshot.side_effect=capture
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=tick), \
                self.assertRaisesRegex(MouseStopped,'did not open'):
            app._wait_for_shop(final=True)
        self.assertGreaterEqual(clock[0],8)

    def test_shop_menu_that_never_opens_stops_after_bounded_attempts(self):
        import itertools
        from e7_shop_flow import SHOP_OPEN_ATTEMPTS
        app=self.make_engine();clock=itertools.count(0,.5)
        app.navigation.menu_target.return_value=(97,635)
        app.navigation.shop_visible.return_value=False
        visible=shop();visible[561:590,75:95]=230;visible[565:600,105:125]=230
        app.mouse.screenshot.return_value=Image.fromarray(visible)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'did not open after selecting its menu'):
            app.clickShop()
        self.assertEqual(app.mouse.click.call_count,SHOP_OPEN_ATTEMPTS)

    def test_home_entry_rejects_controls_that_disappear_before_click(self):
        app=self.make_engine();app.navigation.shop_visible.return_value=False
        app.navigation.menu_target.return_value=(97,635)
        visible=shop();visible[561:590,75:95]=230;visible[565:600,105:125]=230
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (visible,shop())]
        with patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,31]):
            with self.assertRaises(MouseStopped): app.clickShop()
        app.mouse.click.assert_not_called()

    def test_native_icon_mask_ignores_bright_wallpaper_fragments(self):
        icon=np.asarray(Image.open('adb-assets/builtin-navigation/native-secret-shop-icon.png'))
        frame=shop();patch_rgb=frame[475:523,54:115];patch_rgb[icon>0]=230
        target=home_icon_target(frame,(84,548.5))
        self.assertIsNotNone(target)
        frame[463:472,29:36]=230;frame[463:472,132:139]=230
        self.assertEqual(home_icon_target(frame,(84,548.5)),target)

    def test_home_failure_saves_only_menu_crop_and_actual_ocr(self):
        app=self.make_engine();app._last_home_ocr=dict(text='sanctuary',words=[])
        with tempfile.TemporaryDirectory() as temp,patch('e7_shop_flow.Path',side_effect=lambda path:Path(temp)/path):
            self.assertTrue(E7MouseShopRefresh._save_home_failure(app,True))
            folders=list((Path(temp)/'mouse-failures').iterdir());self.assertEqual(len(folders),1)
            with Image.open(folders[0]/'home-menu.png') as image:self.assertEqual(image.size,(420,740))
            data=json.loads((folders[0]/'failure.json').read_text())
            self.assertTrue(data['reveal_clicked']);self.assertFalse(data['shop_clicked'])
            self.assertEqual(data['home_ocr'],app._last_home_ocr)

    def test_unknown_screen_sends_no_pointer_input(self):
        app=self.make_engine(); app.navigation.shop_visible.return_value=False
        app.navigation.menu_target.return_value=None
        with patch('e7_shop_flow.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,0,31]):
            with self.assertRaisesRegex(MouseStopped,'home Secret Shop menu'):
                app.clickShop()
        app.mouse.click.assert_not_called()
        app.mouse.move.assert_not_called()

    def test_private_home_reference_rejects_changed_page_or_popup(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'hidden.png'
            frame=np.random.default_rng(23).integers(30,230,(1080,1920),dtype=np.uint8)
            Image.fromarray(frame).save(path)
            self.assertTrue(hidden_home_matches(frame,path))
            popup=frame.copy(); popup[300:900,500:1450]=30
            self.assertFalse(hidden_home_matches(popup,path))
            self.assertFalse(hidden_home_matches(np.full_like(frame,50),path))

    def test_stove_reframed_home_requires_matching_artwork_and_rejects_overlays(self):
        import cv2
        rng = np.random.default_rng(41)
        saved = np.full((540,960), 70, dtype=np.uint8)
        for _ in range(350):
            x,y = rng.integers([20,20],[900,500])
            cv2.circle(saved, (int(x),int(y)), int(rng.integers(3,18)), int(rng.integers(20,230)), -1)
        matrix = np.float32([[1.08,0,-38],[0,1,0]])
        current = cv2.warpAffine(saved, matrix, (960,540))
        self.assertTrue(reframed_home_matches(current,saved))
        for altered in (current.copy(), (current*.45).astype('uint8'), np.full_like(current,50)):
            if np.array_equal(altered,current): altered[155:435,250:720] = 30
            self.assertFalse(reframed_home_matches(altered,saved))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'hidden.png'; Image.fromarray(saved).save(path)
            frame=cv2.resize(current,(1920,1080))
            self.assertTrue(hidden_home_matches(frame,path))

    def test_default_hidden_home_checks_google_without_replacing_native_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'adb-assets/native-home';folder.mkdir(parents=True)
            native=np.random.default_rng(11).integers(30,230,(1080,1920),dtype=np.uint8)
            google=np.random.default_rng(23).integers(30,230,(1080,1920),dtype=np.uint8)
            Image.fromarray(native).save(folder/'hidden.png')
            Image.fromarray(google).save(folder/'google-hidden.png')
            with patch('e7_shop_flow.Path',side_effect=lambda name:root/name):
                self.assertTrue(hidden_home_matches(native))
                self.assertTrue(hidden_home_matches(google))
                self.assertFalse(hidden_home_matches(np.full_like(google,50)))

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

    def test_native_blue_confirm_uses_observed_label_and_paired_cancel(self):
        frame=dialog();frame[650:740,1040:1290]=(30,60,120)
        self.ui_ocr.return_value=dict(text='Use Skystone to refresh? Cancel Confirm',words=[dict(text='cancel',box=[768,677,852,704]),dict(text='confirm',box=[1063,676,1161,704])])
        self.assertEqual(confirmation_button(frame,'refresh',shop()),(1063,676,1161,704))
        self.ui_ocr.return_value['words'].pop(0)
        self.assertIsNone(confirmation_button(frame,'refresh',shop()))

    def test_native_wide_purchase_confirmation_is_clicked_only_for_matching_item(self):
        frame=shop();frame[300:920,550:1400]=90
        frame[718:809,896:1351]=(20,110,40)  # Captured STOVE button geometry.
        self.assertEqual(confirmation_button(frame,'buy',shop()),(896,718,1351,809))
        self.assertIsNone(confirmation_button(frame,'refresh',shop()))
        self.assertEqual(green_buttons(frame,(800,400,1450,1000)),[])
        for name,text in (('Covenant bookmark','Cancel Buy Covenant Bookmarks 184,000'),
                          ('Mystic medal','Cancel Buy Mystic Medals 280,000')):
            with self.subTest(item=name):
                app=self.make_engine();app._item_name=name
                app.read_confirmation_text=lambda _,text=text:text
                app.mouse.screenshot.side_effect=[Image.fromarray(image) for image in (frame,frame,shop())]
                with patch('e7_mouse_refresh.time.sleep'):
                    self.assertTrue(app._confirm('buy',shop()))
                self.assertEqual(app.mouse.click.call_args_list[0].args,(1123.5,763.5))
                self.assertEqual(app.mouse.click.call_count,1)
        app=self.make_engine();app._item_name='Mystic medal'
        app.read_confirmation_text=lambda _:'Cancel Buy Covenant Bookmarks 184,000'
        app.mouse.screenshot.return_value=Image.fromarray(frame)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,1,6]),self.assertRaisesRegex(MouseStopped,'does not match'):
            app._confirm('buy',shop())
        app.mouse.click.assert_not_called()
        frame[718:809,896:1400]=(20,110,40)
        self.assertIsNone(confirmation_button(frame,'buy',shop()))

    def test_refresh_uses_recognized_label_then_observed_confirmation(self):
        app = self.make_engine()
        app.mouse.screenshot.side_effect = [Image.fromarray(frame) for frame in (shop(),dialog(),dialog(),shop())]
        with patch('e7_mouse_refresh.time.sleep'),patch.object(adb_engine.subprocess,'run') as adb:
            self.assertTrue(app.clickRefresh())
        adb.assert_not_called()
        self.assertEqual(app.mouse.click.call_args_list[0].args,(436,994))
        self.assertEqual(app.mouse.click.call_args_list[1].args,(1165,695))
        self.assertEqual(app.refresh_count,0)  # Only the shared loop increments.

    def _ignored_refresh_app(self,ignored):
        """The first `ignored` Refresh clicks open no dialog."""
        import itertools
        app=self.make_engine()
        app.read_confirmation_text=lambda rgb:'Use Skystone to refresh? Cancel Confirm' if rgb[700,1100,1]==110 else ''
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(dialog() if app.mouse.click.call_count==ignored+1 else shop())
        return app,itertools.count(0,.25)

    def test_refresh_ignored_by_the_game_is_clicked_once_more(self):
        # Reported on Steam 1920x1080: a few refreshes, then 'refresh confirmation was not recognized'.
        app,clock=self._ignored_refresh_app(1)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print') as printed:
            self.assertTrue(app.clickRefresh())
        self.assertEqual([c.args for c in app.mouse.click.call_args_list],[(436,994),(436,994),(1165,695)])
        self.assertTrue(any('did not open the Refresh dialog' in str(c.args[0]) for c in printed.call_args_list))

    def test_refresh_ignored_twice_stops_after_two_refresh_clicks(self):
        app,clock=self._ignored_refresh_app(2)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'refresh confirmation was not recognized'):
            app.clickRefresh()
        self.assertEqual([c.args for c in app.mouse.click.call_args_list],[(436,994)]*2)

    def test_refresh_is_not_clicked_again_if_its_label_moved_or_shop_is_dimmed(self):
        for case in ('moved','dimmed'):
            with self.subTest(case=case):
                app,clock=self._ignored_refresh_app(1)
                marker=app.navigation.navigators[0][1]
                if case=='moved':
                    marker.match.side_effect=lambda *_:dict(point=(436,994) if app.mouse.click.call_count==0 else (436,960))
                else:
                    app.navigation.shop_visible.side_effect=lambda _:app.mouse.click.call_count==0
                with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                        self.assertRaisesRegex(MouseStopped,'refresh confirmation was not recognized'):
                    app.clickRefresh()
                self.assertEqual([c.args for c in app.mouse.click.call_args_list],[(436,994)])

    def test_covered_refresh_label_is_read_again_before_one_click(self):
        # STOVE: after a purchase a toast can still cover Refresh when the shop returns.
        app=self.make_engine();marker=app.navigation.navigators[0][1]
        marker.match.side_effect=[None,None,dict(point=(436,994))]
        app.mouse.screenshot.side_effect=[Image.fromarray(f) for f in (shop(),shop(),shop(),dialog(),dialog(),shop())]
        with patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickRefresh())
        self.assertEqual(app.mouse.click.call_args_list[0].args,(436,994))
        self.assertEqual(app.mouse.click.call_count,2)  # Refresh, then one Confirm

    def test_refresh_label_that_stays_covered_stops_without_any_click(self):
        import itertools
        app=self.make_engine();clock=itertools.count(0,.5)
        app.navigation.navigators[0][1].match.return_value=None
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'Refresh target was not recognized'):
            app.clickRefresh()
        app.mouse.click.assert_not_called()
        self.assertGreater(app.mouse.screenshot.call_count,2)

    def test_real_navigator_waits_for_covered_refresh_but_not_for_another_screen(self):
        # Codex P2: full shop recognition needs the Refresh label, so the
        # covered case must be tested through the real navigator, not a mock.
        import itertools
        from e7_shop_navigation import create_navigator, REFERENCE_BOXES
        navigation=create_navigator('adb-assets')
        refs=navigation.navigators[-1][1].references
        def frame(title=True,refresh=True):
            gray=np.full((1080,1920),30,dtype=np.uint8)
            for name,show in (('shop-title.png',title),('refresh-label.png',refresh)):
                if show:
                    x1,y1,x2,y2=REFERENCE_BOXES[name];gray[y1:y2,x1:x2]=refs[name]
            return Image.fromarray(np.stack([gray]*3,axis=2))
        self.assertTrue(navigation.shop_visible(np.array(frame().convert('L'))))
        app=self.make_engine();app.navigation=navigation;app._confirm=Mock(return_value=True)
        app.mouse.screenshot.side_effect=[frame(refresh=False),frame(refresh=False),frame()]
        with patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickRefresh())
        self.assertEqual(app.mouse.click.call_count,1)
        self.assertEqual(app.mouse.screenshot.call_count,3)
        # Covered until the deadline: no click.
        app=self.make_engine();app.navigation=navigation;app._confirm=Mock(return_value=True);clock=itertools.count(0,.5)
        app.mouse.screenshot.side_effect=lambda:frame(refresh=False)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaises(RuntimeError):
            app.clickRefresh()
        app.mouse.click.assert_not_called();self.assertGreater(app.mouse.screenshot.call_count,2)
        # No shop title: stop on the first frame.
        app=self.make_engine();app.navigation=navigation;app._confirm=Mock(return_value=True)
        app.mouse.screenshot.side_effect=lambda:frame(title=False,refresh=False)
        with patch('e7_mouse_refresh.time.sleep'),self.assertRaisesRegex(RuntimeError,'could not be verified'):
            app.clickRefresh()
        app.mouse.click.assert_not_called();self.assertEqual(app.mouse.screenshot.call_count,1)

    def _real_navigator_frames(self):
        from e7_shop_navigation import create_navigator, REFERENCE_BOXES
        navigation=create_navigator('adb-assets')
        refs=navigation.navigators[-1][1].references
        def frame(dim=1.):
            gray=np.full((1080,1920),30,dtype=np.uint8)
            for name in ('shop-title.png','refresh-label.png'):
                x1,y1,x2,y2=REFERENCE_BOXES[name];gray[y1:y2,x1:x2]=refs[name]
            gray=(gray*dim).astype(np.uint8)  # a dialog or overlay darkens the whole shop
            return Image.fromarray(np.stack([gray]*3,axis=2))
        return navigation,frame

    def test_shop_dimmed_behind_a_dialog_is_not_the_shop(self):
        # Live Steam/STOVE frames: the shop behind a dialog keeps its shape
        # (score ~.94) but only ~15% of its contrast.
        navigation,frame=self._real_navigator_frames()
        dimmed=np.array(frame(.15).convert('L'))
        self.assertTrue(navigation.shop_visible(np.array(frame().convert('L'))))
        self.assertFalse(navigation.shop_visible(dimmed))
        self.assertTrue(all(nav.dimmed(dimmed,'shop-title.png') for _,nav in navigation.navigators))
        self.assertIn('dimmed',navigation.verification_details(dimmed))

    def test_refresh_waits_for_an_overlay_to_clear_and_never_clicks_through_it(self):
        import itertools
        navigation,frame=self._real_navigator_frames()
        app=self.make_engine();app.navigation=navigation;app._confirm=Mock(return_value=True)
        app.mouse.screenshot.side_effect=[frame(.15),frame(.15),frame()]
        with patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickRefresh())
        self.assertEqual(app.mouse.click.call_count,1)
        app=self.make_engine();app.navigation=navigation;app._confirm=Mock(return_value=True);clock=itertools.count(0,.5)
        app.mouse.screenshot.side_effect=lambda:frame(.15)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(RuntimeError,'dimmed'):
            app.clickRefresh()
        app.mouse.click.assert_not_called()

    def test_dialog_still_open_after_confirm_is_not_counted_as_the_shop_returning(self):
        # Live Linux run: the game ignored a Confirm, one capture's OCR missed
        # the dialog's buttons, and the dimmed shop behind it was taken as the
        # shop returning. That counted a refresh that never happened and sent
        # the next Refresh click into the open dialog.
        import itertools
        navigation,frame=self._real_navigator_frames()
        app=self.make_engine();app.navigation=navigation;app._item_name=None
        app.read_confirmation_text=Mock(return_value='Use Skystone to refresh?')
        box=(1100,600,1300,660);calls=itertools.count()
        found=lambda *a:box if next(calls)<2 else None  # the button is read twice, then OCR misses it
        clock=itertools.count(0,.25)
        app.mouse.screenshot.side_effect=lambda:frame(.15)
        with patch('e7_shop_flow.confirmation_button',side_effect=found),patch('e7_shop_flow.confirmation_matches',return_value=True), \
                patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'shop did not return'):
            app._confirm('refresh',np.array(frame()))
        self.assertEqual(app.mouse.click.call_count,1)  # the one Confirm, nothing more

    def test_blank_dialog_backdrop_gets_a_longer_wait_but_still_needs_the_full_checks(self):
        # Steam 3840x2019, 2026-11-24: the dimmed shop and an empty dialog band
        # stayed up for the whole 5 s, probably while the game waited on the server.
        import itertools
        navigation,frame=self._real_navigator_frames()
        before=np.array(frame())
        box=(1100,600,1300,660)
        for appears in (8.,None):
            with self.subTest(appears=appears):
                app=self.make_engine();app.navigation=navigation;app._item_name=None
                app.read_confirmation_text=lambda _:'' if appears is None else 'Use Skystone to refresh?'
                clock=itertools.count(0,.25);now=[0.]
                def tick():
                    now[0]=next(clock);return now[0]
                found=lambda *a:box if appears is not None and now[0]>=appears else None
                app.mouse.screenshot.side_effect=lambda:frame(.15)
                with patch('e7_shop_flow.confirmation_button',side_effect=found), \
                        patch('e7_shop_flow.confirmation_matches',  # Codex P2: text readable 1 s after the button
                              side_effect=lambda *a:appears is not None and now[0]>=appears+1), \
                        patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=tick), \
                        patch('builtins.print') as printed:
                    if appears is None:
                        with self.assertRaisesRegex(MouseStopped,'refresh confirmation was not recognized: it stayed blank for 15 seconds'):
                            app._confirm('refresh',before)
                        app.mouse.click.assert_not_called()
                        self.assertGreaterEqual(now[0],15)
                    else:
                        # The shop never returns in this fake, so it stops after Confirm.
                        clicked=[];app.mouse.click.side_effect=lambda *a:clicked.append(now[0])
                        with self.assertRaisesRegex(MouseStopped,'shop did not return'):
                            app._confirm('refresh',before)
                        self.assertGreaterEqual(clicked[0],appears+1)  # clicked only once the dialog was read
                self.assertTrue(any('still blank' in str(c.args[0]) for c in printed.call_args_list if c.args))
        # A dark frame without the dimmed shop behind it gets no extra time.
        app=self.make_engine();app.navigation=navigation;app.read_confirmation_text=lambda _:''
        clock=itertools.count(0,.25);now=[0.]
        def tick2():
            now[0]=next(clock);return now[0]
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(np.full((1080,1920,3),5,dtype=np.uint8))
        with patch('e7_shop_flow.confirmation_button',return_value=None),patch('e7_mouse_refresh.time.sleep'), \
                patch('e7_mouse_refresh.time.monotonic',side_effect=tick2), \
                self.assertRaisesRegex(MouseStopped,r'refresh confirmation was not recognized\. No'):
            app._confirm('refresh',before)
        self.assertLess(now[0],8)

    def test_fading_confirmation_is_read_again_and_clicked_once_settled(self):
        # Fast captures can catch the dialog half transparent (seen live on Linux):
        # the button is found but looks different in the next capture.
        grown=dialog();grown[740:762,1040:1290]=(20,110,40)  # live crop: bottom edge 22px lower mid-fade
        dim=dialog();dim[650:740,1040:1290]=(12,66,24)        # same outline, still fading
        for name,faded in (('outline',grown),('pixels',dim)):
            with self.subTest(fade=name):
                app=self.make_engine()
                app.mouse.screenshot.side_effect=[Image.fromarray(f) for f in (shop(),faded,dialog(),dialog(),dialog(),shop())]
                with patch('e7_mouse_refresh.time.sleep'):
                    self.assertTrue(app.clickRefresh())
                self.assertEqual(app.mouse.click.call_count,2)  # Refresh, then one Confirm
                self.assertEqual(app.mouse.click.call_args_list[1].args,(1165,695))
                self.assertEqual(app.mouse.screenshot.call_count,6)  # the faded read was not clicked

    def test_confirmation_that_never_settles_stops_without_confirm_click(self):
        import itertools
        grown=dialog();grown[740:762,1040:1290]=(20,110,40)  # bottom edge keeps moving
        frames=itertools.cycle((grown,dialog()))
        app=self.make_engine();clock=itertools.count(0,.05)
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(next(frames))
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'kept changing while being read. No confirmation click sent'):
            app._confirm('refresh',shop())
        app.mouse.click.assert_not_called()
        self.assertIsNotNone(app._save_confirmation_failure.call_args.kwargs['validated'])

    def test_confirmation_changing_in_place_is_clicked_after_holding_its_place(self):
        # STOVE windowed 2026-11-14: the Covenant Buy dialog differed between
        # every two captures for 5 s while its button never moved.
        import itertools
        faded=dialog();faded[650:740,1040:1290]=(12,66,24)  # same outline, other pixels
        frames=itertools.cycle((faded,dialog()))
        app=self.make_engine();clock=itertools.count(0,.05)
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(next(frames))
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print') as printed,self.assertRaisesRegex(MouseStopped,'shop did not return'):
            app._confirm('refresh',shop())
        self.assertEqual(app.mouse.click.call_args_list[0].args,(1165,695))  # one Confirm, on the held button
        self.assertTrue(any('stays in place' in c.args[0] for c in printed.call_args_list))
        # The text is still checked: a held button naming another action is never clicked.
        app=self.make_engine();clock=itertools.count(0,.05);frames=itertools.cycle((faded,dialog()))
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(next(frames))
        # First reads see the faded frame; the fresh read before the click sees the other one.
        app.read_confirmation_text=lambda rgb:('Use Skystone to refresh? Cancel Confirm' if rgb[700,1100,1]==66
                                              else 'Cancel Buy Mystic Medals 280,000')
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print'),self.assertRaisesRegex(MouseStopped,'changed while being read'):
            app._confirm('refresh',shop())
        app.mouse.click.assert_not_called()

    def test_in_place_hold_restarts_when_the_button_disappears(self):
        # Codex review: a dialog that vanished and came back must hold its place a full second again.
        import itertools
        faded=dialog();faded[650:740,1040:1290]=(12,66,24)
        seq=[faded,dialog()]*6+[shop(),shop()]+[faded,dialog()]*40
        app=self.make_engine();clock=itertools.count(0,.05);now=[0]
        def monotonic():
            now[0]=next(clock);return now[0]
        captures=iter(seq);seen=[];clicked=[]
        def capture():
            frame=shop() if clicked else next(captures)  # the shop returns after the one Confirm
            seen.append(now[0]);return Image.fromarray(frame)
        app.mouse.screenshot.side_effect=capture
        app.mouse.click.side_effect=lambda *a,**k:clicked.append(now[0])
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=monotonic), \
                patch('builtins.print'):
            self.assertTrue(app._confirm('refresh',shop()))
        back=seen[14]  # first capture after the two dialog-free frames
        self.assertEqual(len(clicked),1)
        self.assertGreaterEqual(clicked[0]-back,1.0)

    def _paused_confirm_app(self,frames,pause_at):
        """Captures from `frames`; the pointer-pause counter rises at capture `pause_at`."""
        import itertools
        app=self.make_engine();app.mouse.pause_revision=0;clock=itertools.count(0,.5)
        app.read_confirmation_text=lambda rgb:'Use Skystone to refresh? Cancel Confirm' if rgb[700,1100,1]==110 else ''
        frames=iter(frames);count=[0]
        def capture():
            count[0]+=1
            if count[0]==pause_at:app.mouse.pause_revision+=1
            return Image.fromarray(next(frames))
        app.mouse.screenshot.side_effect=capture
        return app,clock

    def test_confirm_swallowed_by_pointer_is_repeated_once_on_same_dialog(self):
        # Live 2026-11-14 08:27: pointer crossed the game after Confirm; dialog stayed.
        frames=[dialog()]*2+[dialog()]*12+[dialog(),dialog(),shop()]
        app,clock=self._paused_confirm_app(frames+[shop()]*5,pause_at=3)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(app._confirm('refresh',shop()))
        self.assertEqual([c.args for c in app.mouse.click.call_args_list],[(1165,695)]*2)

    def test_confirm_ignored_by_busy_game_is_repeated_once_on_same_dialog(self):
        # Reported on 0.2.3: after buying the bottom row of the scrolled list
        # the game ignored Confirm with no pointer pause; the dialog stayed.
        frames=[dialog()]*2+[dialog()]*12+[dialog(),dialog(),shop()]
        app,clock=self._paused_confirm_app(frames+[shop()]*5,pause_at=0)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print') as printed:
            self.assertTrue(app._confirm('refresh',shop()))
        self.assertEqual([c.args for c in app.mouse.click.call_args_list],[(1165,695)]*2)
        self.assertTrue(any('did not take the Confirm click' in str(c.args[0]) for c in printed.call_args_list))

    def test_open_dialog_without_pointer_pause_is_confirmed_at_most_twice(self):
        app,clock=self._paused_confirm_app([dialog()]*60,pause_at=0)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'shop did not return after confirmation'):
            app._confirm('refresh',shop())
        self.assertEqual(app.mouse.click.call_count,2)

    def test_confirmation_sent_before_a_stop_is_counted_as_unverified(self):
        # The game may have charged a Confirm whose result was never seen; the
        # record must not show less than was spent.
        app,clock=self._paused_confirm_app([dialog()]*60,pause_at=0)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'shop did not return after confirmation'):
            app._confirm('refresh',shop())
        self.assertEqual(app._confirm_sent,('refresh',None))
        app.storage.writeToCSV=Mock()
        with patch('builtins.print') as printed:
            app.record_session('failed','The shop did not return after confirmation.')
        record=app.storage.writeToCSV.call_args.kwargs
        self.assertEqual((app.refresh_count,record['skystone_spent']),(1,3))
        self.assertIn('It is counted, but its result was not seen',record['session']['Reason'])
        self.assertTrue(any('E7GUI_STATS' in str(c.args[0]) for c in printed.call_args_list))
        # A purchase is counted the same way, once.
        app=self.make_engine();self.add_real_currencies(app);app.storage.writeToCSV=Mock()
        app._confirm_sent=('buy','Covenant bookmark')
        with patch('builtins.print'):
            app.record_session('stopped','Stop key pressed.');app.record_session('stopped','again')
        self.assertEqual(app.storage.inventory['Covenant bookmark'].count,1)
        self.assertEqual(app.refresh_count,0)
        # A confirmation whose shop return was seen leaves nothing pending, and nothing sent counts nothing.
        app,clock=self._paused_confirm_app([dialog()]*4+[shop()]*10,pause_at=0)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(app._confirm('refresh',shop()))
        self.assertIsNone(app._confirm_sent)
        self.assertEqual(app._count_sent_confirmation(),'')
        self.assertEqual(app.refresh_count,0)
        # Codex review: a Stop during the click can raise after the input went out, so that counts too.
        app,clock=self._paused_confirm_app([dialog()]*60,pause_at=0)
        app.mouse.click.side_effect=MouseStopped('Mouse session stopped.')
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'session stopped'):
            app._confirm('refresh',shop())
        self.assertEqual(app._confirm_sent,('refresh',None))
        # A recheck comes before any input: nothing is pending.
        app,clock=self._paused_confirm_app([dialog()]*60,pause_at=0)
        app.mouse.click.side_effect=MouseRecheckRequired('recheck')
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print'),self.assertRaisesRegex(MouseStopped,'No confirmation click sent'):
            app._confirm('refresh',shop())
        self.assertIsNone(app._confirm_sent)

    def test_refresh_waits_once_after_a_scrolled_purchase(self):
        app=self.make_engine();app._bought_scrolled=True
        waits=[]
        def wait(seconds,action,**_):
            waits.append(action);app.loop_active=False  # Stop right after the settle wait.
        app._wait_observed=wait
        self.assertFalse(app.clickRefresh())
        self.assertEqual(waits,['scrolled purchase settle'])
        self.assertFalse(app._bought_scrolled)

    def test_confirm_retry_happens_at_most_once(self):
        app,clock=self._paused_confirm_app([dialog()]*60,pause_at=3)
        def pause_each_click(*_):app.mouse.pause_revision+=1
        app.mouse.click.side_effect=pause_each_click
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'shop did not return after confirmation'):
            app._confirm('refresh',shop())
        self.assertEqual(app.mouse.click.call_count,2)

    def test_changed_dialog_after_pause_is_not_confirmed_again(self):
        other=shop();other[300:920,550:1400]=90;other[810:890,1100:1350]=(20,110,40)  # a dialog whose action moved: not the clicked one
        app,clock=self._paused_confirm_app([dialog()]*2+[other]*40,pause_at=3)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'shop did not return after confirmation'):
            app._confirm('refresh',shop())
        app.mouse.click.assert_called_once()

    def test_dialog_already_open_before_refresh_is_named_in_the_stop(self):
        app=self.make_engine()
        app.read_confirmation_text=lambda rgb:'Use Skystone to refresh? Cancel Confirm' if rgb[700,1100,1]==110 else ''
        app.mouse.screenshot.return_value=Image.fromarray(dialog())
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,1,6]), \
                self.assertRaisesRegex(MouseStopped,'refresh confirmation was already open before the refresh click'):
            app._confirm('refresh',dialog())
        app.mouse.click.assert_not_called()
        # A shop frame before the click still reports an unrecognized confirmation.
        app.mouse.screenshot.return_value=Image.fromarray(shop())
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,1,6]), \
                self.assertRaisesRegex(MouseStopped,'The refresh confirmation was not recognized'):
            app._confirm('refresh',shop())

    def test_button_settled_compares_only_the_button(self):
        from e7_shop_flow import button_settled
        moving=dialog();moving[300:600,550:1400]=200  # animated artwork elsewhere
        self.assertTrue(button_settled(dialog(),moving,(1040,650,1290,740)))
        faded=dialog();faded[650:740,1040:1290]=(12,66,24)
        self.assertFalse(button_settled(faded,dialog(),(1040,650,1290,740)))
        self.assertFalse(button_settled(dialog(),dialog(),(1040,650,1040,740)))

    def test_refresh_offset_is_small_bounded_and_respects_randomization_setting(self):
        for enabled in (False,True):
            for offset in (-75,75):
                app=self.make_engine();del app.generateOffset
                app.random_offset=enabled;app.x_offset=75;app.y_offset=25
                frame=shop();frame[950:1040,300:580]=(20,110,40)
                app.mouse.screenshot.return_value=Image.fromarray(frame)
                app._confirm=Mock(return_value=True)
                with patch('E7ADBShopRefresh.random.randint',side_effect=[offset,25]):
                    self.assertTrue(app.clickRefresh())
                x,y=app.mouse.click.call_args.args
                self.assertEqual((x,y),(436,994) if not enabled else (436+(14 if offset>0 else -14),1001))

    def test_refresh_without_observed_button_keeps_verified_label_point(self):
        app=self.make_engine();app.generateOffset=lambda:(75,25)
        app._confirm=Mock(return_value=True)
        self.assertTrue(app.clickRefresh())
        app.mouse.click.assert_called_once_with(436,994)

    def test_refresh_offset_handles_green_background_joined_above_button(self):
        app=self.make_engine();app.generateOffset=lambda:(-75,-25)
        frame=shop();frame[870:1040,300:580]=(20,110,40)
        app.mouse.screenshot.return_value=Image.fromarray(frame)
        app._confirm=Mock(return_value=True)
        self.assertTrue(app.clickRefresh())
        app.mouse.click.assert_called_once_with(422,987)

    def test_confirmation_waits_use_configured_tap_delay(self):
        app=self.make_engine();app.tap_sleep=.67
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (shop(),dialog(),dialog(),shop())]
        with patch('e7_mouse_refresh.time.sleep') as sleep:
            self.assertTrue(app.clickRefresh())
        self.assert_paced(sleep,app,.67)

    def test_mouse_confirmation_resamples_delay_for_each_tap(self):
        app=self.make_engine();app.random_offset=True
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (shop(),dialog(),dialog(),shop())]
        with patch.object(adb_engine.random, 'uniform', side_effect=[-.03,.03]), patch('e7_mouse_refresh.time.sleep') as sleep:
            self.assertTrue(app.clickRefresh())
        # A draw below the 0.3 s floor is raised to it.
        self.assert_paced(sleep,app,.3)
        self.assertEqual(app.tap_sleep,.3)

    def assert_paced(self,sleep,app,delay):
        waits=[call.args[0] for call in sleep.call_args_list]
        self.assertEqual(len(waits),3,waits)
        self.assertEqual((waits[0],waits[2]),(app.POLL_SECONDS,app.POLL_SECONDS))
        self.assertTrue(delay-.05<waits[1]<=delay,waits)

    def test_adjustable_mouse_timing_samples_full_selected_range(self):
        app=self.make_engine();app.random_offset=True;app.tap_jitter=.1
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (shop(),dialog(),dialog(),shop())]
        with patch.object(adb_engine.random,'uniform',side_effect=[-.1,.1]),patch('e7_mouse_refresh.time.sleep') as sleep:
            self.assertTrue(app.clickRefresh())
        # Dialog and shop-return waits poll; the confirm click is paced by one
        # draw from the jitter range, measured from the Refresh click, and
        # never faster than the 0.3 s floor.
        self.assert_paced(sleep,app,.3)

    def test_mouse_cli_rejects_fractional_budget_and_invalid_jitter_before_input(self):
        from e7_mouse_refresh import run_mouse_session
        args=['--mouse-session','{}','--budget','12','--delay','.3','--stop-key','esc','--random-offset','yes','--tap-jitter','.1']
        for flag,value in (('--budget','3.5'),('--tap-jitter','.11'),('--tap-jitter','nan')):
            altered=args.copy();altered[altered.index(flag)+1]=value
            with patch('e7_mouse_refresh.E7MouseShopRefresh') as factory,contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                run_mouse_session(altered)
            factory.assert_not_called()

    def test_missing_confirmation_stops_after_one_refresh_click(self):
        app = self.make_engine()
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,6]):
            with self.assertRaisesRegex(MouseStopped,'No confirmation click'):
                app.clickRefresh()
        self.assertEqual(app.mouse.click.call_count,1)
        self.assertEqual(app.refresh_count,0)

    def test_focus_pause_does_not_consume_confirmation_timeout(self):
        app=self.make_engine();app.mouse.pause_revision=0;clock=[0];images=iter((shop(),shop(),dialog(),dialog(),shop()))
        captures=[0]
        def capture():
            captures[0]+=1
            if captures[0]==2:
                clock[0]=8;app.mouse.pause_revision+=1
            return Image.fromarray(next(images))
        app.mouse.screenshot.side_effect=capture
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:clock[0]):
            self.assertTrue(app.clickRefresh())
        self.assertEqual(app.mouse.click.call_count,2)

    def test_shifted_dialog_action_is_observed_without_adb_anchor(self):
        frame=shop();frame[300:920,550:1400]=90
        frame[810:890,1100:1350]=(20,110,40)
        self.assertEqual(confirmation_button(frame,'refresh',shop()),(1100,810,1350,890))
        frame[420:500,1100:1350]=(20,110,40)
        self.assertIsNone(confirmation_button(frame,'refresh',shop()))

    def test_stop_protocol_and_eof_cancel_the_native_session(self):
        from e7_mouse_refresh import listen_for_stop
        for text in ('STOP\n',''):
            app=Mock();listen_for_stop(io.StringIO(text),app)
            app.request_stop.assert_called_once()

    def test_private_failure_crops_exclude_header_and_report_write_failure(self):
        import os
        app=self.make_engine();app._rgb=dialog()
        with tempfile.TemporaryDirectory() as temp:
            previous=os.getcwd()
            try:
                os.chdir(temp)
                self.assertTrue(E7MouseShopRefresh._save_confirmation_failure(app,'refresh',shop(),validated=dialog()))
                folder=next(Path('mouse-failures').iterdir())
                with Image.open(folder/'dialog.png') as saved:
                    self.assertEqual(saved.size,(950,740))
                with Image.open(folder/'validated.png') as saved:
                    self.assertEqual(saved.size,(950,740))
                self.assertFalse(json.loads((folder/'failure.json').read_text())['confirmation_clicked'])
                with patch('e7_shop_flow.Path.mkdir',side_effect=OSError('read only')):
                    self.assertFalse(E7MouseShopRefresh._save_confirmation_failure(app,'refresh',shop()))
            finally: os.chdir(previous)

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
        self.assertEqual(pos,(1741,260))
        app.mouse.screenshot.side_effect = [Image.fromarray(image) for image in (frame,dialog('buy'),dialog('buy'),shop())]
        with patch('e7_mouse_refresh.time.sleep'),patch.object(adb_engine.subprocess,'run') as adb:
            self.assertTrue(app.clickBuy(pos))
        adb.assert_not_called()
        self.assertEqual(app.mouse.click.call_args_list[0].args,pos)

    def _moving_buy_app(self,later):
        """A bookmark row found once, then a still-moving list, then `later`."""
        app = self.make_engine()
        template = np.random.default_rng(7).integers(20,240,(40,40),dtype=np.uint8)
        app.storage.inventory['Covenant bookmark'] = adb_engine.E7Item(template,184000)
        def row(top):
            frame = shop(); frame[top:top+40,800:840] = template[:,:,None]
            frame[top+20:top+100,1550:1810] = (20,110,40)
            return frame
        first = row(200); app._rgb = first
        pos = app.findItemPosition(cv_gray(first),template)
        app.read_confirmation_text = lambda rgb:'Cancel Buy Covenant Bookmarks 184,000' if rgb[760,1100,1]==110 else ''
        settled = row(later) if later is not None else shop()
        after = [dialog('buy'),dialog('buy'),shop()]
        captures = [0]
        def capture():
            captures[0] += 1
            if app.mouse.click.call_count:
                return Image.fromarray(after.pop(0) if len(after) > 1 else after[0])
            return Image.fromarray(shop() if captures[0] == 1 else settled)
        app.mouse.screenshot.side_effect = capture
        return app,pos,row

    def test_item_missing_right_before_buy_is_found_again_once_the_list_settles(self):
        import itertools
        clock = itertools.count(0,.25)
        app,pos,row = self._moving_buy_app(420)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print') as printed:
            self.assertTrue(app.clickBuy(pos))
        clicks = [c.args for c in app.mouse.click.call_args_list]
        self.assertEqual(clicks[0][1],480)  # Buy at the row's settled place (420+60)
        self.assertEqual(len(clicks),2)  # Buy, then Confirm
        self.assertTrue(any('moved before Buy' in str(c.args[0]) for c in printed.call_args_list))

    def test_item_still_missing_after_the_list_settles_stops_without_a_click(self):
        import itertools
        clock = itertools.count(0,.25)
        app,pos,_ = self._moving_buy_app(None)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print'),self.assertRaisesRegex(MouseStopped,'selected item changed before Buy'):
            app.clickBuy(pos)
        app.mouse.click.assert_not_called()

    def _unclear_then(self,app,clear_after):
        """findItemPosition raises an unclear-row stop for the first `clear_after` looks."""
        real, looks = app.findItemPosition, []
        def look(*args,**kwargs):
            looks.append(1)
            if len(looks) <= clear_after:
                from e7_shop_flow import UnclearShopRow; raise UnclearShopRow('The Covenant bookmark name was recognized, but its price and Buy button could not be verified on the same row. Stopped before scrolling or refreshing.')
            return real(*args,**kwargs)
        return look

    def test_unclear_row_right_before_buy_is_read_again_once_the_list_settles(self):
        import itertools
        clock = itertools.count(0,.25)
        app,pos,_ = self._moving_buy_app(200)
        with patch.object(app,'findItemPosition',self._unclear_then(app,1)), \
                patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print'):
            self.assertTrue(app.clickBuy(pos))
        self.assertEqual(app.mouse.click.call_args_list[0].args[1],260)

    def test_row_still_unclear_after_the_list_settles_stops_without_a_click(self):
        import itertools
        clock = itertools.count(0,.25)
        app,pos,_ = self._moving_buy_app(200)
        with patch.object(app,'findItemPosition',self._unclear_then(app,3)), \
                patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print'),self.assertRaisesRegex(MouseStopped,'could not be verified on the same row'):
            app.clickBuy(pos)
        app.mouse.click.assert_not_called()

    def test_shop_unverified_on_one_frame_before_buy_is_looked_at_again(self):
        # A fade or toast can hide the shop title for one frame; no click was sent.
        import itertools
        clock = itertools.count(0,.25)
        app,pos,_ = self._moving_buy_app(200)
        real, looks = app.navigation.require_shop, []
        def require(frame):
            looks.append(1)
            if len(looks) == 1:
                raise RuntimeError('Secret Shop screen could not be verified (test). Stopped before further shop actions.')
            return real(frame)
        with patch.object(app.navigation,'require_shop',side_effect=require), \
                patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print'):
            self.assertTrue(app.clickBuy(pos))
        self.assertEqual(app.mouse.click.call_args_list[0].args[1],260)

    def test_pre_buy_looks_are_bounded_and_send_no_click(self):
        import itertools
        clock = itertools.count(0,.25)
        app,pos,_ = self._moving_buy_app(200)
        with patch.object(app,'findItemPosition',self._unclear_then(app,99)) as look, \
                patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print'),self.assertRaises(MouseStopped):
            app.clickBuy(pos)
        app.mouse.click.assert_not_called()

    def test_ignored_buy_after_the_row_moved_is_retried_at_its_new_place(self):
        # Codex review 2026-11-14: the retry compared against the scan position.
        import itertools
        clock = itertools.count(0,.25)
        app,pos,row = self._moving_buy_app(420)
        moved, after = row(420), [dialog('buy'),dialog('buy'),shop()]
        def capture():
            clicks = app.mouse.click.call_count
            if clicks == 0:
                capture.n += 1
                return Image.fromarray(shop() if capture.n == 1 else moved)
            if clicks == 1:
                return Image.fromarray(moved)  # the game ignored this Buy
            return Image.fromarray(after.pop(0) if len(after) > 1 else after[0])
        capture.n = 0
        app.mouse.screenshot.side_effect = capture
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print'):
            self.assertTrue(app.clickBuy(pos))
        ys = [c.args[1] for c in app.mouse.click.call_args_list]
        self.assertEqual(ys[:2],[480,480])  # Buy, then Buy once more at the moved row

    def _ignored_buy_app(self,ignored):
        """A bookmark row whose first `ignored` Buy clicks open no dialog."""
        import itertools
        app = self.make_engine()
        template = np.random.default_rng(7).integers(20,240,(40,40),dtype=np.uint8)
        app.storage.inventory['Covenant bookmark'] = adb_engine.E7Item(template,184000)
        frame = shop(); frame[200:240,800:840] = template[:,:,None]
        frame[220:300,1550:1810] = (20,110,40)
        app._rgb = frame
        pos = app.findItemPosition(cv_gray(frame),template)
        app.read_confirmation_text = lambda rgb:'Cancel Buy Covenant Bookmarks 184,000' if rgb[760,1100,1]==110 else ''
        def capture():
            clicks = app.mouse.click.call_count
            return Image.fromarray(dialog('buy') if clicks == ignored+1 else frame)
        app.mouse.screenshot.side_effect = capture
        return app,pos,itertools.count(0,.25)

    def test_buy_ignored_by_the_game_is_clicked_once_more_on_the_same_row(self):
        app,pos,clock = self._ignored_buy_app(1)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                patch('builtins.print') as printed:
            self.assertTrue(app.clickBuy(pos))
        clicks = [c.args for c in app.mouse.click.call_args_list]
        self.assertEqual(clicks[:2],[pos,pos])  # Buy, Buy again
        self.assertEqual(len(clicks),3)  # then one Confirm
        self.assertTrue(any('did not open the Buy dialog' in str(c.args[0]) for c in printed.call_args_list))

    def test_buy_ignored_twice_stops_after_two_buy_clicks(self):
        app,pos,clock = self._ignored_buy_app(2)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'buy confirmation was not recognized'):
            app.clickBuy(pos)
        self.assertEqual([c.args for c in app.mouse.click.call_args_list],[pos,pos])

    def test_buy_is_not_clicked_again_unless_the_shop_is_fully_visible(self):
        app,pos,clock = self._ignored_buy_app(1)
        app.navigation.shop_visible.return_value = False  # e.g. dimmed behind an unrecognized dialog
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)), \
                self.assertRaisesRegex(MouseStopped,'buy confirmation was not recognized'):
            app.clickBuy(pos)
        self.assertEqual([c.args for c in app.mouse.click.call_args_list],[pos])

    def test_icon_match_checks_stock_before_buy_for_covenant_and_mystic(self):
        for name,price in (('Covenant bookmark',184000),('Mystic medal',280000)):
            app=self.make_engine()
            template=np.random.default_rng(7).integers(20,240,(40,40),dtype=np.uint8)
            app.storage.inventory[name]=adb_engine.E7Item(template,price)
            frame=shop();frame[200:240,800:840]=template[:,:,None];frame[220:300,1550:1810]=(20,110,40)
            for stock in ('0/1','1/1'):
                app._rgb=frame.copy()
                self.ui_ocr.return_value=dict(words=currency_words(name)+[dict(text=stock,box=[1580,243,1628,276])])
                with self.subTest(name=name,stock=stock):
                    point=app.findItemPosition(cv_gray(frame),template)
                    self.assertEqual(point,None if stock=='0/1' else (1741,260))
            app.mouse.click.assert_not_called()

    def test_stock_retry_recovers_small_fraction_and_caches_only_current_capture(self):
        for stock in ('0/1','1/1'):
            app=self.make_engine();app.storage.inventory['Friendship points']=adb_engine.E7Item(price=18000)
            app._rgb[220:300,1550:1810]=(20,110,40)
            self.ui_ocr.reset_mock()
            base=dict(words=currency_words('Friendship points'))
            row=dict(words=currency_words('Friendship points')+[dict(text=stock,box=[1580,243,1628,276])])
            self.ui_ocr.side_effect=[base,row,base,row]
            for index in range(3):
                if index==2:app._rgb=app._rgb.copy()
                point=app.findItemPosition(cv_gray(app._rgb),None)
                self.assertEqual(point,None if stock=='0/1' else (1734,260))
                self.assertEqual(self.ui_ocr.call_count,2 if index<2 else 4)
            retry=self.ui_ocr.call_args_list[1]
            self.assertEqual(retry.kwargs,dict(scale=2,contrast=True))
            app.mouse.click.assert_not_called()
        self.ui_ocr.side_effect=None

    def test_split_stock_uses_whole_list_row_when_row_retry_loses_category(self):
        # Mac Phase 4 run 2: whole-list OCR read the row but split "1/1"; the
        # enlarged row re-read garbled the small "Currency" label.
        for stock in ('0','1'):
            app=self.make_engine();app.storage.inventory['Friendship points']=adb_engine.E7Item(price=18000)
            app._rgb[220:300,1550:1810]=(20,110,40)
            self.ui_ocr.reset_mock()
            whole=dict(words=currency_words('Friendship points')+[dict(text=stock,box=[1580,243,1592,276]),
                                                                   dict(text='/1',box=[1594,243,1628,276])])
            garbled=dict(words=[dict(text='if' if word['text']=='currency' else word['text'],box=word['box'])
                                for word in currency_words('Friendship points')]+[dict(text=stock+'/1',box=[1580,243,1628,276])])
            self.ui_ocr.side_effect=[whole,garbled]
            with self.subTest(stock=stock):
                point=app.findItemPosition(cv_gray(app._rgb),None)
                self.assertEqual(point,None if stock=='0' else (1734,260))
                self.assertEqual(self.ui_ocr.call_count,1)
            app.mouse.click.assert_not_called()
        self.ui_ocr.side_effect=None

    def test_unreadable_category_is_reread_from_its_own_strip_only(self):
        # Mac, 2026-11-18: whole-list and row OCR both lost the top row's small
        # "Currency" label ("ancy"); a tight read of only that strip read it.
        def lost(label):
            return [dict(text=label if word['text']=='currency' else word['text'],box=word['box'])
                    for word in currency_words('Friendship points')]+[dict(text='1/1',box=[1580,243,1628,276])]
        currency=dict(text='currency',box=[1035,155,1135,180])
        cases=(('strip reads it',[currency],(1734,260)),
               ('strip loses it',[dict(text='ancy',box=[1080,155,1135,180])],None),
               ('two category words',[currency,dict(text='currency',box=[1240,155,1340,180])],None),
               ('outside the row window',[dict(text='currency',box=[1035,120,1135,140])],None))
        for case,strip,expected in cases:
            app=self.make_engine();app.storage.inventory['Friendship points']=adb_engine.E7Item(price=18000)
            app._rgb[220:300,1550:1810]=(20,110,40)
            self.ui_ocr.reset_mock()
            self.ui_ocr.side_effect=[dict(words=lost('ancy')),dict(words=strip),dict(words=lost('if'))]
            with self.subTest(case=case):
                if expected is None:
                    with self.assertRaisesRegex(MouseStopped,'could not be verified on the same row|ambiguous'):
                        app.findItemPosition(cv_gray(app._rgb),None)
                else:
                    self.assertEqual(app.findItemPosition(cv_gray(app._rgb),None),expected)
                    self.assertEqual(self.ui_ocr.call_count,2)
                strip_call=self.ui_ocr.call_args_list[1]
                self.assertEqual(strip_call.args[1],(960,153,1480,203))  # name top 205: 52 to 2 px above
                self.assertEqual(strip_call.kwargs,dict(scale=2,contrast=True))
            app.mouse.click.assert_not_called()
        self.ui_ocr.side_effect=None

    def friendship_engine(self,top=220):
        app=self.make_engine();app.storage.inventory['Friendship points']=adb_engine.E7Item(price=18000)
        app._rgb[top:top+80,1550:1810]=(20,110,40)
        self.ui_ocr.reset_mock()
        return app

    def test_ambiguity_in_one_read_is_not_erased_by_a_cleaner_reread(self):
        def lost(offset=0,extra=()):
            return [dict(text='ancy' if word['text']=='currency' else word['text'],box=word['box'])
                    for word in currency_words('Friendship points',offset)]+[dict(text='1/1',box=[1580,243+offset,1628,276+offset]),*extra]
        clean=lost()+[dict(text='currency',box=[1035,155,1135,180])]
        currency=dict(text='currency',box=[1035,155,1135,180])
        cases=(('two prices in the whole list',[dict(words=lost(extra=[dict(text='18,000',box=[1684,140,1786,165])])),dict(words=[currency])]),
               ('two category words in the strip',[dict(words=lost()),dict(words=[currency,dict(text='currency',box=[1240,155,1340,180])])]),
               ('two Buy words in the re-read',[dict(words=lost()),dict(words=[]),
                                                 dict(words=clean+[dict(text='buy',box=[1500,250,1540,282])])]))
        for case,reads in cases:
            app=self.friendship_engine()
            self.ui_ocr.side_effect=reads
            with self.subTest(case=case),self.assertRaisesRegex(MouseStopped,'ambiguous'):
                app.findItemPosition(cv_gray(app._rgb),None)
            app.mouse.click.assert_not_called()
        self.ui_ocr.side_effect=None

    def test_category_strip_is_clamped_to_the_list_top_and_skipped_when_too_short(self):
        def lost(offset):
            return [dict(text='ancy' if word['text']=='currency' else word['text'],box=word['box'])
                    for word in currency_words('Friendship points',offset)]+[dict(text='1/1',box=[1580,243+offset,1628,276+offset])]
        # Name top 150: the strip starts at the list top (110), not above it.
        app=self.friendship_engine(165)
        self.ui_ocr.side_effect=[dict(words=lost(-55)),dict(words=[dict(text='currency',box=[1035,115,1135,140])])]
        self.assertEqual(app.findItemPosition(cv_gray(app._rgb),None),(1734,205))
        self.assertEqual(self.ui_ocr.call_args_list[1].args[1],(960,110,1480,148))
        # Name top 139: under 30 px of strip is left, so it is not read and the
        # row still has to prove itself from the other reads.
        app=self.friendship_engine(154)
        self.ui_ocr.side_effect=[dict(words=lost(-66)),dict(words=lost(-66))]
        with self.assertRaisesRegex(MouseStopped,'could not be verified on the same row'):
            app.findItemPosition(cv_gray(app._rgb),None)
        self.assertFalse([call for call in self.ui_ocr.call_args_list if call.args[1][2]==1480])
        app.mouse.click.assert_not_called()
        self.ui_ocr.side_effect=None

    def test_readable_category_needs_no_strip_read(self):
        app=self.make_engine();app.storage.inventory['Friendship points']=adb_engine.E7Item(price=18000)
        app._rgb[220:300,1550:1810]=(20,110,40)
        self.ui_ocr.reset_mock()
        self.ui_ocr.side_effect=[dict(words=currency_words('Friendship points')+[dict(text='1/1',box=[1580,243,1628,276])])]
        self.assertEqual(app.findItemPosition(cv_gray(app._rgb),None),(1734,260))
        self.assertEqual(self.ui_ocr.call_count,1)
        self.ui_ocr.side_effect=None

    def test_scaled_row_ocr_maps_word_bounds_to_original_view(self):
        from e7_mouse_confirmation import read_ui_text
        rgb=shop();rgb[200:240,1500:1700]=80
        def child(*args,**kwargs):
            path=kwargs['env']['E7_MOUSE_OCR_FRAME']
            with Image.open(path) as image:
                self.assertEqual(image.size,(400,80))
            return Mock(returncode=0,stdout=json.dumps(dict(text='0/1',words=[dict(text='0/1',box=[20,10,100,60])])))
        # Windows OCR path, pinned so it is also covered when tests run elsewhere.
        with patch('e7_mouse_confirmation.subprocess.run',side_effect=child),\
             patch('e7_mouse_confirmation.ocr_backend',return_value='windows'),\
             patch.dict('os.environ',{'WINDIR':'C:\\Windows'}),\
             patch('e7_mouse_confirmation.subprocess.CREATE_NO_WINDOW',0x08000000,create=True):
            result=read_ui_text(rgb,(1500,200,1700,240),scale=2,contrast=True)
        self.assertEqual(result['words'][0]['box'],[1510,205,1550,230])

    def add_real_currencies(self,app):
        for filename,name,price in (('cov.png','Covenant bookmark',184000),('mys.png','Mystic medal',280000)):
            path=Path(adb_engine.__file__).parent/'adb-assets'/filename
            template=adb_engine.cv2.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),adb_engine.cv2.IMREAD_GRAYSCALE)
            self.assertIsNotNone(template)
            app.storage.inventory[name]=adb_engine.E7Item(template,price)

    def test_currency_text_fallback_uses_buy_label_and_caches_only_current_capture(self):
        app=self.make_engine();self.add_real_currencies(app)
        frame=shop();frame[220:300,1550:1810]=(20,110,40);frame[650:730,1550:1810]=(20,110,40)
        app._rgb=frame;self.ui_ocr.return_value=dict(words=currency_words('Covenant bookmark')+currency_words('Mystic medal',430)+[dict(text='1/1',box=[1580,243,1628,276]),dict(text='1/1',box=[1580,673,1628,706])])
        points=[app.findItemPosition(cv_gray(frame),item.image) for item in app.storage.inventory.values()]
        self.assertEqual(points,[(1734,260),(1734,690)])
        self.assertEqual(self.ui_ocr.call_count,1)
        app._rgb=frame.copy();app.findItemPosition(cv_gray(frame),app.storage.inventory['Mystic medal'].image)
        self.assertEqual(self.ui_ocr.call_count,2)

    def test_partial_currency_can_scroll_on_first_page_but_cannot_be_refreshed_on_second(self):
        app=self.make_engine();self.add_real_currencies(app)
        words=currency_words('Mystic medal',800)
        self.ui_ocr.return_value=dict(words=[word for word in words if word['text'] not in ('buy','only','1','available')])
        app._scan_page=1
        self.assertIsNone(app.findItemPosition(cv_gray(app._rgb),app.storage.inventory['Mystic medal'].image))
        app._scan_page=2
        with self.assertRaises(IncompleteCurrencyRow):app.findItemPosition(cv_gray(app._rgb),app.storage.inventory['Mystic medal'].image)
        app.mouse.click.assert_not_called()

    def test_unverified_currency_stops_shared_loop_before_drag_or_refresh(self):
        app=self.make_engine();self.add_real_currencies(app)
        frame=shop();frame[220:300,1550:1810]=(20,110,40)
        app.mouse.screenshot.return_value=Image.fromarray(frame)
        self.ui_ocr.return_value=dict(words=currency_words('Mystic medal',price='184,000'))
        app.clickRefresh=Mock()
        with patch('e7_mouse_refresh.time.sleep'),self.assertRaisesRegex(MouseStopped,'same row'):
            app.refreshShop()
        app.mouse.click.assert_not_called();app.mouse.drag.assert_not_called();app.clickRefresh.assert_not_called()

    def test_shared_loop_buys_both_currencies_before_drag_and_refresh(self):
        app=self.make_engine();self.add_real_currencies(app);app.budget=3
        bought=set();pending=[None];stage=['shop'];events=[];dragged=[False]
        def scene():
            frame=scrolled() if dragged[0] else shop()
            for name,top in (('Covenant bookmark',220),('Mystic medal',650)):
                if name not in bought:frame[top:top+80,1550:1810]=(20,110,40)
            return frame
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(dialog('buy') if stage[0]=='confirm' else scene())
        def words(rgb,region,**kwargs):
            result=[]
            for name,offset in (('Covenant bookmark',0),('Mystic medal',430)):
                row=currency_words(name,offset)
                if name in bought:
                    row=[word for word in row if word['text']!='buy']
                    for word in row:
                        if word['text']=='1':word['text']='0'
                result.extend(row)
            return dict(words=result)
        self.ui_ocr.side_effect=words
        app.read_confirmation_text=lambda rgb:f'Cancel Confirm {pending[0]} {app.storage.inventory[pending[0]].price}'
        def click(x,y):
            if stage[0]=='shop':
                self.assertEqual(x,1734)
                pending[0]='Covenant bookmark' if y==260 else 'Mystic medal'
                self.assertEqual(y,260 if pending[0]=='Covenant bookmark' else 690)
                stage[0]='confirm';events.append('buy '+pending[0])
            else:
                self.assertEqual((x,y),(1165,765))
                bought.add(pending[0]);stage[0]='shop';events.append('confirm '+pending[0])
        def drag(*args,**kw):dragged[0]=True;events.append('drag')
        app.mouse.click.side_effect=click;app.mouse.drag.side_effect=drag
        def refresh():events.append('refresh');app.loop_active=False;return True
        app.clickRefresh=Mock(side_effect=refresh)
        with patch('e7_mouse_refresh.time.sleep'),patch.object(adb_engine.subprocess,'run') as adb:
            app.refreshShop()
        adb.assert_not_called()
        self.assertEqual(events,['buy Covenant bookmark','confirm Covenant bookmark','buy Mystic medal','confirm Mystic medal','drag','refresh'])
        self.assertEqual([item.count for item in app.storage.inventory.values()],[1,1])
        self.assertEqual(app.refresh_count,1)

    def test_offline_item_check_never_constructs_mouse_transport(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'shop.png';Image.fromarray(shop()).save(path)
            with patch('e7_shop_flow.read_ui_text',return_value=dict(words=[])),patch('e7_mouse_refresh.create_navigator') as navigator,patch('e7_mouse_refresh.WindowsMouse') as transport:
                result=inspect_mouse_items(path,Path(adb_engine.__file__).parent/'adb-assets')
            navigator.return_value.require_shop.assert_called_once()
            transport.assert_not_called()
            self.assertEqual(result,dict(read_only=True,state='shop',items=[]))

    def test_currencies_revealed_by_drag_are_bought_before_refresh(self):
        app=self.make_engine();self.add_real_currencies(app);app.budget=3
        exposed=[False];events=[]
        page=scrolled();page[220:300,1550:1810]=(20,110,40);page[650:730,1550:1810]=(20,110,40)
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(page if exposed[0] else shop())
        self.ui_ocr.side_effect=lambda rgb,region,**kwargs:dict(words=(currency_words('Covenant bookmark')+currency_words('Mystic medal',430)) if exposed[0] else [])
        def drag(*args,**kw):exposed[0]=True;events.append('drag')
        def buy(pos):events.append('buy '+app._item_name);return True
        def refresh():events.append('refresh');app.loop_active=False;return True
        app.mouse.drag.side_effect=drag;app.clickBuy=Mock(side_effect=buy);app.clickRefresh=Mock(side_effect=refresh)
        with patch('e7_mouse_refresh.time.sleep'):
            app.refreshShop()
        self.assertEqual(events,['drag','buy Covenant bookmark','buy Mystic medal','refresh'])
        self.assertEqual([item.count for item in app.storage.inventory.values()],[1,1])
        self.assertEqual(app.refresh_count,1)

    def test_one_row_still_moving_keeps_the_list_unsettled(self):
        # Linux Steam 2026-11-14: one row still animating is too small a change
        # for a whole-list average, so the list counted as settled too early.
        from e7_shop_flow import list_change,list_view,LIST_STILL
        base=shop();base[220:300,1550:1810]=base[420:500,1550:1810]=base[620:700,1550:1810]=(20,110,40)
        def with_block(x):
            frame=base.copy();frame[520:580,x:x+60]=230;return frame
        a,b=list_view(with_block(900)),list_view(with_block(1000))
        self.assertLess(float(np.mean(np.abs(a-b))),LIST_STILL)  # the old whole-list test saw "still"
        self.assertGreater(list_change(a,b),LIST_STILL)
        app=self.make_engine();app.fast_waits=True
        frames=[with_block(800+40*i) for i in range(6)]+[with_block(1100)]*8
        app.mouse.screenshot.side_effect=[Image.fromarray(f) for f in frames]
        clock=itertools.count(0,.05)
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)):
            frame=app._settled_screenshot(2.5,'inventory settle')
        self.assertIsNotNone(frame)
        self.assertEqual(int(app._rgb[550,1110,0]),230)  # the row at its final place
        self.assertGreaterEqual(app.mouse.screenshot.call_count,6+4)

    def test_next_item_is_searched_on_a_settled_list_after_a_purchase(self):
        # Orlando 2026-11-14: right after a purchase the list still slides; an
        # item located on that moving frame is not where Buy then lands.
        app=self.make_engine();self.add_real_currencies(app);app.budget=3
        animating=[0];events=[]
        page=shop();page[220:300,1550:1810]=(20,110,40);page[650:730,1550:1810]=(20,110,40)
        moving=shop();moving[220:300,1550:1810]=(20,110,40);moving[590:670,1550:1810]=(20,110,40)
        dragged=[False]
        def capture():
            if animating[0]:
                animating[0]-=1;return Image.fromarray(moving)
            return Image.fromarray(scrolled(page) if dragged[0] else page)
        app.mouse.screenshot.side_effect=capture
        app.mouse.drag.side_effect=lambda *args,**kw:dragged.__setitem__(0,True)
        def words(rgb,region,**kwargs):
            offset=370 if tuple(app._rgb[700,1600])!=(20,110,40) else 430
            return dict(words=currency_words('Covenant bookmark')+currency_words('Mystic medal',offset))
        self.ui_ocr.side_effect=words
        def buy(pos):
            events.append((app._item_name,round(pos[1])))
            animating[0]=2;app.takeScreenshot()  # clickBuy's own capture lands mid-slide
            return True
        def refresh():app.loop_active=False;return True
        app.clickBuy=Mock(side_effect=buy);app.clickRefresh=Mock(side_effect=refresh)
        with patch('e7_mouse_refresh.time.sleep'):
            app.refreshShop()
        self.assertEqual(events[:2],[('Covenant bookmark',260),('Mystic medal',690)])

    def test_a_drag_the_game_cancelled_is_sent_once_more_before_page_two(self):
        # Orlando 2026-11-14, windowed: a pointer crossing the game cancelled
        # the drag, page two was page one again and its Friendship was missed.
        app=self.make_engine();self.add_real_currencies(app);app.budget=3
        drags=[0];events=[]
        page=scrolled();page[650:730,1550:1810]=(20,110,40)
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(page if drags[0]>=2 else shop())
        self.ui_ocr.side_effect=lambda rgb,region,**kwargs:dict(words=currency_words('Mystic medal',430) if drags[0]>=2 else [])
        def drag(*args,**kw):drags[0]+=1;events.append('drag')
        def buy(pos):events.append('buy '+app._item_name);return True
        def refresh():events.append('refresh');app.loop_active=False;return True
        app.mouse.drag.side_effect=drag;app.clickBuy=Mock(side_effect=buy);app.clickRefresh=Mock(side_effect=refresh)
        with patch('e7_mouse_refresh.time.sleep'),contextlib.redirect_stdout(io.StringIO()) as output:
            app.refreshShop()
        self.assertEqual(events,['drag','drag','buy Mystic medal','refresh'])
        self.assertIn('The list did not scroll; dragging once more.',output.getvalue())

    def test_odd_frame_after_a_cancelled_drag_does_not_pass_for_a_scrolled_list(self):
        # A pointer pause can cancel the drag and hand back one frame that is
        # not the shop. That frame differs from page one; judged as it is, the
        # list would count as scrolled and Refresh would follow an unchecked
        # page two. The scroll is judged on the verified shop frame instead.
        app=self.make_engine();self.add_real_currencies(app);app.budget=3
        drags=[0];events=[];odd=[False]
        page=scrolled();page[650:730,1550:1810]=(20,110,40)
        blank=np.full((1080,1920,3),200,dtype=np.uint8)
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(blank if odd[0] else page if drags[0]>=2 else shop())
        def visible(frame):
            if frame.mean()>150:
                odd[0]=False;return False
            return True
        app.navigation.shop_visible.side_effect=visible
        self.ui_ocr.side_effect=lambda rgb,region,**kwargs:dict(words=currency_words('Mystic medal',430) if drags[0]>=2 else [])
        def drag(*args,**kw):
            drags[0]+=1;events.append('drag');odd[0]=drags[0]==1
        def buy(pos):events.append('buy '+app._item_name);return True
        def refresh():events.append('refresh');app.loop_active=False;return True
        app.mouse.drag.side_effect=drag;app.clickBuy=Mock(side_effect=buy);app.clickRefresh=Mock(side_effect=refresh)
        with patch('e7_mouse_refresh.time.sleep'),contextlib.redirect_stdout(io.StringIO()) as output:
            app.refreshShop()
        self.assertEqual(events,['drag','drag','buy Mystic medal','refresh'])
        self.assertIn('The list did not scroll; dragging once more.',output.getvalue())

    def test_ignored_drags_stop_before_refresh(self):
        app=self.make_engine();self.add_real_currencies(app);app.budget=3
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(shop())
        app.clickRefresh=Mock(return_value=True)
        with patch('e7_mouse_refresh.time.sleep'),self.assertRaisesRegex(MouseStopped,'did not move after three drags'):
            app.refreshShop()
        self.assertEqual(app.mouse.drag.call_count,3)
        down,up=app.mouse.drag.call_args_list[0].args,app.mouse.drag.call_args_list[2].args
        self.assertLess(down[3],down[1]);self.assertGreater(up[3],up[1])
        app.clickRefresh.assert_not_called()

    def test_shop_left_scrolled_to_the_bottom_checks_the_top_rows(self):
        # Session started on a shop already scrolled down: drags down do
        # nothing, a drag up reveals the top rows and their item is bought.
        app=self.make_engine();self.add_real_currencies(app);app.budget=3
        at_top=[False];events=[]
        top=scrolled();top[220:300,1550:1810]=(20,110,40)
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(top if at_top[0] else shop())
        self.ui_ocr.side_effect=lambda rgb,region,**kwargs:dict(words=currency_words('Covenant bookmark') if at_top[0] else [])
        def drag(x1,y1,x2,y2,**kw):
            events.append('up' if y2>y1 else 'down')
            if y2>y1:at_top[0]=True
        def buy(pos):events.append('buy '+app._item_name);return True
        def refresh():events.append('refresh');app.loop_active=False;return True
        app.mouse.drag.side_effect=drag;app.clickBuy=Mock(side_effect=buy);app.clickRefresh=Mock(side_effect=refresh)
        with patch('e7_mouse_refresh.time.sleep'):
            app.refreshShop()
        self.assertEqual(events,['down','down','up','buy Covenant bookmark','refresh'])

    def test_shared_loop_enforces_four_refreshes_for_twelve_skystones(self):
        app = self.make_engine()
        state = ['shop']; dragged = [False]
        def screenshot(): return Image.fromarray(dialog() if state[0]=='confirm' else scrolled() if dragged[0] else shop())
        def click(x,y): state[0] = 'confirm' if y>900 else 'shop'; dragged[0] = False
        app.mouse.screenshot.side_effect = screenshot
        app.mouse.click.side_effect = click
        app.mouse.drag.side_effect = lambda *args,**kw: dragged.__setitem__(0,True)
        with patch.object(adb_engine.time,'sleep'),patch.object(adb_engine.subprocess,'run') as adb, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            app.refreshShop()
        adb.assert_not_called()
        self.assertEqual(app.refresh_count,4)
        self.assertEqual(app.mouse.click.call_count,8)
        self.assertEqual(app.mouse.drag.call_count,5)
        stats = [json.loads(line.split(' ',1)[1]) for line in output.getvalue().splitlines() if line.startswith('E7GUI_STATS ')]
        self.assertEqual(stats[-1]['skystone_spent'],12)
        app.storage.writeToCSV.assert_called_once()

    def test_native_swipe_preserves_vertical_coverage_with_small_variation(self):
        app=self.make_engine();del app.generateOffset
        app.x_offset,app.y_offset=75,25
        for enabled in (False,True):
            app.random_offset=enabled
            with patch('E7ADBShopRefresh.random.randint',side_effect=[75,-25]),patch('e7_mouse_refresh.random.uniform',side_effect=[.36,-3]):
                dx,dy=app.generateSwipeOffset()
                app.swipe(1200+dx,808+dy,1200+dx,392+dy)
            args=app.mouse.drag.call_args
            self.assertEqual(args.args,(1212,802,1209,386) if enabled else (1200,808,1200,392))
            self.assertEqual(args.kwargs,dict(duration=.36 if enabled else .32))
            self.assertEqual(args.args[1]-args.args[3],416)

    def test_adb_swipe_offsets_keep_the_existing_range(self):
        app=adb_engine.E7ADBShopRefresh.__new__(adb_engine.E7ADBShopRefresh)
        app.generateOffset=Mock(return_value=(75,-25))
        self.assertEqual(app.generateSwipeOffset(),(75,-25))
        app.generateOffset.assert_called_once()

    def test_insufficient_currency_or_wrong_confirmation_never_receives_second_click(self):
        for text in ('Not enough Skystone. Cancel Confirm Refresh 3 Skystone',
                     'Cancel Confirm Purchase Skystone', 'Cancel Confirm Covenant 184,000', ''):
            app = self.make_engine()
            app.read_confirmation_text = lambda _,text=text:text
            app.mouse.screenshot.side_effect = [Image.fromarray(shop()),Image.fromarray(dialog()),Image.fromarray(dialog())]
            with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,1,6]):
                with self.assertRaisesRegex(MouseStopped,'does not match'):
                    app.clickRefresh()
            self.assertEqual(app.mouse.click.call_count,1)
            app._save_confirmation_failure.assert_called_once()

    def test_partial_confirmation_text_is_recaptured_before_confirming_each_action(self):
        for operation,name,text in (('refresh',None,'Use Skystone to refresh? Cancel Confirm'),
                                    ('buy','Covenant bookmark','Cancel Buy Covenant Bookmarks 184,000'),
                                    ('buy','Mystic medal','Cancel Buy Mystic Medals 280,000')):
            with self.subTest(operation=operation,item=name):
                app=self.make_engine();app._item_name=name
                app.read_confirmation_text=Mock(side_effect=['Cancel Confirm',text,text])
                app.mouse.screenshot.side_effect=[Image.fromarray(image) for image in (dialog(operation),dialog(operation),dialog(operation),shop())]
                with patch('e7_mouse_refresh.time.sleep'):
                    self.assertTrue(app._confirm(operation,shop()))
                self.assertEqual(app.read_confirmation_text.call_count,3)
                self.assertEqual(app.mouse.click.call_count,1)
                app._save_confirmation_failure.assert_not_called()

    def test_refresh_rechecks_shop_after_undelivered_click_visibility_failure(self):
        app=self.make_engine();state=['shop'];attempts=[0]
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(shop() if state[0]=='shop' else dialog())
        def click(x,y):
            attempts[0]+=1
            if attempts[0]==1:raise MouseRecheckRequired('temporary coverage')
            state[0]='confirm' if y>900 else 'shop'
        app.mouse.click.side_effect=click
        with patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickRefresh())
        self.assertEqual(attempts[0],3)
        self.assertEqual(app.navigation.require_shop.call_count,2)

    def test_confirmation_recovery_rereads_prompt_and_does_not_reclick_refresh(self):
        for changed in (False,True):
            with self.subTest(changed=changed):
                app=self.make_engine();state=['shop'];attempts=[]
                app.mouse.screenshot.side_effect=lambda:Image.fromarray(shop() if state[0]=='shop' else dialog())
                valid='Use Skystone to refresh? Cancel Confirm'
                texts=iter([valid,valid]+([] if changed else [valid,valid]))
                app.read_confirmation_text=Mock(side_effect=lambda rgb:next(texts,'Cancel Buy Covenant Bookmarks 184,000'))
                def click(x,y):
                    attempts.append(y)
                    if len(attempts)==2:raise MouseRecheckRequired('temporary coverage')
                    state[0]='confirm' if y>900 else 'shop'
                app.mouse.click.side_effect=click
                with patch('e7_mouse_refresh.time.sleep'):
                    if changed:
                        # A clock that keeps advancing, so the 5 s confirmation deadline always expires.
                        clock=itertools.count()
                        with patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)),self.assertRaises(MouseStopped):
                            app.clickRefresh()
                    else:self.assertTrue(app.clickRefresh())
                self.assertEqual(sum(y>900 for y in attempts),1)
                self.assertEqual(len(attempts),2 if changed else 3)
                self.assertGreaterEqual(app.read_confirmation_text.call_count,3)

    def test_home_menu_recovery_recognizes_new_target_before_click(self):
        app=self.make_engine();state=['home'];targets=iter([(84,498),(84,498),(90,499),(90,499)])
        app.navigation.shop_visible.side_effect=lambda _:state[0]=='shop'
        app._home_menu_target=Mock(side_effect=lambda _:next(targets))
        def click(x,y):
            if app.mouse.click.call_count==1:raise MouseRecheckRequired('temporary coverage')
            state[0]='shop'
        app.mouse.click.side_effect=click
        with patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickShop())
        self.assertEqual([call.args for call in app.mouse.click.call_args_list],[(84,498),(90,499)])
        self.assertEqual(app._home_menu_target.call_count,4)

    def test_repeated_visibility_failure_is_bounded_and_stop_is_not_retried(self):
        app=self.make_engine();app.mouse.click.side_effect=MouseRecheckRequired('temporary coverage')
        with self.assertRaisesRegex(MouseStopped,'three recognition'):
            app.clickRefresh()
        self.assertEqual(app.mouse.click.call_count,3)
        app=self.make_engine()
        def stop(*_):
            app.loop_active=False
            raise MouseRecheckRequired('temporary coverage')
        app.mouse.click.side_effect=stop
        self.assertFalse(app.clickRefresh())
        self.assertEqual(app.mouse.click.call_count,1)

    def test_scroll_recovery_requires_a_fresh_shop_before_retry(self):
        app=self.make_engine();app.mouse.drag.side_effect=[MouseRecheckRequired('temporary coverage'),None]
        with patch('e7_mouse_refresh.time.sleep'):
            app.swipe(1200,808,1200,392)
        self.assertEqual(app.mouse.drag.call_count,2)
        app.navigation.require_shop.assert_called_once()
        app=self.make_engine();app.mouse.drag.side_effect=MouseRecheckRequired('temporary coverage')
        app.navigation.require_shop.side_effect=MouseStopped('not the shop')
        with self.assertRaisesRegex(MouseStopped,'not the shop'):
            app.swipe(1200,808,1200,392)
        self.assertEqual(app.mouse.drag.call_count,1)

    def test_stop_during_rejected_confirmation_text_never_retries_or_clicks(self):
        app=self.make_engine();app.mouse.screenshot.return_value=Image.fromarray(dialog())
        def read(_):
            app.loop_active=False
            return 'Cancel Confirm'
        app.read_confirmation_text=read
        with patch('e7_mouse_refresh.time.sleep'):
            self.assertFalse(app._confirm('refresh',shop()))
        self.assertEqual(app.mouse.screenshot.call_count,1)
        app.mouse.click.assert_not_called()

    def test_confirmation_changing_during_ocr_is_not_clicked(self):
        import itertools
        app = self.make_engine();clock=itertools.count(0,.05)
        frames = itertools.chain((shop(),dialog()),itertools.repeat(shop()))  # dialog vanishes after one read
        app.mouse.screenshot.side_effect = lambda:Image.fromarray(next(frames))
        with patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)):
            with self.assertRaisesRegex(MouseStopped,'kept changing while'):
                app.clickRefresh()
        self.assertEqual(app.mouse.click.call_count,1)  # Refresh only

    def test_consecutive_refreshes_accept_animated_background_and_small_button_jitter(self):
        app=self.make_engine();app.budget=6
        state=['shop'];reads=[0];dragged=[False]
        def screenshot():
            image=(scrolled() if dragged[0] else shop()) if state[0]=='shop' else dialog()
            if state[0]=='confirm':
                reads[0]+=1
                image[300:500,550:1450]=40 if reads[0]%2 else 100
            return Image.fromarray(image)
        def click(x,y):state[0]='confirm' if y>900 else 'shop';dragged[0]=False
        app.mouse.screenshot.side_effect=screenshot;app.mouse.click.side_effect=click
        app.mouse.drag.side_effect=lambda *args,**kw:dragged.__setitem__(0,True)
        original=confirmation_button
        observed=[]
        def button(rgb,operation,before):
            box=original(rgb,operation,before)
            if box is not None:
                box=tuple(v+(1 if reads[0]%2==0 else 0) for v in box)
                observed.append(box)
            return box
        with patch('e7_shop_flow.confirmation_button',side_effect=button),patch('e7_mouse_refresh.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
            app.refreshShop()
        self.assertEqual(app.refresh_count,2)
        self.assertEqual(app.mouse.click.call_count,4)
        self.assertEqual([call.args for call in app.mouse.click.call_args_list[1::2]],
                         [((box[0]+box[2])/2,(box[1]+box[3])/2) for box in observed[1::2]])
        app._save_confirmation_failure.assert_not_called()

    def test_fresh_confirmation_must_still_match_item_cost_and_action(self):
        for operation,name,initial,changed in (
            ('refresh',None,'Use Skystone to refresh? Cancel Confirm','Cancel Buy Covenant Bookmarks 184,000'),
            ('refresh',None,'Use Skystone to refresh? Cancel Confirm','Not enough Skystone Cancel Confirm Refresh 3 Skystone'),
            ('buy','Covenant bookmark','Cancel Buy Covenant Bookmarks 184,000','Cancel Buy Mystic Medals 280,000'),
            ('buy','Mystic medal','Cancel Buy Mystic Medals 280,000','Cancel Buy Mystic Medals 184,000')):
            with self.subTest(operation=operation,item=name):
                app=self.make_engine();app._item_name=name
                app.mouse.screenshot.return_value=Image.fromarray(dialog(operation))
                app.read_confirmation_text=Mock(side_effect=[initial,changed])
                with patch('e7_mouse_refresh.time.sleep'):
                    with self.assertRaisesRegex(MouseStopped,'changed while'):
                        app._confirm(operation,shop())
                app.mouse.click.assert_not_called()
                self.assertIn('validated',app._save_confirmation_failure.call_args.kwargs)

    def test_large_confirmation_button_movement_is_not_clicked(self):
        app=self.make_engine();app.mouse.screenshot.return_value=Image.fromarray(dialog())
        import itertools
        boxes=itertools.cycle(((1040,650,1290,740),(1060,650,1310,740)));clock=itertools.count(0,.05)
        with patch('e7_shop_flow.confirmation_button',side_effect=lambda *a:next(boxes)),patch('e7_mouse_refresh.time.sleep'), \
                patch('e7_mouse_refresh.time.monotonic',side_effect=lambda:next(clock)):
            with self.assertRaisesRegex(MouseStopped,'kept changing while'):
                app._confirm('refresh',shop())
        app.mouse.click.assert_not_called()

    def test_stop_during_fresh_confirmation_ocr_prevents_click(self):
        app=self.make_engine();app.mouse.screenshot.return_value=Image.fromarray(dialog())
        def read(_):
            app.loop_active=False
            return 'Use Skystone to refresh? Cancel Confirm'
        app.read_confirmation_text=Mock()
        app.read_confirmation_text.side_effect=lambda rgb: read(rgb) if app.read_confirmation_text.call_count==2 else 'Use Skystone to refresh? Cancel Confirm'
        with patch('e7_mouse_refresh.time.sleep'):
            self.assertFalse(app._confirm('refresh',shop()))
        self.assertEqual(app.mouse.screenshot.call_count,2)
        app.mouse.click.assert_not_called()

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
        self.assertTrue(confirmation_matches('Use Skystone to refresh? Cancel Confirm','refresh'))
        self.assertFalse(confirmation_matches('Use Skystone to refresh? 30 Cancel Confirm','refresh'))
        self.assertFalse(confirmation_matches('Use Skystone to refresh? Not enough Skystone Cancel Confirm','refresh'))
        self.assertTrue(confirmation_matches('Cancel Confirm Covenant Bookmark 184,000','buy','Covenant bookmark'))
        self.assertFalse(confirmation_matches('Cancel Confirm Mystic Medal 184,000','buy','Covenant bookmark'))
        self.assertFalse(confirmation_matches('Cancel Confirm Covenant Bookmark 280,000','buy','Covenant bookmark'))
        # Windows OCR on the STOVE windowed Covenant dialog (Orlando, 2026-11-14)
        # reads the gold coin as a leading 0. The price is unchanged; any other
        # extra digit still changes it and is rejected.
        self.assertTrue(confirmation_matches('would you like to purchase this product? cancel summon covenant bookmarks 0184,000 buy','buy','Covenant bookmark'))
        self.assertTrue(confirmation_matches('Cancel Buy Mystic Medals 0280,000','buy','Mystic medal'))
        for text in ('Cancel Buy Covenant Bookmarks 8184,000','Cancel Buy Covenant Bookmarks 1840,000',
                     'Cancel Buy Covenant Bookmarks 0280,000','Cancel Buy Covenant Bookmarks 0184,000 0280,000'):
            self.assertFalse(confirmation_matches(text,'buy','Covenant bookmark'),text)


def cv_gray(rgb):
    import cv2
    return cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)


if __name__ == '__main__':
    unittest.main()
