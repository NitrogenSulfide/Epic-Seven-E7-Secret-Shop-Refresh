"""Normalized recognition frames and reversible device coordinate mapping."""
from dataclasses import dataclass
import math
import numpy as np
from PIL import Image
from e7_windows_capture import game_view
from e7_native_mouse import MouseStopped

@dataclass(frozen=True)
class FrameGeometry:
    source_size: tuple[int,int]
    bounds: tuple[int,int,int,int]

    def point(self,x,y):
        if not all(math.isfinite(value) for value in (x,y)) or not (0<=x<1920 and 0<=y<1080):
            raise MouseStopped('Invalid game target. No input sent.')
        left,top,right,bottom=self.bounds
        return (min(right-1,round(left+x*(right-left)/1920)),
                min(bottom-1,round(top+y*(bottom-top)/1080)))

def normalize_game_frame(image,*,bounds=None,native_stove=False):
    source=image.size
    if bounds is None:view,bounds=game_view(image.convert('RGB'))
    else:view=image.convert('RGB').crop(bounds)
    width,height=view.size
    aspect=width/height if height else 0
    supported=abs(aspect-16/9)<=.035
    # STOVE fills maximized client areas (for example 3840 x 2019).
    # Preserve the whole client: cropping to 16:9 would discard UI targets.
    if native_stove is True and 16/9<=aspect<=2:
        supported=True
    if width<640 or height<360 or not supported:
        raise MouseStopped('Use a landscape game view of at least 640 x 360 with a supported 16:9 layout.')
    rgb=np.asarray(view.resize((1920,1080),Image.Resampling.LANCZOS))
    return rgb,FrameGeometry(source,bounds)
