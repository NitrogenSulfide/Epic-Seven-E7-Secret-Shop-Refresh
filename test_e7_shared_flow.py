"""Same action loop through fake ADB/Windows transports. Never access a game."""
import contextlib,io,itertools,json,random,unittest
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

ITEM_ROWS = (('Covenant bookmark','cov.png',184000,220),
             ('Mystic medal','mys.png',280000,470),
             ('Friendship points',None,18000,720))

def shop_image(with_items=False,names=None):
    rgb=base_image();nav=create_navigator('adb-assets').navigators[-1][1]
    for name in ('shop-title.png','refresh-label.png'):
        x,y,_,_=REFERENCE_BOXES[name];reference=nav.references[name]
        h,w=reference.shape;rgb[y:y+h,x:x+w]=reference[:,:,None]
    if with_items:
        for name,filename,_,y in ITEM_ROWS:
            if name not in (names if names is not None else ('Covenant bookmark','Mystic medal')):continue
            if filename is not None:
                icon=cv2.imread('adb-assets/'+filename);h,w=icon.shape[:2]
                rgb[y:y+h,800:800+w]=cv2.cvtColor(icon,cv2.COLOR_BGR2RGB)
            rgb[y+25:y+105,1570:1850]=(20,110,40)
    return rgb

def home_image(wallpaper,third='epic-pass'):
    rgb=wallpaper.copy()
    for name,y in (('sanctuary',296),('secret-shop',498),(third,598)):
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
    def make_app(self,mode,width=1920,wallpaper=None,items=False,height=None,buy_friendship=False,offered=None,home_control='epic-pass'):
        app=(E7ADBShopRefresh if mode=='adb' else E7MouseShopRefresh).__new__(E7ADBShopRefresh if mode=='adb' else E7MouseShopRefresh)
        app.loop_active=True;app.end_of_refresh=False;app.debug=False;app.budget=6
        app.tap_sleep=.3;app.random_offset=True;app.tap_jitter=.1
        app.x_offset,app.y_offset=75,25;app.screenwidth,app.screenheight=1920,1080
        app.refresh_count=0;app._rgb=None;app._item=app._item_name=None;app._scan_page=1
        app._adb_geometry=None;app._capture_resumed=False
        app.adb_path='NEVER-RUN-ADB';app.device_args=['-s','fake-device']
        app.navigation=create_navigator('adb-assets');app.read_navigation_text=Mock(return_value=dict(text='',words=[]))
        app.storage=E7Inventory()
        for name,filename,price,_ in ITEM_ROWS:
            if name=='Friendship points' and not buy_friendship:continue
            app.storage.inventory[name]=E7Item(cv2.imread('adb-assets/'+filename,cv2.IMREAD_GRAYSCALE) if filename else None,price)
        app.storage.writeToCSV=Mock();app._save_home_failure=Mock(return_value=False);app._save_confirmation_failure=Mock(return_value=False)
        wallpaper=base_image() if wallpaper is None else wallpaper
        state=dict(screen='hidden',bought=set(),refreshes=0,events=[],pending=None,page=1)
        def image():
            screen=state['screen']
            names=offered[state['page']-1] if offered is not None else None
            rgb=wallpaper if screen=='hidden' else home_image(wallpaper,home_control) if screen=='home' else shop_image(items,names) if screen=='shop' else dialog_image(screen)
            if screen=='shop' and items:
                for name,_,_,y in ITEM_ROWS:
                    if name in state['bought'] and not state.get('keep_purchased_controls'):
                        rgb[y:y+115,780:1030]=30;rgb[y+25:y+105,1570:1850]=30
            return Image.fromarray(rgb).resize((width,height or round(width*9/16)),Image.Resampling.LANCZOS)
        def click(x,y):
            screen=state['screen'];state['events'].append((screen,x,y))
            if screen=='hidden':state['screen']='home'
            elif screen=='home':state['screen']='shop'
            elif screen=='shop':
                state['pending']=app._item_name if x>1400 else None
                state['screen']='buy' if state['pending'] else 'refresh'
            elif screen=='buy':state['bought'].add(state['pending']);state['screen']='shop'
            elif screen=='refresh':state['refreshes']+=1;state['bought'].clear();state['screen']='shop';state['page']=1
        def text(_):
            if state['screen']=='refresh':return 'Use Skystone to refresh? Cancel Confirm'
            name=state['pending'];price=next(price for item,_,price,_ in ITEM_ROWS if item==name)
            return f'Cancel Buy {name if name=="Friendship points" else name+"s"} {price:,}'
        def shop_ocr():
            names=offered[state['page']-1] if offered is not None else ()
            if state['screen']!='shop' or 'Friendship points' not in names or 'Friendship points' in state['bought']:
                return dict(words=[])
            return dict(words=[dict(text=text,box=box) for text,box in (
                ('Currency',[1035,660,1135,685]),('Friendship',[1035,710,1180,742]),
                ('Points',[1190,710,1320,742]),('18,000',[1684,673,1786,704]),
                ('Buy',[1711,755,1757,787]))])
        app._fake_shop_ocr=shop_ocr
        def scroll():
            state['events'].append(('drag',));state['page']=2
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
                elif 'swipe' in command:scroll()
                else:self.fail('Unexpected device operation')
                return SimpleNamespace(returncode=0)
            app._adb_runner=Mock(side_effect=runner)
        else:
            app.mouse=Mock();app.mouse.pause_revision=0;app.mouse.screenshot.side_effect=image
            app.mouse.native_stove=mode=='mouse-stove'
            app.mouse.click.side_effect=click;app.mouse.drag.side_effect=lambda *_args,**_kwargs:scroll()
        return app,state

    def test_event_home_opens_observed_shop_in_adb_google_and_stove_without_refresh(self):
        for mode,width,height in (('adb',1920,1080),('mouse',1280,720),('mouse-stove',3840,2019)):
            with self.subTest(mode=mode):
                app,state=self.make_app(mode,width,height=height,home_control='event')
                state['screen']='home'
                with patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
                    self.assertTrue(app.clickShop())
                self.assertEqual(state['screen'],'shop');self.assertEqual(state['refreshes'],0)
                self.assertEqual(len(state['events']),1)
                _,x,y=state['events'][0];self.assertLess(abs(x-84)+abs(y-498),8)
                app.read_navigation_text.assert_not_called()
                app._save_home_failure.assert_not_called()

    def test_native_maximized_hidden_home_purchases_and_repeated_refreshes(self):
        for width,height in ((1920,1010),(3840,2019),(1920,1035)):
            with self.subTest(size=(width,height)):
                wallpaper=np.random.default_rng(width+height).integers(10,65,(1080,1920,3),dtype=np.uint8)
                app,state=self.make_app('mouse-stove',width,wallpaper,items=True,height=height)
                with patch('e7_shop_flow.hidden_home_matches',return_value=False),patch('e7_shop_flow.read_ui_text',return_value=dict(text='',words=[])),patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
                    app.refreshShop()
                self.assertEqual(state['refreshes'],2)
                self.assertEqual([item.count for item in app.storage.inventory.values()],[3,3])
                self.assertEqual([event[0] for event in state['events'][:2]],['hidden','home'])
                app._save_confirmation_failure.assert_not_called()

    def test_native_layout_exception_still_rejects_unsupported_shapes(self):
        for size in ((500,300),(1920,800),(1080,1920)):
            with self.subTest(size=size),self.assertRaises(MouseStopped):
                normalize_game_frame(Image.new('RGB',size),native_stove=True)
        for enabled in (False,None):
            with self.subTest(native_stove=enabled),self.assertRaises(MouseStopped):
                normalize_game_frame(Image.new('RGB',(1920,1010)),native_stove=enabled)

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

    def test_new_session_skips_previously_purchased_friendship_and_continues_across_clients(self):
        offered=(('Friendship points',),('Friendship points',))
        for mode,width,height in (('adb',1920,1080),('mouse-google',1280,720),('mouse-stove',3840,2019)):
            with self.subTest(mode=mode):
                app,state=self.make_app(mode,width,items=True,height=height,buy_friendship=True,offered=offered)
                state['screen']='shop';state['bought'].add('Friendship points')
                original=app._fake_shop_ocr
                def ocr(*unused,**kwargs):
                    if state['screen']=='shop' and 'Friendship points' in state['bought']:
                        return dict(words=[dict(text=text,box=box) for text,box in (
                            ('Currency',[1035,660,1135,685]),('Friendship',[1035,710,1180,742]),
                            ('Points',[1190,710,1320,742]),('Purchased',[1590,755,1790,787]))])
                    return original()
                with patch('e7_shop_flow.read_ui_text',side_effect=ocr),patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
                    app.refreshShop()
                self.assertEqual(state['refreshes'],2)
                self.assertEqual(app.storage.inventory['Friendship points'].count,2)
                self.assertEqual(sum(event[0]=='buy' for event in state['events']),2)
                app._save_confirmation_failure.assert_not_called()

    def test_friendship_and_every_mixed_inventory_are_bought_once_per_refresh(self):
        names=[row[0] for row in ITEM_ROWS]
        combinations=[group for size in range(1,4) for group in itertools.combinations(names,size)]
        for mode in ('adb','mouse'):
            for group in combinations:
                # Also exercise first-page-only, lower-page-only, and overlap.
                for offered in ((group,group),((),group),(group,())):
                    with self.subTest(mode=mode,offered=offered):
                        app,state=self.make_app(mode,items=True,buy_friendship=True,offered=offered)
                        state['screen']='shop'
                        output=io.StringIO()
                        # Generated icons are exactly 1:1. Other shared tests
                        # exercise real rescaling; this matrix checks combinations.
                        with patch('e7_shop_flow.np.linspace',return_value=np.array([1.])),patch('e7_shop_flow.read_ui_text',side_effect=lambda *_,**kwargs:app._fake_shop_ocr()),patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(output):
                            app.refreshShop()
                        self.assertEqual(state['refreshes'],2)
                        self.assertEqual([item.count for item in app.storage.inventory.values()],
                                         [3 if name in group else 0 for name in names])
                        self.assertEqual(sum(event[0]=='buy' for event in state['events']),3*len(group))
                        self.assertEqual(app.storage.getTotalCost(),3*sum(price for name,_,price,_ in ITEM_ROWS if name in group))
                        stats=[json.loads(line[12:]) for line in output.getvalue().splitlines() if line.startswith('E7GUI_STATS ')]
                        self.assertEqual(stats[-1]['friendship'],3 if names[2] in group else 0)
                        app._save_confirmation_failure.assert_not_called()

    def test_mixed_available_rows_and_purchased_updates_in_ocr_fallback_with_friendship_on_or_off(self):
        names=tuple(row[0] for row in ITEM_ROWS)
        for enabled in (False,True):
            for mode in ('adb','mouse-google','mouse-stove'):
                with self.subTest(enabled=enabled,mode=mode):
                    app,state=self.make_app(mode,items=True,buy_friendship=enabled,offered=(names,names))
                    app.budget=3;state['screen']='shop'
                    for item in app.storage.inventory.values():
                        if item.image is not None:
                            # Deliberately too large at every matching scale:
                            # exercise the shared OCR fallback for Covenant and
                            # Mystic rather than the icon fast path.
                            item.image=np.zeros((1600,600),dtype=np.uint8)
                    def ocr(*unused,**kwargs):
                        words=[]
                        for name,filename,price,y in ITEM_ROWS:
                            prefix,noun=name.lower().split(' ',1)
                            words.extend(dict(text=text,box=box) for text,box in (
                                ('currency' if filename is None else 'summon',[1035,y-60,1135,y-35]),
                                (prefix,[1035,y-10,1180,y+22]),(noun,[1190,y-10,1335,y+22])))
                            if name in state['bought']:
                                words.append(dict(text='Purchased',box=[1590,y+35,1790,y+67]))
                            else:
                                words.extend(dict(text=text,box=box) for text,box in (
                                    (f'{price:,}',[1684,y-47,1786,y-16]),('Buy',[1711,y+35,1757,y+67])))
                        return dict(words=words)
                    with patch('e7_shop_flow.read_ui_text',side_effect=ocr),patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
                        app.refreshShop()
                    expected=[2,2]+([2] if enabled else [])
                    self.assertEqual([item.count for item in app.storage.inventory.values()],expected)
                    self.assertEqual(state['refreshes'],1)
                    self.assertEqual(sum(event[0]=='buy' for event in state['events']),sum(expected))
                    self.assertEqual(app.storage.getTotalCost(),2*(184000+280000+(18000 if enabled else 0)))
                    app._save_confirmation_failure.assert_not_called()

    def test_prebought_zero_stock_keeps_icon_and_buy_but_available_currencies_are_bought(self):
        names=tuple(row[0] for row in ITEM_ROWS)
        for mode in ('adb','mouse-google','mouse-stove'):
            for prebought in names:
                with self.subTest(mode=mode,prebought=prebought):
                    app,state=self.make_app(mode,items=True,buy_friendship=True,offered=(names,names))
                    app.budget=3;state['screen']='shop';state['bought'].add(prebought);state['keep_purchased_controls']=True
                    def ocr(*unused,**kwargs):
                        words=[]
                        for name,filename,price,y in ITEM_ROWS:
                            prefix,noun=name.lower().split(' ',1)
                            words.extend(dict(text=text,box=box) for text,box in (
                                ('currency' if filename is None else 'summon',[1035,y-60,1135,y-35]),
                                (prefix,[1035,y-10,1180,y+22]),(noun,[1190,y-10,1335,y+22]),
                                (f'{price:,}',[1684,y-47,1786,y-16]),('Buy',[1711,y+35,1757,y+67]),
                                ('0/1' if name in state['bought'] else '1/1',[1580,y+35,1628,y+67]),
                                ('Only',[1035,y+40,1085,y+70]),('1',[1094,y+40,1103,y+70]),('available',[1114,y+40,1220,y+70])))
                        return dict(words=words)
                    with patch('e7_shop_flow.read_ui_text',side_effect=ocr),patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
                        app.refreshShop()
                    expected=[1 if name==prebought else 2 for name in names]
                    self.assertEqual([item.count for item in app.storage.inventory.values()],expected)
                    self.assertEqual(state['refreshes'],1)
                    self.assertEqual(sum(event[0]=='buy' for event in state['events']),sum(expected))
                    self.assertEqual(app.storage.getTotalCost(),sum(price*count for (_,_,price,_),count in zip(ITEM_ROWS,expected)))

    def test_friendship_is_ignored_when_not_selected_even_in_mixed_lists(self):
        names=tuple(row[0] for row in ITEM_ROWS)
        for mode in ('adb','mouse'):
            app,state=self.make_app(mode,items=True,offered=(names,names));state['screen']='shop'
            with patch('e7_shop_flow.read_ui_text',return_value=dict(text='',words=[])),patch('e7_shop_flow.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
                app.refreshShop()
            self.assertEqual([item.count for item in app.storage.inventory.values()],[3,3])
            self.assertEqual(sum(event[0]=='buy' for event in state['events']),6)

    def test_friendship_confirmation_requires_name_price_and_no_conflicting_item(self):
        self.assertTrue(confirmation_matches('Cancel Buy Friendship Points 18,000','buy','Friendship points'))
        for text in ('Cancel Buy Friendship Equipment 18,000','Cancel Buy Friendship Points 180,000',
                     'Cancel Buy Friendship Bookmarks 18,000',
                     'Cancel Buy Covenant Bookmarks 18,000','Not enough Gold Cancel Buy Friendship Points 18,000',
                     'Cancel Buy Friendship Points 18,000 Mystic Medals','Cancel Buy Friendship Points 18,000 184,000'):
            self.assertFalse(confirmation_matches(text,'buy','Friendship points'),text)
        for item in ('Covenant bookmark','Mystic medal'):
            self.assertFalse(confirmation_matches(f'Cancel Buy {item}s 184,000 Friendship Bookmarks','buy',item))
        self.assertFalse(confirmation_matches('Cancel Confirm Use Skystone to refresh? Friendship','refresh'))

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
