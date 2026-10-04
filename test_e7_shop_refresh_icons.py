from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import tempfile
import sys
from unittest.mock import patch
import e7_shop_refresh_gui as gui
from e7_windows_icon import WindowIcons

class IconInfo(ctypes.Structure):
    _fields_=[('is_icon',wintypes.BOOL),('x',wintypes.DWORD),('y',wintypes.DWORD),('mask',wintypes.HANDLE),('color',wintypes.HANDLE)]
class Bitmap(ctypes.Structure):
    _fields_=[('type',wintypes.LONG),('width',wintypes.LONG),('height',wintypes.LONG),('stride',wintypes.LONG),('planes',wintypes.WORD),('bits_pixel',wintypes.WORD),('bits',ctypes.c_void_p)]
user=ctypes.WinDLL('user32',use_last_error=True)
gdi=ctypes.WinDLL('gdi32',use_last_error=True)
user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
user.GetAncestor.restype=wintypes.HWND
user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
user.SendMessageW.restype=wintypes.LPARAM
user.GetClassLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]
user.GetClassLongPtrW.restype=wintypes.LPARAM
user.GetIconInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(IconInfo)]
gdi.GetObjectW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p]
gdi.DeleteObject.argtypes=[wintypes.HANDLE]

def icon_size(hwnd,kind):
    icon=user.SendMessageW(hwnd,0x7F,kind,0)
    if not icon:
        icon=user.GetClassLongPtrW(hwnd,-14 if kind==1 else -34)
    info=IconInfo()
    assert user.GetIconInfo(icon,ctypes.byref(info))
    try:
        bitmap=Bitmap()
        assert gdi.GetObjectW(info.color,ctypes.sizeof(bitmap),ctypes.byref(bitmap))
        return [bitmap.width,bitmap.height]
    finally:
        if info.mask:gdi.DeleteObject(info.mask)
        if info.color:gdi.DeleteObject(info.color)

def main():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        with patch.object(gui.RefreshGui,'refresh_devices',lambda _:None), patch.object(gui.RefreshGui,'_schedule_native_icon',lambda *args:None), patch.object(gui,'CONFIG_FILE',root/'config.ini'),patch.object(gui,'GUI_CONFIG_FILE',root/'gui.ini'),patch.object(gui,'HISTORY_FILE',root/'history.csv'):
            app=gui.RefreshGui()
        app.update()
        hwnd=user.GetAncestor(app.winfo_id(),2)
        report=dict(before=dict(big=icon_size(hwnd,1),small=icon_size(hwnd,0)))
        app._apply_native_icon()
        app.update()
        assert app._native_icons is not None,app.raw_output
        report['after']=dict(dpi=app._native_icons.dpi,big=icon_size(hwnd,1),small=icon_size(hwnd,0))
        for dpi,big,small in [(96,32,16),(120,40,20),(144,48,24),(192,64,32),(288,96,48)]:
            replacement=WindowIcons(hwnd,(gui.ASSET_DIR/'shopkeeper-v2.ico').read_bytes(),dpi=dpi)
            app._native_icons.close()
            app._native_icons=replacement
            assert icon_size(hwnd,1)==[big,big]
            assert icon_size(hwnd,0)==[small,small]
        report['dpi_checks']='96, 120, 144, 192, 288: exact native icon dimensions verified.'
        app.destroy()
    print(json.dumps(report,indent=2))
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__ == "__main__":
    main()
