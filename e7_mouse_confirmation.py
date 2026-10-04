"""Read confirmation text locally; never move the pointer or contact the game."""
import json
import base64
import os
from pathlib import Path
import re
import subprocess
import tempfile
from PIL import Image
import numpy as np


def read_ui_text(rgb, region):
    helper = Path('mouse_confirmation_ocr.ps1')
    if not helper.is_file():
        raise ValueError('The Mouse confirmation helper is missing. Use the complete player folder.')
    script = helper.read_text(encoding='utf-8-sig')
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    powershell = Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    # Only this temporary crop is removed on exit; no runtime captures/settings
    # are read, moved or deleted. The text is kept in memory and not logged.
    with tempfile.TemporaryDirectory(prefix='e7-confirm-') as temp:
        path = Path(temp)/'dialog.png'
        left,top,right,bottom = region
        Image.fromarray(rgb[top:bottom,left:right]).save(path)
        environment = dict(os.environ); environment['E7_MOUSE_OCR_FRAME'] = str(path)
        child = subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                               env=environment,capture_output=True,text=True,
                               encoding='utf-8',timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    if child.returncode:
        raise ValueError('Windows could not read the confirmation. No confirmation click sent.')
    try:
        result = json.loads(child.stdout)
        result['text'] = str(result['text']).lower()
        result['words'] = [dict(text=str(word['text']).lower(),
            box=[word['box'][0]+left,word['box'][1]+top,word['box'][2]+left,word['box'][3]+top])
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
        if re.search(r'\b(buy|purchase|covenant|mystic)\b',text):return False
        if any(re.sub(r'[, .\u00a0]','',number)!='3' for number in numbers):return False
        return 'refresh' in text and 'skystone' in text and (bool(numbers) or native_prompt)
    if operation != 'buy' or item_name not in ('Covenant bookmark','Mystic medal'):
        return False
    item,noun,price,other = ('covenant','bookmarks?','184000','mystic') if item_name == 'Covenant bookmark' else ('mystic','medals?','280000','covenant')
    if re.search(r'\b'+other+r'\b|\brefresh\b',text):return False
    if not re.search(r'\b'+item+r'\s+'+noun+r'\b',text):return False
    numbers=[re.sub(r'[, .\u00a0]','',number) for number in re.findall(r'\b\d[\d,.\u00a0]*\b',text)]
    amounts=[number for number in numbers if int(number)>=1000]
    return bool(amounts) and all(number==price for number in amounts)
