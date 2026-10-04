"""Fake desktop/saved-frame checks. No live screenshot, input or ADB."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from PIL import Image, ImageDraw
import cv2
import numpy as np
from e7_window_preview import GameWindow, capture_selected, analyze_capture
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

    def test_capture_only_selected_client_with_negative_monitor_coordinates(self):
        capture_selected(self.target,self.destination,backend=self.backend,grabber=self.grabber)
        self.grabber.assert_called_once_with(bbox=self.target.rectangle,all_screens=True)
        self.assertTrue(self.destination.exists())
        self.assertEqual(self.backend.unobstructed.call_count,2)

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

    def test_normalized_resolution_and_invalid_aspect(self):
        frame=cv2.resize(self.fixture.frame(['menu-secret-shop.png']),(2560,1440))
        report=self.inspect(frame);self.assertEqual(report['original_size'],[2560,1440])
        self.assertEqual(report['state'],'home')
        with self.assertRaises(ValueError):self.inspect(np.zeros((1000,1600),dtype=np.uint8))


if __name__=='__main__':unittest.main()
