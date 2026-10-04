"""Fake desktop/saved-frame checks. No live screenshot, input or ADB."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import threading
import unittest
from unittest.mock import Mock
from PIL import Image, ImageDraw
import cv2
import numpy as np
from e7_window_preview import GameWindow, capture_selected, analyze_capture, game_view, wait_for_window, annotated_capture
from e7_mouse_analysis import inspect_mouse_frame
import test_e7_shop_navigation as navigation_tests


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.target = GameWindow(123,456,'Epic Seven',(-1920,100,0,1180))
        self.backend = Mock(); self.backend.inspect.return_value=self.target
        self.backend.unobstructed.return_value=True
        self.image=Image.new('RGB',(1920,1080)); ImageDraw.Draw(self.image).rectangle((50,50,250,250),fill='white')
        self.grabber=Mock(return_value=self.image)
        self.destination=self.root/'capture.png'

    def tearDown(self): self.temp.cleanup()

    def test_source_adb_import_still_supports_missing_optional_pillow(self):
        result = subprocess.run([sys.executable,'-c',
            "import sys; sys.modules['PIL']=None; import e7_shop_refresh_gui; from e7_window_preview import Image; assert Image is None"],
            cwd=Path(__file__).resolve().parent,capture_output=True,text=True,timeout=15,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr)

    def test_capture_only_selected_client_with_negative_monitor_coordinates(self):
        capture_selected(self.target,self.destination,backend=self.backend,grabber=self.grabber)
        self.grabber.assert_called_once_with(bbox=self.target.rectangle,all_screens=True)
        self.assertTrue(self.destination.exists())
        self.assertEqual(self.backend.unobstructed.call_count,2)

    def test_wait_until_user_game_is_ready_without_input(self):
        self.backend.unobstructed.side_effect=[False,False,True]
        cancel=Mock();cancel.is_set.return_value=False
        self.assertEqual(wait_for_window(self.target,cancel,backend=self.backend),self.target)
        self.assertEqual(cancel.wait.call_count,2)
        self.grabber.assert_not_called()

    def test_wait_timeout_cancel_and_changed_window_do_not_capture(self):
        cancel=threading.Event();cancel.set()
        with self.assertRaisesRegex(ValueError,'cancelled'):
            wait_for_window(self.target,cancel,backend=self.backend)
        self.backend.inspect.assert_not_called()
        cancel.clear();self.backend.unobstructed.return_value=False
        with self.assertRaisesRegex(ValueError,'20 seconds'):
            wait_for_window(self.target,cancel,backend=self.backend,now=Mock(side_effect=[0,21]))
        self.backend.inspect.return_value=GameWindow(123,999,'Epic Seven',self.target.rectangle)
        with self.assertRaisesRegex(ValueError,'window changed'):
            wait_for_window(self.target,cancel,backend=self.backend)
        self.grabber.assert_not_called()

    def test_cancel_during_image_grab_saves_nothing(self):
        cancel=threading.Event()
        def grab(**kwargs):
            cancel.set();return self.image
        with self.assertRaisesRegex(ValueError,'cancelled'):
            capture_selected(self.target,self.destination,backend=self.backend,grabber=grab,cancel=cancel)
        self.assertFalse(self.destination.exists())

    def test_stove_maximized_letterbox_uses_game_view_and_screen_offset(self):
        game=Image.new('RGB',(3590,2019),(40,60,80))
        ImageDraw.Draw(game).rectangle((50,50,250,250),fill='white')
        window=Image.new('RGB',(3840,2019));window.paste(game,(125,0))
        target=GameWindow(123,456,'Epic Seven',(-3840,45,0,2064))
        self.backend.inspect.return_value=target
        actual=capture_selected(target,self.destination,backend=self.backend,grabber=Mock(return_value=window))
        self.assertEqual(actual.rectangle,(-3715,45,-125,2064))
        with Image.open(self.destination) as saved:
            self.assertEqual(saved.size,game.size)
            self.assertEqual(saved.getpixel((100,100)),(255,255,255))

    def test_top_bottom_bars_crop_but_other_shapes_preserve_full_view(self):
        game=Image.new('RGB',(1280,720),(40,60,80))
        letterbox=Image.new('RGB',(1280,800));letterbox.paste(game,(0,40))
        result,bounds=game_view(letterbox)
        self.assertEqual(bounds,(0,40,1280,760));self.assertEqual(result.size,game.size)
        for mode in ('chrome','asymmetric','wrong_ratio'):
            image=Image.new('RGB',(1280,800))
            image.paste(game,(0,0 if mode=='asymmetric' else 40))
            if mode=='chrome':ImageDraw.Draw(image).rectangle((0,0,1279,30),fill='gray')
            if mode=='wrong_ratio':image=Image.new('RGB',(1600,1000),'gray')
            view,bounds=game_view(image)
            self.assertEqual(view.size,image.size)
            self.assertEqual(bounds,(0,0,*image.size))

    def test_native_wide_client_is_saved_and_annotations_preserve_aspect(self):
        image=Image.new('RGB',(3840,2019),(40,60,80))
        ImageDraw.Draw(image).rectangle((50,50,250,250),fill='white')
        target=GameWindow(123,456,'Epic Seven',(0,45,3840,2064))
        self.backend.inspect.return_value=target
        actual=capture_selected(target,self.destination,backend=self.backend,grabber=Mock(return_value=image))
        self.assertEqual(actual.rectangle,target.rectangle)
        with Image.open(self.destination) as saved:self.assertEqual(saved.size,image.size)
        self.assertTrue((self.root/'client-capture.png').is_file())
        rendered=annotated_capture(self.destination,dict(targets=[dict(point=[960,540])],detections=[]))
        self.assertAlmostEqual(rendered.width/rendered.height,image.width/image.height,places=2)
        self.assertEqual(rendered.getpixel((rendered.width//2,rendered.height//2)),(251,191,36))

    def test_changed_identity_closed_minimized_or_obstructed_never_capture(self):
        for mode in ('identity','closed','obstructed'):
            backend=Mock(); backend.inspect.return_value=self.target; backend.unobstructed.return_value=True
            if mode=='identity':backend.inspect.return_value=GameWindow(123,999,'Epic Seven',self.target.rectangle)
            if mode=='closed':backend.inspect.side_effect=ValueError('Closed')
            if mode=='obstructed':backend.unobstructed.return_value=False
            with self.assertRaises(ValueError):capture_selected(self.target,self.destination,backend=backend,grabber=self.grabber)
            self.grabber.assert_not_called();self.assertFalse(self.destination.exists())

    def test_focus_or_geometry_change_during_capture_saves_nothing(self):
        for moved in (False,True):
            backend=Mock();backend.inspect.return_value=self.target;backend.unobstructed.side_effect=[True,False]
            if moved:
                backend.inspect.side_effect=[self.target,GameWindow(123,456,'Epic Seven',(0,0,1920,1080))]
            with self.assertRaises(ValueError):capture_selected(self.target,self.destination,backend=backend,grabber=self.grabber)
            self.assertFalse(self.destination.exists())

    def test_bad_aspect_capture_dimensions_or_blank_frame_rejected(self):
        for fault in ('aspect','size','blank'):
            backend=Mock();backend.inspect.return_value=self.target;backend.unobstructed.return_value=True
            grabber=Mock(return_value=self.image)
            if fault=='aspect':backend.inspect.return_value=GameWindow(123,456,'Epic Seven',(0,0,1600,1000))
            if fault=='size':grabber.return_value=self.image.resize((960,540))
            if fault=='blank':grabber.return_value=Image.new('RGB',(1920,1080))
            with self.assertRaises(ValueError):capture_selected(self.target,self.destination,backend=backend,grabber=grabber)
            self.assertFalse(self.destination.exists())

    def test_analysis_uses_only_offline_engine_mode_and_matching_receipt(self):
        engine=self.root/'engine.exe';engine.write_bytes(b'fake executable')
        engine.with_suffix('.sha256').write_text(hashlib.sha256(engine.read_bytes()).hexdigest())
        report=self.root/'preview.json';report.write_text(json.dumps(dict(read_only=True,state='unrecognized',targets=[],detections=[])))
        runner=Mock(return_value=subprocess.CompletedProcess([],0,'',''))
        analyze_capture(engine,self.root,self.destination,report,runner=runner)
        self.assertEqual(runner.call_args.args[0],[str(engine),'--preview-mouse-frame',str(self.destination),'--output',str(report)])
        engine.write_bytes(b'changed')
        with self.assertRaises(ValueError):analyze_capture(engine,self.root,self.destination,report,runner=runner)
        self.assertEqual(runner.call_count,1)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.fixture=navigation_tests.NavigationTests();self.fixture.setUp()
        self.root=self.fixture.directory
        self.assets=self.root/'assets';self.assets.mkdir()
        (self.assets/'gui-navigation').mkdir()
        for file in self.root.glob('*.png'):
            (self.assets/'gui-navigation'/file.name).write_bytes(file.read_bytes())
        # Fixture root is the navigator's actual reference directory.
        for name,data in self.fixture.nav.references.items():
            cv2.imwrite(str(self.assets/'gui-navigation'/name),data)
        project=Path(__file__).resolve().parent
        for name in ('cov.png','mys.png'):
            (self.assets/name).write_bytes((project/'adb-assets'/name).read_bytes())
        self.path=self.root/'frame.png'

    def tearDown(self):self.fixture.tearDown()

    def inspect(self,frame):
        cv2.imwrite(str(self.path),frame)
        return inspect_mouse_frame(self.path,self.assets)

    def test_home_shop_and_unrecognized_only_offer_verified_targets(self):
        for markers,state,labels in ((['menu-secret-shop.png'],'home',['Secret Shop menu']),
                    (['shop-title.png','refresh-label.png'],'shop',['Refresh button']),([], 'unrecognized', [])):
            report=self.inspect(self.fixture.frame(markers))
            self.assertTrue(report['read_only']);self.assertEqual(report['state'],state)
            self.assertEqual([t['label'] for t in report['targets']],labels)
            self.assertEqual(report['detections'],[])

    def test_item_detections_only_inside_verified_shop(self):
        icon=cv2.imread(str(self.assets/'cov.png'),cv2.IMREAD_GRAYSCALE)
        for shop in (False,True):
            frame=self.fixture.frame(['shop-title.png','refresh-label.png'] if shop else [])
            frame[200:200+icon.shape[0],810:810+icon.shape[1]]=icon
            report=self.inspect(frame)
            self.assertEqual([d['label'] for d in report['detections']],['Covenant Bookmark'] if shop else [])

    def test_normalized_resolution_and_too_small_image(self):
        frame=cv2.resize(self.fixture.frame(['menu-secret-shop.png']),(2560,1440))
        report=self.inspect(frame);self.assertEqual(report['original_size'],[2560,1440])
        self.assertEqual(report['state'],'home')
        with self.assertRaises(ValueError):self.inspect(np.zeros((300,600),dtype=np.uint8))

    def test_native_wide_frames_recognize_visible_labels_or_return_unknown(self):
        for markers,state in ((['shop-title.png','refresh-label.png'],'shop'),([], 'unrecognized')):
            frame=cv2.resize(self.fixture.frame(markers),(3840,2019))
            report=self.inspect(frame)
            self.assertEqual(report['state'],state)
            self.assertEqual(report['original_size'],[3840,2019])

    def test_shop_recognition_after_letterbox_crop(self):
        frame=self.fixture.frame(['shop-title.png','refresh-label.png'])
        # The navigation fixture has black empty space; give its outer edge
        # non-black game content so only the added bars can be identified.
        frame[0,:]=frame[-1,:]=20
        frame[:,0]=frame[:,-1]=20
        image=Image.fromarray(frame).convert('RGB')
        padded=Image.new('RGB',(2048,1080));padded.paste(image,(64,0))
        view,bounds=game_view(padded)
        self.assertEqual(bounds,(64,0,1984,1080))
        report=self.inspect(np.array(view.convert('L')))
        self.assertEqual(report['state'],'shop')
        self.assertEqual([t['label'] for t in report['targets']],['Refresh button'])


if __name__=='__main__':unittest.main()
