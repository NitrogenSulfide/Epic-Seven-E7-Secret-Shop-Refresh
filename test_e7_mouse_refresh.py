"""Fake native input and synthetic shop/dialog tests. Never operate the desktop."""
import contextlib
import ctypes
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
from PIL import Image, ImageDraw
import E7ADBShopRefresh as adb_engine
from e7_windows_capture import GameWindow
from e7_native_mouse import WindowsMouse, MouseStopped, Input, verify_native_target, physical_pixel_coordinates, process_is_elevated, require_mouse_permissions, pointer_glide
from e7_mouse_refresh import E7MouseShopRefresh, confirmation_button, green_buttons, home_menu_target, home_icon_target, hidden_home_matches, reframed_home_matches, idle_home_candidate, currency_button, IncompleteCurrencyRow, inspect_mouse_items
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


def currency_words(name,offset=0,price=None):
    prefix,noun,normal_price = ('covenant','bookmarks','184,000') if name=='Covenant bookmark' else ('mystic','medals','280,000')
    fields = [('summon',[1035,155,1135,180]),(prefix,[1035,205,1160,237]),
              (noun,[1170,205,1335,237]),(price or normal_price,[1684,168,1786,199]),
              ('buy',[1711,244,1757,276]),('only',[1035,255,1085,285]),
              ('1',[1094,255,1103,285]),('available',[1114,255,1220,285])]
    return [dict(text=text,box=[box[0],box[1]+offset,box[2],box[3]+offset]) for text,box in fields]


class CurrencyRowTests(unittest.TestCase):
    def test_each_currency_requires_its_own_name_price_category_and_buy(self):
        for name in ('Covenant bookmark','Mystic medal'):
            words=currency_words(name)
            self.assertEqual(currency_button(dict(words=words),[(1550,220,1810,300)],name),(1711,244,1757,276))
            for omitted in ('summon','buy'):
                with self.subTest(name=name,omitted=omitted),self.assertRaises(MouseStopped):
                    currency_button(dict(words=[word for word in words if word['text']!=omitted]),[(1550,220,1810,300)],name)

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
        words=currency_words('Mystic medal')
        for word in words:
            if word['text']=='1':word['text']='0'
        self.assertIsNone(currency_button(dict(words=words),[],'Mystic medal'))
        self.assertIsNotNone(currency_button(dict(words=words),[(1550,220,1810,300)],'Mystic medal'))


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
            with self.assertRaisesRegex(MouseStopped,'restart to recognize'):
                self.mouse.click(436,994)
        self.sender.assert_not_called()

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
        self.ocr_patch=patch('e7_mouse_refresh.read_ui_text',return_value=dict(text='',words=[]))
        self.ui_ocr=self.ocr_patch.start();self.addCleanup(self.ocr_patch.stop)

    def make_engine(self):
        app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        app.loop_active,app.end_of_refresh = True,False
        app.budget,app.tap_sleep,app.debug = 12,.3,False
        app.random_offset=False
        app.screenwidth,app.screenheight = 1920,1080
        app.refresh_count = 0; app.stop_refresh_key = '`'
        app.generateOffset = lambda:(0,0)
        app._rgb = shop(); app._item = None; app._item_name = None
        app.read_confirmation_text = lambda _:'Cancel Confirm Refresh Secret Shop 3 Skystone Covenant bookmark 184,000 Mystic medal 280,000'
        app.read_navigation_text = Mock(return_value=dict(text='',words=[]))
        app.mouse = Mock()
        app._save_confirmation_failure=Mock(return_value=False)
        app._save_home_failure=Mock(return_value=False)
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
        with patch('e7_mouse_refresh.hidden_home_matches',return_value=True),patch('e7_mouse_refresh.time.sleep'):
            self.assertTrue(app.clickShop())
        app.mouse.move.assert_not_called()
        self.assertEqual([call.args for call in app.mouse.click.call_args_list],[(960,540),(100,580.5)])

    def test_unfamiliar_idle_artwork_reveals_once_then_requires_observed_shop_menu(self):
        app=self.make_engine()
        artwork=np.random.default_rng(42).integers(0,255,(1080,1920,3),dtype=np.uint8)
        visible=shop();visible[561:590,75:95]=230;visible[565:600,105:125]=230
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (artwork,artwork,visible,visible,shop())]
        app.navigation.shop_visible.side_effect=[False,False,True]
        app.navigation.menu_target.side_effect=[None,(97,635),(97,635)]
        self.ui_ocr.return_value=dict(text='',words=[])
        with patch('e7_mouse_refresh.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'):
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
        with patch('e7_mouse_refresh.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,0,31]):
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

    def test_idle_reveal_rechecks_full_screen_for_new_dialog_before_click(self):
        app=self.make_engine()
        app.mouse.screenshot.return_value=Image.fromarray(np.random.default_rng(42).integers(0,255,(1080,1920,3),dtype=np.uint8))
        app.navigation.shop_visible.return_value=False
        app.navigation.menu_target.return_value=None
        self.ui_ocr.side_effect=[dict(text='',words=[]),dict(text='Cancel Confirm',words=[])]
        with patch('e7_mouse_refresh.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,31]):
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
        with tempfile.TemporaryDirectory() as temp,patch('e7_mouse_refresh.Path',side_effect=lambda path:Path(temp)/path):
            self.assertTrue(E7MouseShopRefresh._save_home_failure(app,True))
            folders=list((Path(temp)/'mouse-failures').iterdir());self.assertEqual(len(folders),1)
            with Image.open(folders[0]/'home-menu.png') as image:self.assertEqual(image.size,(420,740))
            data=json.loads((folders[0]/'failure.json').read_text())
            self.assertTrue(data['reveal_clicked']);self.assertFalse(data['shop_clicked'])
            self.assertEqual(data['home_ocr'],app._last_home_ocr)

    def test_unknown_screen_sends_no_pointer_input(self):
        app=self.make_engine(); app.navigation.shop_visible.return_value=False
        app.navigation.menu_target.return_value=None
        with patch('e7_mouse_refresh.hidden_home_matches',return_value=False),patch('e7_mouse_refresh.time.sleep'),patch('e7_mouse_refresh.time.monotonic',side_effect=[0,0,0,31]):
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
            with patch('e7_mouse_refresh.Path',side_effect=lambda name:root/name):
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

    def test_refresh_uses_recognized_label_then_observed_confirmation(self):
        app = self.make_engine()
        app.mouse.screenshot.side_effect = [Image.fromarray(frame) for frame in (shop(),dialog(),dialog(),shop())]
        with patch('e7_mouse_refresh.time.sleep'),patch.object(adb_engine.subprocess,'run') as adb:
            self.assertTrue(app.clickRefresh())
        adb.assert_not_called()
        self.assertEqual(app.mouse.click.call_args_list[0].args,(436,994))
        self.assertEqual(app.mouse.click.call_args_list[1].args,(1165,695))
        self.assertEqual(app.refresh_count,0)  # Only the shared loop increments.

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
        self.assertEqual([call.args[0] for call in sleep.call_args_list],[.67,.67])

    def test_mouse_confirmation_resamples_delay_for_each_tap(self):
        app=self.make_engine();app.random_offset=True
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (shop(),dialog(),dialog(),shop())]
        with patch.object(adb_engine.random, 'uniform', side_effect=[-.03,.03]), patch('e7_mouse_refresh.time.sleep') as sleep:
            self.assertTrue(app.clickRefresh())
        self.assertEqual([round(call.args[0],2) for call in sleep.call_args_list],[.27,.33])
        self.assertEqual(app.tap_sleep,.3)

    def test_adjustable_mouse_timing_samples_full_selected_range(self):
        app=self.make_engine();app.random_offset=True;app.tap_jitter=.1
        app.mouse.screenshot.side_effect=[Image.fromarray(frame) for frame in (shop(),dialog(),dialog(),shop())]
        with patch.object(adb_engine.random,'uniform',side_effect=[-.1,.1]),patch('e7_mouse_refresh.time.sleep') as sleep:
            self.assertTrue(app.clickRefresh())
        self.assertEqual([round(call.args[0],2) for call in sleep.call_args_list],[.2,.4])

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
                self.assertTrue(E7MouseShopRefresh._save_confirmation_failure(app,'refresh',shop()))
                folder=next(Path('mouse-failures').iterdir())
                with Image.open(folder/'dialog.png') as saved:
                    self.assertEqual(saved.size,(950,740))
                self.assertFalse(json.loads((folder/'failure.json').read_text())['confirmation_clicked'])
                with patch('e7_mouse_refresh.Path.mkdir',side_effect=OSError('read only')):
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

    def add_real_currencies(self,app):
        for filename,name,price in (('cov.png','Covenant bookmark',184000),('mys.png','Mystic medal',280000)):
            path=Path(adb_engine.__file__).parent/'adb-assets'/filename
            template=adb_engine.cv2.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),adb_engine.cv2.IMREAD_GRAYSCALE)
            self.assertIsNotNone(template)
            app.storage.inventory[name]=adb_engine.E7Item(template,price)

    def test_currency_text_fallback_uses_buy_label_and_caches_only_current_capture(self):
        app=self.make_engine();self.add_real_currencies(app)
        frame=shop();frame[220:300,1550:1810]=(20,110,40);frame[650:730,1550:1810]=(20,110,40)
        app._rgb=frame;self.ui_ocr.return_value=dict(words=currency_words('Covenant bookmark')+currency_words('Mystic medal',430))
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
        bought=set();pending=[None];stage=['shop'];events=[]
        def scene():
            frame=shop()
            for name,top in (('Covenant bookmark',220),('Mystic medal',650)):
                if name not in bought:frame[top:top+80,1550:1810]=(20,110,40)
            return frame
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(dialog('buy') if stage[0]=='confirm' else scene())
        def words(rgb,region):
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
        app.mouse.click.side_effect=click;app.mouse.drag.side_effect=lambda *args,**kw:events.append('drag')
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
            with patch('e7_mouse_refresh.create_navigator') as navigator,patch('e7_mouse_refresh.WindowsMouse') as transport:
                result=inspect_mouse_items(path,Path(adb_engine.__file__).parent/'adb-assets')
            navigator.return_value.require_shop.assert_called_once()
            transport.assert_not_called()
            self.assertEqual(result,dict(read_only=True,state='shop',items=[]))

    def test_currencies_revealed_by_drag_are_bought_before_refresh(self):
        app=self.make_engine();self.add_real_currencies(app);app.budget=3
        exposed=[False];events=[]
        page=shop();page[220:300,1550:1810]=(20,110,40);page[650:730,1550:1810]=(20,110,40)
        app.mouse.screenshot.side_effect=lambda:Image.fromarray(page if exposed[0] else shop())
        self.ui_ocr.side_effect=lambda rgb,region:dict(words=(currency_words('Covenant bookmark')+currency_words('Mystic medal',430)) if exposed[0] else [])
        def drag(*args,**kw):exposed[0]=True;events.append('drag')
        def buy(pos):events.append('buy '+app._item_name);return True
        def refresh():events.append('refresh');app.loop_active=False;return True
        app.mouse.drag.side_effect=drag;app.clickBuy=Mock(side_effect=buy);app.clickRefresh=Mock(side_effect=refresh)
        with patch('e7_mouse_refresh.time.sleep'):
            app.refreshShop()
        self.assertEqual(events,['drag','buy Covenant bookmark','buy Mystic medal','refresh'])
        self.assertEqual([item.count for item in app.storage.inventory.values()],[1,1])
        self.assertEqual(app.refresh_count,1)

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
        self.assertTrue(confirmation_matches('Use Skystone to refresh? Cancel Confirm','refresh'))
        self.assertFalse(confirmation_matches('Use Skystone to refresh? 30 Cancel Confirm','refresh'))
        self.assertFalse(confirmation_matches('Use Skystone to refresh? Not enough Skystone Cancel Confirm','refresh'))
        self.assertTrue(confirmation_matches('Cancel Confirm Covenant Bookmark 184,000','buy','Covenant bookmark'))
        self.assertFalse(confirmation_matches('Cancel Confirm Mystic Medal 184,000','buy','Covenant bookmark'))
        self.assertFalse(confirmation_matches('Cancel Confirm Covenant Bookmark 280,000','buy','Covenant bookmark'))


def cv_gray(rgb):
    import cv2
    return cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)


if __name__ == '__main__':
    unittest.main()
