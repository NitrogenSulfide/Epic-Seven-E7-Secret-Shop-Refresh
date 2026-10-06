import subprocess
import os
import sys
from io import BytesIO
import time
import csv

from PIL import Image
import threading
import cv2
import numpy as np
import keyboard
import random
import configparser
import json
import math
from e7_shop_navigation import create_navigator, NavigationSetupRequired, prepare_references
from e7_shop_flow import ObservedShopFlow
from e7_mouse_confirmation import read_confirmation_text,read_ui_text
from e7_native_mouse import MouseStopped
from e7_frame import normalize_game_frame
from e7_timing import validate_timing, sample_tap_delay
from e7_history import append_session, new_session_metadata
from e7_session_control import listen_for_stop
from e7_input_trace import InputTrace

class E7Item:
    def __init__(self, image=None, price=0, count=0):
        self.image=image
        self.price=price
        self.count=count

    def __repr__(self):
        return f'ShopItem(image={self.image}, price={self.price}, count={self.count})'

class E7Inventory:
    def __init__(self):
        self.inventory = dict()

    def addItem(self, path:str, name='', price=0, count=0):
        image = cv2.imread(os.path.join('adb-assets', path))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # cv2.imshow('test', image)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()
        newItem = E7Item(image, price, count)
        self.inventory[name] = newItem

    def getStatusString(self):
        status_string = ''
        for key, value in self.inventory.items():
            status_string += key[0:4] + ': ' + str(value.count) + ' '
        return status_string

    def getName(self):
        res = []
        for key in self.inventory.keys():
            res.append(key)
        return res
    
    def getCount(self):
        res = []
        for value in self.inventory.values():
            res.append(value.count)
        return res
    
    def getTotalCost(self):
        sum = 0
        for value in self.inventory.values():
            sum += value.price * value.count
        return sum

    def writeToCSV(self, duration, skystone_spent, session=None):
        record = dict(session or {})
        record.update({'Duration': round(duration, 2), 'Skystone spent': skystone_spent,
                       'Gold spent': self.getTotalCost()})
        record.update({name: item.count for name, item in self.inventory.items()})
        append_session(os.path.join('ShopRefreshHistory', 'ADB_History.csv'), record)

class E7ADBShopRefresh(ObservedShopFlow):
    def __init__(self, tap_sleep:float = 0.3, budget=None, ip_port=None, stop_refresh_key='esc', random_offset = False, debug=False, tap_jitter=None, adb_runner=None, trace_input=False):
        if budget is not None:
            if isinstance(budget, bool) or not math.isfinite(float(budget)) or int(budget) != float(budget) or int(budget) < 3:
                raise ValueError('Skystone budget must be a whole number of at least 3.')
            budget = int(budget)
        tap_sleep, tap_jitter = validate_timing(tap_sleep, tap_jitter)
        if type(trace_input) is not bool:
            raise ValueError('Input tracing must be on or off.')
        self.input_trace = InputTrace(trace_input)
        if hasattr(self, 'mouse'):
            self.mouse.input_trace = self.input_trace
        self._stop_requested = threading.Event()
        self._stop_reason = ''
        self._session_recorded = False
        self._session_metadata = new_session_metadata('ADB', debug)
        self._session_clock = time.monotonic()
        self.loop_active = False
        self.end_of_refresh = True
        self.tap_sleep = tap_sleep
        self.tap_jitter = tap_jitter
        self.budget = budget
        self.ip_port = ip_port
        self.stop_refresh_key = stop_refresh_key

        #random offset
        self.random_offset = random_offset
        self.x_offset = 75 if random_offset else 0
        self.y_offset = 25 if random_offset else 0

        self.debug = debug
        self.device_args = [] if ip_port is None else ['-s', ip_port]
        self.refresh_count = 0
        self.keyboard_thread = threading.Thread(target=self.checkKeyPress)
        self.adb_path = os.path.join('adb-assets','platform-tools', 'adb')
        self._adb_runner=adb_runner or subprocess.run
        self.storage = E7Inventory()
        self.screenwidth = 1920
        self.screenheight = 1080
        self._rgb = None
        self._item = self._item_name = None
        self._adb_geometry = None
        self.read_confirmation_text = read_confirmation_text
        self.read_navigation_text = lambda rgb:read_ui_text(rgb,(0,180,420,920))
        self.checkScreenDimension()
        self.navigation = create_navigator('adb-assets')

        self.storage.addItem('cov.png', 'Covenant bookmark', 184000)
        self.storage.addItem('mys.png', 'Mystic medal', 280000)

    def start(self):
        if not hasattr(self, '_stop_requested'):
            self._stop_requested = threading.Event()
        if not hasattr(self, '_stop_reason'):
            self._stop_reason = ''
        if self._stop_requested.is_set():
            self.record_session('stopped', self._stop_reason)
            return
        self.loop_active = True
        self.end_of_refresh = False
        self._session_clock = time.monotonic()
        self.keyboard_thread.start()
        try:
            self.refreshShop()
        except Exception as error:
            self.record_session('stopped' if self._stop_requested.is_set() else 'failed',
                                self._stop_reason or str(error))
            raise
        finally:
            self.end_of_refresh = True
            self.loop_active = False
            self.keyboard_thread.join(timeout=1)
            self.record_session('stopped', self._stop_reason or 'Stopped before refreshing.')

    def request_stop(self, reason='Stopped by user.'):
        self._stop_reason = reason
        self._stop_requested.set()
        self.loop_active = False

    def wait(self, seconds):
        """Interrupt pacing immediately; fake legacy transports retain their sleep stub."""
        event = getattr(self, '_stop_requested', None)
        if event is None:
            time.sleep(seconds)
        else:
            event.wait(seconds)

    def record_session(self, outcome, reason='', duration=None):
        if getattr(self, '_session_recorded', False):
            return
        trace = getattr(self, 'input_trace', None)
        if trace is not None and trace.enabled:
            trace.finish(sum(item.count for item in self.storage.inventory.values()),
                         'final scan' if outcome == 'completed' else 'interrupted')
        metadata = dict(getattr(self, '_session_metadata', {}))
        if not metadata:
            metadata = new_session_metadata('Mouse' if hasattr(self, 'mouse') else 'ADB', self.debug)
        metadata.update({'Outcome': outcome, 'Reason': reason})
        if duration is None:
            duration = max(0, time.monotonic() - getattr(self, '_session_clock', time.monotonic()))
        self.storage.writeToCSV(duration=duration, skystone_spent=self.refresh_count * 3, session=metadata)
        self._session_recorded = True

    #threads
    def checkKeyPress(self):
        while(self.loop_active and not self.end_of_refresh):
            if keyboard.is_pressed(self.stop_refresh_key):
                if hasattr(self, '_stop_requested'):
                    self.request_stop('Stop key pressed.')
                else:
                    self.loop_active = False
                print('Shop refresh terminated!', flush=True)
                return
            # Yield the GIL/CPU so keyboard hooks and foreground typing can run.
            time.sleep(0.02)

    def reportLiveStats(self):
        counts = {name: item.count for name, item in self.storage.inventory.items()}
        print('E7GUI_STATS ' + json.dumps({
            'refreshes': self.refresh_count,
            'skystone_spent': self.refresh_count * 3,
            'covenant': counts.get('Covenant bookmark', 0),
            'mystic': counts.get('Mystic medal', 0),
            'friendship': 0,  # Reserved legacy protocol field; no Friendship purchases.
        }), flush=True)

    def refreshShop(self):
        if not self.clickShop():
            return
        self.reportLiveStats()
        trace = getattr(self, 'input_trace', None)
        if trace is not None and trace.enabled:
            trace.begin(sum(item.count for item in self.storage.inventory.values()))
        #time needed for item to drop in after refresh (0.5 second loading + drop 1 second)
        sliding_time = 1.5
        #stat track
        start_time = time.time()
        milestone = self.budget//10
        #swipe location
        x1 = 0.6250 * self.screenwidth
        y1 = 0.7481 * self.screenheight
        y2 = 0.3629 * self.screenheight
        #refresh loop
        while self.loop_active:

            self._wait_observed(sliding_time, 'inventory settle')
            brought = set()

            if not self.loop_active: break
            #look at shop (page 1)
            self._scan_page = 1
            screenshot = self.takeScreenshot()
            self.navigation.require_shop(screenshot)
            #print(len(self.storage.inventory.items()))
            for key, value in self.storage.inventory.items():
                pos = self.findItemPosition(screenshot, value.image)
                if pos is not None:
                    if self.clickBuy(pos):
                        value.count += 1
                        brought.add(key)
                        self.reportLiveStats()

            if not self.loop_active: break
            
            #swipe
            #debug
            if self.debug:
                self.showOffsetArea(x1, y1, "Please check if red rectangle is in a scrollable area", "start scroll area")    

            xoff, yoff = self.generateSwipeOffset()
            self.swipe(x1+xoff,y1+yoff,x1+xoff,y2+yoff)
            #wait for action to complete
            self._wait_observed(1, 'scroll settle')

            if not self.loop_active: break
            #look at shop (page 2)
            self._scan_page = 2
            screenshot = self.takeScreenshot()
            self.navigation.require_shop(screenshot)
            for key, value in self.storage.inventory.items():
                if key in brought:
                    continue
                pos = self.findItemPosition(screenshot, value.image)
                if pos is not None:
                    if self.clickBuy(pos):
                        value.count += 1
                        self.reportLiveStats()

            #print every 10% progress
            if self.budget >= 30 and self.refresh_count*3 >= milestone and not self.debug:
                sys.stdout.write(' ' * 80 + '\r')
                sys.stdout.write(f'{int(milestone/self.budget*100)}% {self.storage.getStatusString()}\r')
                sys.stdout.flush()
                milestone += self.budget//10
            
            if not self.loop_active: break
            if self.budget:
                if self.refresh_count >= self.budget//3:
                    break

            if self.clickRefresh():
                self.refresh_count += 1
                if trace is not None and trace.enabled:
                    trace.complete(sum(item.count for item in self.storage.inventory.values()))
                self.reportLiveStats()
        
        self.end_of_refresh = True
        self.loop_active = False
        self.reportLiveStats()
        completed = self.budget is not None and self.refresh_count >= self.budget // 3
        if completed: print('100%')
        duration = time.time()-start_time
        self.record_session('completed' if completed else 'stopped',
                            'Skystone budget reached.' if completed else getattr(self, '_stop_reason', '') or 'Session stopped.', duration)
        self.printResult()
    
    #helper function
    def printResult(self):
        print('\n---Result---')
        for key, value in self.storage.inventory.items():
            print(key, ':', value.count)
        print('Skystone spent:', self.refresh_count*3)

    def checkScreenDimension(self):
        self.takeScreenshot()
        if self.debug and self._adb_geometry.source_size!=(1920,1080):
            raise ValueError('ADB calibration requires a 1920 x 1080 Android display.')

    def takeScreenshot(self):
        result=getattr(self,'_adb_runner',subprocess.run)([self.adb_path]+self.device_args+['exec-out','screencap','-p'],
                              stdout=subprocess.PIPE,check=True,timeout=10)
        raw=cv2.imdecode(np.frombuffer(result.stdout,dtype=np.uint8),cv2.IMREAD_COLOR)
        if raw is None:
            raise MouseStopped('ADB returned an unreadable game capture. No input sent.')
        previous=getattr(self,'_adb_geometry',None)
        if previous is not None and previous.source_size!=(raw.shape[1],raw.shape[0]) and self.loop_active:
            raise MouseStopped('The Android game viewport changed. Restart at the chosen resolution.')
        if np.ptp(raw)<12:
            raise MouseStopped('ADB returned a blank game capture. No input sent.')
        rgb,geometry=normalize_game_frame(Image.fromarray(cv2.cvtColor(raw,cv2.COLOR_BGR2RGB)),
                                         bounds=previous.bounds if previous is not None and previous.source_size==(raw.shape[1],raw.shape[0]) else None)
        if previous is not None and previous!=geometry and self.loop_active:
            raise MouseStopped('The Android game viewport changed. Restart at the chosen resolution.')
        self._rgb,self._adb_geometry,self._capture_resumed=rgb,geometry,False
        return cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)

    def findItemPosition(self,frame,template):
        return self._calibration_findItemPosition(frame,template) if getattr(self,'debug',False) else super().findItemPosition(frame,template)

    def clickBuy(self,pos):
        return self._calibration_clickBuy(pos) if getattr(self,'debug',False) else super().clickBuy(pos)

    def clickRefresh(self):
        return self._calibration_clickRefresh() if getattr(self,'debug',False) else super().clickRefresh()

    def showOffsetArea(self, x, y, imshow_title = "Debug", text_desc = ''):

        #Grab a color image
        adb_process = subprocess.run([self.adb_path] + self.device_args + ['exec-out', 'screencap','-p'], stdout=subprocess.PIPE)
        img_array = np.frombuffer(adb_process.stdout, dtype=np.uint8)
        ims = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        cv2.rectangle(ims, (int(x-self.x_offset), int(y-self.y_offset)), (int(x+self.x_offset), int(y+self.y_offset)), (0, 0, 255), 2)
        
        # show text tip
        if text_desc:
            (text_width, text_height), baseline = cv2.getTextSize(text_desc, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
            text_x = int(x-self.x_offset + ((x+self.x_offset) - (x-self.x_offset) -  text_width)/2)
            text_y = int(y+self.y_offset + text_height + baseline)

            text_props = {
                'text': text_desc,
                'org': (text_x, text_y),
                'fontFace': cv2.FONT_HERSHEY_SIMPLEX,
                'fontScale': 1,
                'color': (0, 0, 255),
                'thickness': 2,
            }

            #border  
            text_border = {
                'text': text_desc,
                'org': (text_x, text_y),
                'fontFace': cv2.FONT_HERSHEY_SIMPLEX,
                'fontScale': 1,
                'color': (0, 0, 0),
                'thickness': 6,
            }
            ims = cv2.putText(ims, **text_border)
            ims = cv2.putText(ims, **text_props)
        
        ims = cv2.resize(ims, (960, 540))
        cv2.imshow(imshow_title + f' - press {self.stop_refresh_key} to stop debug', ims)
        print('check image - find it in taskbar')
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def generateSwipeOffset(self):
        return self.generateOffset()

    def generateTapDelay(self):
        """Vary only tap pacing; retain the configured baseline and fixed calibration."""
        return sample_tap_delay(self.tap_sleep, getattr(self, 'tap_jitter', None),
                                self.random_offset, self.debug, random.uniform)

    def generateOffset(self):
        if self.random_offset:
            generate_x_offset = random.randint(-self.x_offset, self.x_offset)
            generate_y_offset = random.randint(-self.y_offset, self.y_offset)
            return (generate_x_offset, generate_y_offset)
        return (0, 0)

    def _calibration_findItemPosition(self, screen_image, item_image):
        result = cv2.matchTemplate(screen_image, item_image, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= 0.75)
        
        #find location of item
        if loc[0].size > 0:
            x = loc[1][0] + self.screenwidth * 0.4718
            y = loc[0][0] + self.screenheight * 0.1000
            pos = (x, y)
            return pos
        return None

    #macro
    def _device_point(self,x,y):
        geometry=getattr(self,'_adb_geometry',None)
        if geometry is None:
            raise MouseStopped('Capture the Android game before input.')
        return geometry.point(x,y)

    def tap(self,x,y):
        if not self.loop_active:return
        x,y=self._device_point(x,y)
        getattr(self,'_adb_runner',subprocess.run)([self.adb_path]+self.device_args+['shell','input','tap',str(x),str(y)],check=True,timeout=10)
        return (x, y)

    def swipe(self,x1,y1,x2,y2):
        if not self.loop_active:return
        x1,y1=self._device_point(x1,y1);x2,y2=self._device_point(x2,y2)
        duration=random.uniform(.28,.36) if self.random_offset else .32
        getattr(self,'_adb_runner',subprocess.run)([self.adb_path]+self.device_args+['shell','input','swipe',str(x1),str(y1),str(x2),str(y2),str(round(duration*1000))],check=True,timeout=10)

    def _calibration_clickBuy(self, pos):
        if pos is None or not self.loop_active:
            return False
        self.navigation.require_shop(self.takeScreenshot())
        
        x, y = pos
        xoff, yoff = self.generateOffset() 

        #debug
        if self.debug: self.showOffsetArea(x, y, "Please check if red rectangle is within buy button's border", "click buy area")

        if not self.loop_active:
            return False
        self._tap_observed(x+xoff,y+yoff, anchor=(x,y), action='calibration buy')
        self._wait_tap_delay('calibration buy')

        #confirm
        x = self.screenwidth * 0.5677
        y = self.screenheight * 0.7037
        xoff, yoff = self.generateOffset() 

        #debug
        if self.debug: self.showOffsetArea(x, y, "Please check if red rectangle is within buy button's border", "click buy area")

        if not self.loop_active:
            return False
        self._tap_observed(x+xoff,y+yoff, anchor=(x,y), action='calibration buy confirm')
        self._wait_tap_delay('calibration buy confirm')
        #loading sleep
        self.wait(1)
        return True
    
    def _calibration_clickRefresh(self):
        if not self.loop_active:
            return False
        self.navigation.require_shop(self.takeScreenshot())
        x = self.screenwidth * 0.1698
        y = self.screenheight * 0.9138
        xoff, yoff = self.generateOffset()
        
        #debug
        if self.debug: self.showOffsetArea(x, y, "Please check if red rectangle is within refresh button's border", 'click refresh area')

        if not self.loop_active:
            return False
        self._tap_observed(x+xoff,y+yoff, anchor=(x,y), action='calibration refresh')
        self._wait_tap_delay('calibration refresh')

        if not self.loop_active: return False
        #confirm
        x = self.screenwidth * 0.5828
        y = self.screenheight * 0.6411
        xoff, yoff = self.generateOffset()
        
        #debug
        if self.debug: self.showOffsetArea(x, y, "Please check if red rectangle is within buy confirm's border", 'click confirm area')

        if not self.loop_active:
            return False
        self._tap_observed(x+xoff,y+yoff, anchor=(x,y), action='calibration refresh confirm')
        self._wait_tap_delay('calibration refresh confirm')
        return True

def getDevices(print_output):
        check_devices = subprocess.run([adb_path, 'devices'], capture_output=True, text=True)
        if print_output: print(check_devices.stdout)
        lines = check_devices.stdout.splitlines()
        devices = []
        for line in lines[1:-1]:
            seq = line.split('\t')
            devices.append(seq[0])
        return devices

CONFIG_FILE = "ADBconfig.ini"

def saveConfigFile(tap_sleep, budget, stop_refresh_key, random_offset, tap_jitter=None):
    config = configparser.ConfigParser()
    config["Settings"] = {
        "tap_sleep": str(tap_sleep),
        "budget": str(int(budget)),
        "stop_refresh_key": str(stop_refresh_key),
        "random_offset": str(random_offset)
    }
    if tap_jitter is not None:
        config['Settings']['tap_jitter'] = str(tap_jitter)
    with open(CONFIG_FILE, "w") as f:
        config.write(f)
    print('Setting saved')

def run_refresh_engine(**settings):
    app=None;started=time.time()
    try:
        app = E7ADBShopRefresh(**settings)
        app.start()
    except NavigationSetupRequired as error:
        print('E7GUI_SETUP_REQUIRED ' + str(error), flush=True)
        return False
    except MouseStopped as error:
        print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason':str(error)}),flush=True)
        if app is not None:
            app.reportLiveStats()
            app.record_session('failed', str(error))
            app.printResult()
        return False
    return True


def run_gui_session(arguments):
    """Structured startup leaves stdin available for graceful Stop in ADB mode."""
    import argparse
    from e7_engine_protocol import validate_settings
    parser = argparse.ArgumentParser(description='GUI-controlled ADB session')
    parser.add_argument('--gui-session', required=True)
    args = parser.parse_args(arguments)
    app = None
    try:
        data = json.loads(args.gui_session)
        if not isinstance(data, dict) or any(type(data.get(key)) is not bool for key in ('random_offset', 'debug')):
            raise ValueError('Invalid GUI session settings.')
        settings = validate_settings(data['device'], data['budget'], data['tap_sleep'], data['stop_key'],
                                     data['random_offset'], data['debug'], data['tap_jitter'], data.get('trace_input', False))
        app = E7ADBShopRefresh(tap_sleep=settings.tap_sleep, budget=settings.budget,
                              ip_port=settings.device, stop_refresh_key=settings.stop_key,
                              random_offset=settings.random_offset, debug=settings.debug, tap_jitter=settings.tap_jitter,
                              trace_input=settings.trace_input)
        threading.Thread(target=listen_for_stop, args=(sys.stdin, app), daemon=True).start()
        if settings.trace_input:
            print('E7GUI_TRACE_READY', flush=True)
        print('E7GUI_STARTED', flush=True)
        app.start()
        return 0
    except NavigationSetupRequired as error:
        print('E7GUI_SETUP_REQUIRED ' + str(error), flush=True)
        return 3
    except (KeyError, TypeError, ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print('E7GUI_STOPPED ' + json.dumps({'reason': str(error)}), flush=True)
        return 0 if app is not None and app._stop_requested.is_set() else 3


if __name__ == '__main__':
    if '--gui-session' in sys.argv:
        raise SystemExit(run_gui_session(sys.argv[1:]))
    if sys.argv[1:2] == ['--check-mouse-home']:
        import argparse
        from pathlib import Path
        from e7_mouse_confirmation import read_ui_text
        from e7_mouse_refresh import home_menu_target, hidden_home_matches, native_home_control_target
        parser = argparse.ArgumentParser(description='Read a saved Mouse home frame offline; no input.')
        parser.add_argument('--check-mouse-home',required=True)
        parser.add_argument('--hidden-reference',type=Path)
        args = parser.parse_args()
        with Image.open(args.check_mouse_home) as image:
            rgb = np.asarray(image.convert('RGB').resize((1920,1080),Image.Resampling.LANCZOS))
        target = native_home_control_target(rgb)
        if target is None:
            target = home_menu_target(read_ui_text(rgb,(0,180,420,920)),rgb)
        hidden = args.hidden_reference is not None and hidden_home_matches(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),args.hidden_reference)
        print(json.dumps(dict(read_only=True,state='home' if target else 'hidden-home' if hidden else 'unrecognized',target=target)))
        sys.exit(0)
    if sys.argv[1:2] == ['--check-mouse-items']:
        import argparse
        from e7_mouse_refresh import inspect_mouse_items
        parser = argparse.ArgumentParser(description='Check native currency detection on a saved shop image; no input or spending.')
        parser.add_argument('--check-mouse-items',required=True)
        args = parser.parse_args()
        print(json.dumps(inspect_mouse_items(args.check_mouse_items)))
        sys.exit(0)
    if sys.argv[1:2] == ['--check-mouse-confirmation']:
        import argparse
        from e7_mouse_confirmation import read_confirmation_text, confirmation_matches
        parser = argparse.ArgumentParser(description='Read a saved confirmation offline; no input, ADB or spending.')
        parser.add_argument('--check-mouse-confirmation',required=True)
        parser.add_argument('--operation',choices=('refresh','buy'),required=True)
        parser.add_argument('--item-name',choices=('Covenant bookmark','Mystic medal'))
        args = parser.parse_args()
        with Image.open(args.check_mouse_confirmation) as image:
            rgb = np.asarray(image.convert('RGB').resize((1920,1080),Image.Resampling.LANCZOS))
        matches = confirmation_matches(read_confirmation_text(rgb),args.operation,args.item_name)
        print(json.dumps(dict(read_only=True,text_matches=matches,operation=args.operation)))
        sys.exit(0 if matches else 2)
    if sys.argv[1:2] == ['--mouse-session']:
        from e7_mouse_refresh import run_mouse_session
        sys.exit(run_mouse_session(sys.argv[1:]))
    if sys.argv[1:2] == ['--preview-mouse-frame']:
        import argparse
        from pathlib import Path
        from e7_mouse_analysis import inspect_mouse_frame
        parser = argparse.ArgumentParser(description='Analyze a saved mouse-mode frame offline. No input or spending.')
        parser.add_argument('--preview-mouse-frame',required=True)
        parser.add_argument('--output',required=True)
        args = parser.parse_args()
        report = inspect_mouse_frame(args.preview_mouse_frame,'adb-assets')
        Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Read-only mouse preview analyzed. No game actions.')
        sys.exit(0)
    if sys.argv[1:2] == ['--prepare-navigation-references']:
        import argparse
        parser = argparse.ArgumentParser(description='Prepare private navigation references offline; no ADB or game actions.')
        parser.add_argument('--prepare-navigation-references', action='store_true')
        parser.add_argument('--home', required=True)
        parser.add_argument('--shop', required=True)
        parser.add_argument('--output', required=True)
        args = parser.parse_args()
        prepare_references(args.home, args.shop, args.output)
        print('Private Secret Shop references prepared and checked offline.')
        sys.exit(0)
    if sys.argv[1:] == ['--verify']:
        print('E7 engine: live counters v1; verified shop navigation v3; native mouse v3; window mouse v6; tap timing v2; gui session v1; input trace v1; built-in recognition and setup fallback; visible UI startup wait; sleeping stop-key poll; imports OK')
        sys.exit(0)
    if sys.argv[1:2] == ['--check-navigation-frame']:
        import argparse
        parser = argparse.ArgumentParser(description='Check a saved screenshot offline; no ADB, hooks or game actions.')
        parser.add_argument('--check-navigation-frame', required=True)
        args = parser.parse_args()
        with open(args.check_navigation_frame, 'rb') as stream:
            frame = cv2.imdecode(np.frombuffer(stream.read(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        navigation = create_navigator('adb-assets')
        visible = navigation.shop_visible(frame)
        target = None if visible else navigation.menu_target(frame)
        print(json.dumps(dict(state='shop' if visible else 'home' if target else 'unrecognized', target=target)))
        sys.exit(0 if visible or target else 2)

    import argparse
    parser = argparse.ArgumentParser(description='ADB shop refresh session')
    parser.add_argument('--tap-jitter', type=float, default=None)
    timing_args = parser.parse_args()
    if timing_args.tap_jitter is not None and (not math.isfinite(timing_args.tap_jitter) or not 0 <= timing_args.tap_jitter <= .1):
        parser.error('Timing variation must be between 0 and 0.10 seconds.')

    #intro
    print('Epic Seven Shop Refresh with ADB')
    print('Before launching this application')
    print('Make sure Epic Seven is opened and that ADB is turned on')
    print('Use an English landscape 16:9 game view, at least 640 x 360. ADB calibration requires 1920 x 1080.')
    print('(relaunch this application if the above conditions are not met)')
    print()
    print('It is normal for adb to take a few second to respond')
    input('when you finish reading, press enter to continue!')

    print()

    if not os.path.isdir(os.path.join('adb-assets')):
        print('adb-assets folder is missing!')
        input('Press enter to exit ...')
        sys.exit(0)

    ip_port = None
    adb_path = os.path.join('adb-assets', 'platform-tools', 'adb')
    #use below to test ip port on google beta developer
    #subprocess.run([adb_path, 'kill-server'])
    devices = getDevices(False)

    while(len(devices) == 0 or len(devices) > 1):
        
        print('ADB Setup')
        devices = getDevices(True)
        print('Type the ip and port of the device that you want to select or add')
        print('By leaving it blank it wil default to 127.0.0.1:5555')
        user_choice = input('Device: ') or 'localhost:5555'
        if user_choice in devices:
            ip_port = user_choice
            break
        else:
            test_connection = subprocess.run([adb_path, 'connect', user_choice], capture_output=True, text=True)
            print(test_connection.stdout)
            test_res = test_connection.stdout.split(' ')
            if test_res[0] == 'connected' and test_res[1] == 'to':
                ip_port = user_choice
                break
            else:
                print('Fail to connect, try again')
    
    if os.path.exists(CONFIG_FILE):
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
        print("Last Saved Setting:")
        for section in config.sections():
            for key, value in config[section].items():
                print(f'{key} = {value}')
        print()
        print('Use last saved setting?')
        if input('leave blank for yes, or type (yes/no): ') == 'no':
            print()
            print('Update setting')
            print()
        else:
            #print statistic
            if config.getfloat("Settings", "budget") >= 1000:
                ev_cost = 1691.04536 * config.getfloat("Settings", "budget") * 2
                ev_cov = 0.006602509 * config.getfloat("Settings", "budget") * 2
                ev_mys = 0.001700646 * config.getfloat("Settings", "budget") * 2
                print()
                print('Approximation(EV) based on current budget:')
                print(f'Cost: {int(ev_cost):,} (make sure you have at least this much gold)')
                print(f'Cov: {ev_cov:.1f}')
                print(f'mys: {ev_mys:.1f}')
                print()
            
            #Run refresh based on config file
            input('Press enter to start!')
            print(f'Press "{config["Settings"]["stop_refresh_key"]}" to terminate anytime!')
            print()
            print('Progress:')
            if not run_refresh_engine(tap_sleep=config.getfloat("Settings", "tap_sleep"),
                                    budget=config.getfloat("Settings", "budget"),
                                    ip_port=ip_port,
                                    stop_refresh_key=config["Settings"]["stop_refresh_key"],
                                    random_offset=config.getboolean("Settings", "random_offset"),
                                    tap_jitter=timing_args.tap_jitter if timing_args.tap_jitter is not None else config.getfloat('Settings', 'tap_jitter', fallback=None),
                                    debug=False):
                sys.exit(3)
            print()
            input('press enter to exit...')
            sys.exit(0)


    debug = False
    print('First time user should always launch in debug mode')
    if input('Launch in debug mode? leave bank for no (yes/no): ').lower() == 'yes':
        debug = True
        print()
        print('Debug mode:')
        print('Only Covenant bookmarks and Mystic medals are purchased.')
        print('It will pause to generate a image window - will show up in the taskbar')
        print('If the click area shown is not within the UI button, do not use the randomize click feature')
        print('Closing the image window will continue to refresh action')
    else:
        print('Running as normal')
        print()

    #setting
    stop_refresh_key = 'esc'
    if debug:
        print('Check each highlighted target before continuing.')
        print('Use "esc" key to exit in debug mode')
    else:
        print("Input the key that you want to use to stop refresh (0-9 a-z /.,';[]) ")
        print('Leave blank to use "esc" key')
        stop_refresh_key = input('Key: ')
        
        if stop_refresh_key:
            print(f'"{stop_refresh_key}" key will be use to stop refresh')
        else:
            stop_refresh_key = 'esc'
            print('Default "esc" key to stop refresh')
    print()
    
    random_offset = False
    print('Only enable randomize click after going through a full loop of buying something in debug mode')
    if debug:
        random_offset = True
        print('Automatically enable randomize click due to debug mode')
    elif input('Enable randomize click (yes/no): ').lower() == 'yes':
        random_offset = True
        print('Randomize click enabled')
    else:
        print('Randomize click disabled')
    print()
    

    try:
        tap_sleep = float(input('Tap sleep(in seconds) Recommend - leave blank for 0.3 sec : '))
        if not math.isfinite(tap_sleep) or tap_sleep <= 0:
            raise ValueError('Invalid tap delay')
    except:
        print('Default to tap sleep of 0.3 second')
        tap_sleep = 0.3
    print()
    try:
        budget = 100
        if debug:
            print('Default to 100 skystone for debug testing')
        else:
            budget = int(input('Amount of skystone that you want to spend: '))
        if budget < 3:
            raise ValueError('Budget below one refresh')
    except ValueError:
        print('Invalid skystone budget: enter a whole number of at least 3.')
        sys.exit(2)
    
    if not debug:
        print()
        saveConfigFile(tap_sleep=tap_sleep, budget=budget, stop_refresh_key=stop_refresh_key, random_offset=random_offset, tap_jitter=timing_args.tap_jitter)
        print()

    if budget >= 1000:
            ev_cost = 1691.04536 * int(budget) * 2
            ev_cov = 0.006602509 * int(budget) * 2
            ev_mys = 0.001700646 * int(budget) * 2
            print('Approximation(EV) based on current budget:')
            print(f'Cost: {int(ev_cost):,} (make sure you have at least this much gold)')
            print(f'Cov: {ev_cov:.1f}')
            print(f'mys: {ev_mys:.1f}')
            print()
    input('Press enter to start!')
    print(f'Press "{stop_refresh_key}" to terminate anytime!')
    print()
    print('Progress:')
    if not run_refresh_engine(tap_sleep=tap_sleep,
                               budget=budget,
                               ip_port=ip_port,
                               stop_refresh_key=stop_refresh_key,
                               random_offset=random_offset,
                               tap_jitter=timing_args.tap_jitter,
                               debug=debug):
        sys.exit(3)
    print()
    input('press enter to exit...')
