"""Read confirmation text locally; never move the pointer or contact the game."""
import atexit
import base64
import copy
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
from PIL import Image, ImageOps
import numpy as np


def level_box(box, angle, size):
    """Map a word box from Windows OCR's deskewed frame back to the image.

    Game UI text is level, but sparse crops (one shop row) can be assigned a
    small text angle. Windows then reports word bounds rotated about the image
    centre, shifting far-apart words in opposite directions. Rotate each word
    centre back; the box size is kept.
    """
    if not angle:
        return list(box)
    theta = math.radians(float(angle))
    cx, cy = size[0]/2, size[1]/2
    x1, y1, x2, y2 = box
    dx, dy = (x1+x2)/2-cx, (y1+y2)/2-cy
    x = cx + dx*math.cos(theta) - dy*math.sin(theta)
    y = cy + dx*math.sin(theta) + dy*math.cos(theta)
    half_width, half_height = (x2-x1)/2, (y2-y1)/2
    return [x-half_width, y-half_height, x+half_width, y+half_height]


def _powershell_command():
    helper = Path('mouse_confirmation_ocr.ps1')
    if not helper.is_file():
        raise ValueError('The Mouse confirmation helper is missing. Use the complete player folder.')
    script = helper.read_text(encoding='utf-8-sig')
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    powershell = Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return [str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded]


class _OcrServer:
    """One persistent Windows OCR process: PowerShell and WinRT start once,
    not on every read. Any failure closes it; callers then use a one-shot read."""

    def __init__(self, command, *, popen=subprocess.Popen):
        environment = dict(os.environ); environment['E7_MOUSE_OCR_SERVE'] = '1'
        self.process = popen(command,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.replies = queue.Queue()
        def pump(stream=self.process.stdout, replies=self.replies):
            for line in stream:
                replies.put(line)
            replies.put(None)
        threading.Thread(target=pump,name='E7 OCR',daemon=True).start()

    def read(self, path, timeout=10):
        self.process.stdin.write(str(path)+'\n'); self.process.stdin.flush()
        try:
            line = self.replies.get(timeout=timeout)
        except queue.Empty:
            line = None
        if line is None:
            raise OSError('The OCR process stopped answering.')
        result = json.loads(line)
        if isinstance(result,dict) and 'error' in result:
            raise ValueError(str(result['error']))
        return result

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=2)
        except Exception:
            self.process.kill()


_ocr_server = None
_ocr_server_lock = threading.Lock()


def close_ocr_server():
    global _ocr_server
    with _ocr_server_lock:
        server, _ocr_server = _ocr_server, None
    if server:
        server.close()


atexit.register(close_ocr_server)


def _windows_ocr(path):
    """Built-in Windows OCR through the bundled PowerShell helper."""
    global _ocr_server
    command = _powershell_command()
    with _ocr_server_lock:
        try:
            if _ocr_server is None and os.environ.get('E7_OCR_SERVER','1') != '0':
                _ocr_server = _OcrServer(command)
            if _ocr_server:
                return _ocr_server.read(path)
        except (OSError, ValueError):
            # Fall back to the one-shot read below and keep using it.
            if _ocr_server:
                _ocr_server.close()
            _ocr_server = False
    environment = dict(os.environ); environment['E7_MOUSE_OCR_FRAME'] = str(path)
    child = subprocess.run(command,env=environment,capture_output=True,text=True,
                           encoding='utf-8',timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    if child.returncode:
        raise ValueError('Windows could not read the confirmation. No confirmation click sent.')
    return json.loads(child.stdout)


# Tesseract reads small game UI text best upscaled, in sparse-text mode
# (measured on Steam/Proton frames: names, "1/1 Buy", prices and stock lines).
TESSERACT_SCALE = 2


def _tesseract_ocr(path, *, upscale=TESSERACT_SCALE):
    """Tesseract with the same result shape as Windows OCR (words in crop pixels)."""
    import csv, io, shutil
    program = shutil.which('tesseract')
    if program is None:
        raise ValueError('Tesseract OCR is not installed (Debian/Ubuntu/Mint: tesseract-ocr). No confirmation click sent.')
    with Image.open(path) as image:
        gray = image.convert('L')
        if upscale != 1:
            gray = gray.resize((gray.width*upscale,gray.height*upscale),Image.Resampling.BICUBIC)
        gray.save(path)
    child = subprocess.run([program,str(path),'stdout','--psm','11','-l','eng','tsv'],
                           capture_output=True,text=True,encoding='utf-8',timeout=20)
    if child.returncode:
        raise ValueError('Tesseract could not read the frame. No confirmation click sent.')
    lines, words = {}, []
    for row in csv.DictReader(io.StringIO(child.stdout),delimiter='\t',quoting=csv.QUOTE_NONE):
        text = (row.get('text') or '').strip()
        if row.get('level') != '5' or not text:
            continue
        x,y,w,h = (int(row[key])/upscale for key in ('left','top','width','height'))
        words.append(dict(text=text,box=[x,y,x+w,y+h]))
        lines.setdefault((row['block_num'],row['par_num'],row['line_num']),[]).append(text)
    return dict(text='\n'.join(' '.join(line) for line in lines.values()),angle=None,words=words)


def ocr_backend():
    return 'windows' if os.name == 'nt' and os.environ.get('E7_OCR','').lower() != 'tesseract' else 'tesseract'


# Reads of the most recent frame. Recognition reads the same dialog region
# more than once per capture; a new frame (a new array) clears it.
_frame_reads = {'rgb': None, 'results': {}}


def read_ui_text(rgb, region, *, scale=1, contrast=False):
    key = (tuple(region), scale, bool(contrast))
    if _frame_reads['rgb'] is not rgb:
        _frame_reads['rgb'], _frame_reads['results'] = rgb, {}
    elif key in _frame_reads['results']:
        return copy.deepcopy(_frame_reads['results'][key])
    result = _read_ui_text(rgb, region, scale=scale, contrast=contrast)
    _frame_reads['results'][key] = copy.deepcopy(result)
    return result


def _read_ui_text(rgb, region, *, scale=1, contrast=False):
    # Only this temporary crop is removed on exit; no runtime captures/settings
    # are read, moved or deleted. The text is kept in memory and not logged.
    with tempfile.TemporaryDirectory(prefix='e7-confirm-') as temp:
        path = Path(temp)/'dialog.png'
        left,top,right,bottom = region
        crop = Image.fromarray(rgb[top:bottom,left:right])
        if contrast:
            crop = ImageOps.autocontrast(crop.convert('L')).convert('RGB')
        if scale != 1:
            crop = crop.resize((crop.width*scale,crop.height*scale),Image.Resampling.BICUBIC)
        crop.save(path)
        try:
            result = _windows_ocr(path) if ocr_backend() == 'windows' else _tesseract_ocr(path)
        except subprocess.TimeoutExpired:
            raise ValueError('Text recognition timed out. No confirmation click sent.') from None
        except json.JSONDecodeError:
            raise ValueError('The confirmation text was unreadable. No confirmation click sent.') from None
    try:
        result['text'] = str(result['text']).lower()
        size = (crop.width,crop.height)
        result['words'] = [dict(text=str(word['text']).lower(),
            box=[value/scale+offset for value,offset in
                 zip(level_box(word['box'],result.get('angle'),size),(left,top,left,top))])
            for word in result.get('words',[])]
        return result
    except (ValueError,KeyError,TypeError):
        raise ValueError('The confirmation text was unreadable. No confirmation click sent.') from None


def read_confirmation_text(rgb):
    result=read_ui_text(rgb,(500,260,1450,950))
    # The foreground prompt/product/buttons are bright; the shop behind the
    # translucent modal is dimmed. Keep OCR word bounds and verify their ink,
    # instead of combining background inventory text with the intended price.
    foreground=[]
    for word in result.get('words',[]):
        x1,y1,x2,y2=(int(value) for value in word['box'])
        crop=rgb[max(0,y1):min(rgb.shape[0],y2),max(0,x1):min(rgb.shape[1],x2)]
        if not crop.size:continue
        brightness=crop.max(axis=2)
        if np.quantile(brightness,.90)>=135 and np.quantile(brightness,.95)>=155:
            foreground.append(word['text'])
    return ' '.join(foreground).lower()


def confirmation_matches(text,operation,item_name=None):
    text = text.lower()
    if any(word in text for word in ('not enough','insufficient','buy skystone','purchase skystone','connection','reconnect')):
        return False
    if 'cancel' not in text or not any(word in text for word in ('confirm','purchase','buy','refresh')):
        return False
    if operation == 'refresh':
        native_prompt=bool(re.search(r'\buse\s+skystone\s+to\s+refresh\??',text))
        # STOVE's dialog omits the amount; its exact operation prompt confirms
        # the game's fixed three-skystone Refresh. Reject contradictory numbers.
        numbers=re.findall(r'\b\d[\d,.\u00a0]*\b',text)
        if re.search(r'\b(buy|purchase|covenant|mystic|friendship)\b',text):return False
        if any(re.sub(r'[, .\u00a0]','',number)!='3' for number in numbers):return False
        return 'refresh' in text and 'skystone' in text and (bool(numbers) or native_prompt)
    expected = {'Covenant bookmark':('covenant','bookmarks?','184000'),
                'Mystic medal':('mystic','medals?','280000'),
                'Friendship points':('friendship','points?','18000')}
    if operation != 'buy' or item_name not in expected:
        return False
    item,noun,price = expected[item_name]
    others = [prefix for prefix,_,_ in expected.values() if prefix != item]
    if re.search(r'\b(?:'+'|'.join(others)+r'|refresh)\b',text):return False
    if not re.search(r'\b'+item+r'\s+'+noun+r'\b',text):return False
    numbers=[re.sub(r'[, .\u00a0]','',number) for number in re.findall(r'\b\d[\d,.\u00a0]*\b',text)]
    amounts=[number for number in numbers if int(number)>=1000]
    return bool(amounts) and all(number==price for number in amounts)
