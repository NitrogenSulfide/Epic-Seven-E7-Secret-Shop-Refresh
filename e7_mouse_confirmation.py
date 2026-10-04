"""Read confirmation text locally; never move the pointer or contact the game."""
import json
import base64
import os
from pathlib import Path
import re
import subprocess
import tempfile
from PIL import Image


def read_confirmation_text(rgb):
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
        Image.fromarray(rgb[260:950,500:1450]).save(path)
        environment = dict(os.environ); environment['E7_MOUSE_OCR_FRAME'] = str(path)
        child = subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                               env=environment,capture_output=True,text=True,
                               encoding='utf-8',timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    if child.returncode:
        raise ValueError('Windows could not read the confirmation. No confirmation click sent.')
    try:
        result = json.loads(child.stdout)
        return str(result['text']).lower()
    except (ValueError,KeyError,TypeError):
        raise ValueError('The confirmation text was unreadable. No confirmation click sent.') from None


def confirmation_matches(text,operation,item_name=None):
    text = text.lower()
    if any(word in text for word in ('not enough','insufficient','buy skystone','purchase skystone','connection','reconnect')):
        return False
    if 'cancel' not in text or not any(word in text for word in ('confirm','purchase','buy','refresh')):
        return False
    if operation == 'refresh':
        return 'refresh' in text and 'skystone' in text and bool(re.search(r'\b3\b',text))
    if operation != 'buy' or item_name not in ('Covenant bookmark','Mystic medal'):
        return False
    item,price = ('covenant','184000') if item_name == 'Covenant bookmark' else ('mystic','280000')
    numbers = re.sub(r'[, .\u00a0]','',text)
    return item in text and price in numbers
