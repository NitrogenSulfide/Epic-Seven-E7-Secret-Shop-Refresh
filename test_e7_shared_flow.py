"""Same action loop through fake ADB/Windows transports. Never access a game."""
import contextlib,io,json,random,unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock,patch
import cv2
import numpy as np
from PIL import Image
from E7ADBShopRefresh import E7ADBShopRefresh,E7Inventory,E7Item
from e7_mouse_refresh import E7MouseShopRefresh
from e7_shop_flow import ObservedShopFlow
from e7_shop_navigation import create_navigator,REFERENCE_BOXES
from e7_mouse_confirmation import confirmation_matches,read_confirmation_text
from e7_frame import FrameGeometry,normalize_game_frame
from e7_native_mouse import MouseStopped,MouseRecheckRequired

def base_image():
    rgb=np.full((1080,1920,3),30,dtype=np.uint8)
    # Stable rendering detail makes this a valid, nonblank device capture.
    rgb[10:70,1700:1800]=(60,90,140)
    return rgb

def shop_image(with_items=False):
    rgb=base_image();nav=create_navigator('adb-assets').navigators[-1][1]
    for name in ('shop-title.png','refresh-label.png'):
        x,y,_,_=REFERENCE_BOXES[name];reference=nav.references[name]
        h,w=reference.shape;rgb[y:y+h,x:x+w]=reference[:,:,None]
    if with_items:
        for name,y in (('cov.png',220),('mys.png',470)):
            icon=cv2.imread('adb-assets/'+name);h,w=icon.shape[:2]
            rgb[y:y+h,800:800+w]=cv2.cvtColor(icon,cv2.COLOR_BGR2RGB)
            rgb[y+25:y+105,1570:1850]=(20,110,40)
    return rgb

def home_image(wallpaper):
    rgb=wallpaper.copy()
    for name,y in (('sanctuary',296),('secret-shop',498),('epic-pass',598)):
        icon=cv2.imread('adb-assets/builtin-navigation/native-'+name+'-icon.png',cv2.IMREAD_GRAYSCALE)
        h,w=icon.shape;x=84-w//2;top=y-h//2
        rgb[top:top+h,x:x+w]=np.maximum(rgb[top:top+h,x:x+w],icon[:,:,None])
    return rgb

def dialog_image(operation):
    rgb=shop_image();rgb[300:920,550:1400]=90
    y=650 if operation=='refresh' else 720
    rgb[y:y+90,1040:1290]=(20,110,40)
    return rgb

class SharedFlowTests(unittest.TestCase):
    def make_app(self,mode,width=1920,wallpaper=None,items=False):
        app=(E7ADBShopRefresh if mode=='adb' else E7MouseShopRefresh).__new__(E7ADBShopRefresh if mode=='adb' else E7MouseShopRefresh)
        app.loop_active=True;app.end_of_refresh=False;app.debug=False;app.budget=6
        app.tap_sleep=.3;app.random_offset=True;app.tap_jitter=.1
        app.x_offset,app.y_offset=75,25;app.screenwidth,app.screenheight=1920,1080
        app.refresh_count=0;app._rgb=None;app._item=app._item_name=None;app._scan_page=1
        app._adb_geometry=None;app._capture_resumed=False
        app.adb_path='NEVER-RUN-ADB';app.device_args=['-s','fake-device']
        app.navigation=create_navigator('adb-assets');app.read_navigation_text=Mock(return_value=dict(text='',words=[]))
        app.storage=E7Inventory()
        for name,filename,price in (('Covenant bookmark','cov.png',184000),('Mystic medal','mys.png',280000)):
            app.storage.inventory[name]=E7Item(cv2.imread('adb-assets/'+filename,cv2.IMREAD_GRAYSCALE),price)
        app.storage.writeToCSV=Mock();app._save_home_failure=Mock(return_value=False);app._save_confirmation_failure=Mock(return_value=False)
        wallpaper=base_image() if wallpaper is None else wallpaper
        state=dict(screen='hidden',bought=set(),refreshes=0,events=[],pending=None)
        def image():
            screen=state['screen']
            rgb=wallpaper if screen=='hidden' else home_image(wallpaper) if screen=='home' else shop_image(items) if screen=='shop' else dialog_image(screen)
            if screen=='shop' and items:
                for name,y in (('Covenant bookmark',220),('Mystic medal',470)):
                    if name in state['bought']:rgb[y:y+115,780:1030]=30;rgb[y+25:y+105,1570:1850]=30
            return Image.fromarray(rgb).resize((width,round(width*9/16)),Image.Resampling.LANCZOS)
        def click(x,y):
            screen=state['screen'];state['events'].append((screen,x,y))
            if screen=='hidden':state['screen']='home'
            elif screen=='home':state['screen']='shop'
            elif screen=='shop':
                state['pending']=app._item_name if x>1400 else None
                state['screen']='buy' if state['pending'] else 'refresh'
            elif screen=='buy':state['bought'].add(state['pending']);state['screen']='shop'
            elif screen=='refresh':state['refreshes']+=1;state['bought'].clear();state['screen']='shop'
        def text(_):
            if state['screen']=='refresh':return 'Use Skystone to refresh? Cancel Confirm'
            name=state['pending'];return 'Cancel Buy Covenant Bookmarks 184,000' if name=='Covenant bookmark' else 'Cancel Buy Mystic Medals 280,000'
        app.read_confirmation_text=Mock(side_effect=text)
        if mode=='adb':
            def runner(command,**kwargs):
                self.assertTrue(kwargs['check']);self.assertEqual(kwargs['timeout'],10)
                if 'screencap' in command:
                    ok,data=cv2.imencode('.png',cv2.cvtColor(np.asarray(image()),cv2.COLOR_RGB2BGR));self.assertTrue(ok)
                    return SimpleNamespace(stdout=data.tobytes(),returncode=0)
                if 'tap' in command:
                    # Device coordinates must map back to the normalized target.
                    x,y=map(int,command[-2:]);click(x*1920/width,y*1080/round(width*9/16))
                elif 'swipe' in command:state['events'].append(('drag',))
                else:self.fail('Unexpected device operation')
                return SimpleNamespace(returncode=0)
            app._adb_runner=Mock(side_effect=runner)
        else:
            app.mouse=Mock();app.mouse.pause_revision=0;app.mouse.screenshot.side_effect=image
            app.mouse.click.side_effect=click;app.mouse.drag.side_effect=lambda *_args,**_kwargs:state['events'].append(('drag',))
        return app,state

    def test_hidden_ui_and_two_consecutive_refreshes_across_transports_and_seeded_sizes(self):
        widths=[800,1238,1920]+[random.Random(seed).randint(1000,2600) for seed in (7,41)]
        for mode in ('adb','mouse-google','mouse-stove'):
            for width in widths:
                with self.subTest(mode=mode,width=width):
                    rng=np.random.default_rng(width);wallpaper=rng.integers(10,65,(1080,1920,3),dtype=np.uint8)
                    app,state=self.make_app('adb' if mode=='adb' else 'mouse',width,wallpaper)
                    # Disable private wallpaper matching: exercise the generic reveal.
                    with patch('e7_shop_flow.hidden_home_matches',return_value=False),patch('e7_shop_flow.read_ui_text',return_value=dict(text='',words=[])),patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
                        app.refreshShop()
                    self.assertEqual(app.refresh_count,2);self.assertEqual(state['refreshes'],2)
                    self.assertEqual([event[0] for event in state['events'] if event[0]!='drag'],['hidden','home','shop','refresh','shop','refresh'])
                    app._save_confirmation_failure.assert_not_called()

    def test_both_currencies_are_bought_once_before_each_refresh_in_both_transports(self):
        for mode in ('adb','mouse'):
            app,state=self.make_app(mode,items=True);state['screen']='shop'
            with patch('e7_shop_flow.read_ui_text',return_value=dict(text='',words=[])),patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
                app.refreshShop()
            self.assertEqual(state['refreshes'],2)
            # Final generated inventory is checked even when the budget is exhausted.
            self.assertEqual([item.count for item in app.storage.inventory.values()],[3,3])
            self.assertEqual(sum(event[0]=='buy' for event in state['events']),6)

    def test_confirmation_validator_rejects_mixed_items_and_conflicting_prices(self):
        for text,operation,item in (
            ('Cancel Confirm Refresh 30 Skystone 3','refresh',None),
            ('Cancel Buy Mystic Medals 280,000 Covenant Bookmarks 184,000','buy','Covenant bookmark'),
            ('Cancel Buy Covenant Bookmarks 184,000 280,000','buy','Covenant bookmark'),
            ('Cancel Buy Covenant Equipment 184,000','buy','Covenant bookmark'),
            ('Not enough Gold Cancel Buy Mystic Medals 280,000','buy','Mystic medal')):
            self.assertFalse(confirmation_matches(text,operation,item),text)

    def test_rejected_dialogs_and_stop_prevent_confirmation_through_both_transports(self):
        for mode in ('adb','mouse'):
            for text in ('Cancel Confirm Refresh 30 Skystone 3','Not enough Skystone Cancel Confirm Refresh 3 Skystone'):
                with self.subTest(mode=mode,text=text):
                    app,state=self.make_app(mode);state['screen']='shop'
                    app.read_confirmation_text=Mock(return_value=text)
                    with patch('e7_shop_flow.time.sleep'),patch('e7_shop_flow.time.monotonic',side_effect=[0,0,6]),self.assertRaises(MouseStopped):
                        app.clickRefresh()
                    self.assertEqual([event[0] for event in state['events']],['shop'])
                    self.assertEqual(state['refreshes'],0)
            app,state=self.make_app(mode);state['screen']='shop'
            original=app.tap
            def stop_after_input(x,y):original(x,y);app.loop_active=False
            app.tap=stop_after_input
            with patch('e7_shop_flow.time.sleep'):self.assertFalse(app.clickRefresh())
            self.assertEqual(state['refreshes'],0);self.assertEqual(len(state['events']),1)

    def test_foreground_ocr_does_not_combine_dimmed_inventory_with_dialog(self):
        rgb=base_image();rgb[450:480,1000:1100]=230;rgb[500:530,1000:1100]=55
        result=dict(words=[dict(text='Mystic',box=[1000,450,1100,480]),dict(text='Covenant',box=[1000,500,1100,530])])
        with patch('e7_mouse_confirmation.read_ui_text',return_value=result):
            self.assertEqual(read_confirmation_text(rgb),'mystic')

    def test_adb_viewport_change_or_unreadable_capture_sends_no_action(self):
        app,state=self.make_app('adb');app.takeScreenshot();app._adb_geometry=FrameGeometry((800,450),(0,0,800,450))
        with self.assertRaisesRegex(MouseStopped,'viewport changed'):app.takeScreenshot()
        self.assertEqual(state['events'],[])
        app._adb_runner=Mock(return_value=SimpleNamespace(stdout=b'invalid png'))
        with self.assertRaisesRegex(MouseStopped,'unreadable'):app.takeScreenshot()

    def test_normal_adb_and_mouse_share_every_screen_action(self):
        for name in ('clickShop','_confirm','_home_menu_target','_click_button'):
            self.assertIs(getattr(E7ADBShopRefresh,name),getattr(ObservedShopFlow,name))
            self.assertIs(getattr(E7MouseShopRefresh,name),getattr(ObservedShopFlow,name))

    def test_normalized_mapping_retains_crop_and_rejects_invalid_targets(self):
        image=Image.new('RGB',(1280,800));image.paste(Image.fromarray(shop_image()).resize((1280,720)),(0,40))
        _,geometry=normalize_game_frame(image)
        self.assertEqual(geometry.bounds,(0,40,1280,760));self.assertEqual(geometry.point(960,540),(640,400))
        for point in ((-1,0),(1920,10),(float('nan'),20)):
            with self.assertRaises(MouseStopped):geometry.point(*point)
        with self.assertRaises(MouseStopped):normalize_game_frame(Image.new('RGB',(500,300)))
        with self.assertRaises(MouseStopped):normalize_game_frame(Image.new('RGB',(1920,800),(50,60,70)))

if __name__=='__main__':unittest.main()
