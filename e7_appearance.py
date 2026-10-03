"""Static, locally composited scenery for Tk; no window or desktop transparency."""
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except ImportError:
    Image = None


def theme_icon(master, size, dark):
    if Image is None:
        return None
    canvas = Image.new('RGBA', (size*3, size*3))
    draw = ImageDraw.Draw(canvas)
    color = '#fbbf24' if dark else '#334155'
    s = size*3
    if dark:
        draw.ellipse((s*.30,s*.30,s*.70,s*.70), fill=color)
        import math
        for angle in range(0,360,45):
            a = math.radians(angle)
            draw.line((s*(.5+.31*math.cos(a)),s*(.5+.31*math.sin(a)),
                       s*(.5+.43*math.cos(a)),s*(.5+.43*math.sin(a))), fill=color, width=max(2,s//16))
    else:
        draw.ellipse((s*.16,s*.12,s*.84,s*.87), fill=color)
        draw.ellipse((s*.38,s*.03,s*.96,s*.66), fill=(0,0,0,0))
    return ImageTk.PhotoImage(canvas.resize((size,size), Image.Resampling.LANCZOS), master=master)


def currency_icons(master, assets, size):
    if Image is None:
        return {}
    icons = {}
    for key, name in (('mystic','mystic-medal.png'),('covenant','covenant-bookmark.png'),('spent','skystone.png')):
        path = assets/name
        if path.is_file():
            with Image.open(path) as original:
                image = original.convert('RGBA')
                # Transparent padding in the supplied currency images should
                # not make one counter's icon appear much smaller than another.
                bounds = image.getbbox()
                if bounds:
                    image = image.crop(bounds)
                image.thumbnail((size,size), Image.Resampling.LANCZOS)
                tile = Image.new('RGBA',(size,size))
                tile.alpha_composite(image,((size-image.width)//2,(size-image.height)//2))
                icons[key] = ImageTk.PhotoImage(tile,master=master)
    return icons


class Scenery:
    """Align tinted image crops across otherwise opaque ttk frames and labels.

    Fields/tables remain solid for legibility. Crop images have zero layout
    minimums, so they never change geometry or create resize feedback loops.
    The original files stay intact; all blending is an in-memory UI render.
    """
    def __init__(self, root, assets):
        self.root, self.assets = root, assets
        self.widgets = []
        self.checkbox_styles = {}
        self.job = None
        self.cache_key = None
        self.renders = 0
        self.render_calls = 0
        self.checkbox_theme = None
        self.layer = tk.Label(root,borderwidth=0,highlightthickness=0)
        self.layer.place(x=0,y=0,relwidth=1,relheight=1)
        self.layer.lower()
        if Image is None:
            return
        self.sources = {}
        for dark, filename in ((False,'background-day-hd.png'),(True,'background-night-hd.png')):
            path = assets/filename
            if path.is_file():
                with Image.open(path) as source:
                    self.sources[dark] = source.convert('RGB')
        style = ttk.Style(root)
        def visit(parent):
            for widget in parent.winfo_children():
                visit(widget)
                if widget.winfo_class() not in ('TFrame','TLabel','TCheckbutton'):
                    continue
                ancestor = widget.master
                while ancestor is not root and ancestor.winfo_class() != 'TLabelframe':
                    ancestor = ancestor.master
                if ancestor is not root:
                    continue  # Keep the estimate's solid reading surface intact.
                original = widget.cget('style') or widget.winfo_class()
                name = f'Scenery{len(self.widgets)}.{original}'
                element = f'Scenery{len(self.widgets)}.image'
                # Tiny 1px image elements tile millions of times on a HiDPI
                # window before the first composition. Use a cheap large
                # placeholder; its zero layout minimum still claims no space.
                photo = tk.PhotoImage(master=root,width=128,height=128)
                style.element_create(element,'image',photo,sticky='nswe',width=0,height=0)
                children = [('Label.padding',{'sticky':'nswe','children':[('Label.label',{'sticky':'nswe'})]})] if widget.winfo_class() == 'TLabel' else []
                if widget.winfo_class() == 'TCheckbutton':
                    children = style.layout(original)
                    self.checkbox_styles[widget] = (name,element,original)
                options = {'sticky':'nswe'}
                if children:
                    options['children'] = children
                style.layout(name,[(element,options)])
                widget.configure(style=name)
                self.widgets.append([widget,photo,None])
        visit(root)
        root.bind('<Configure>',self.schedule,add='+')

    def schedule(self, event=None):
        if Image is None or not getattr(self,'sources',{}):
            return
        if self.job is not None:
            self.root.after_cancel(self.job)
        self.job = self.root.after(140,self.render)

    def render(self):
        self.job = None
        self.render_calls += 1
        dark = self.root.dark_mode.get()
        if dark not in self.sources:
            return
        width,height = self.root.winfo_width(),self.root.winfo_height()
        if width < 20 or height < 20:
            return
        key = (width,height,dark)
        if key != self.cache_key:
            scene = ImageOps.fit(self.sources[dark],(width,height),Image.Resampling.LANCZOS)
            tint = Image.new('RGB',(width,height),'#111827' if dark else '#f3f5f8')
            self.backdrop = Image.blend(tint,scene,.23 if dark else .20)
            self.layer_image = ImageTk.PhotoImage(self.backdrop,master=self.root)
            self.layer.configure(image=self.layer_image)
            self.cache_key = key
            self.renders += 1
        style = ttk.Style(self.root)
        if self.checkbox_theme != dark:
            for widget,(name,element,original) in self.checkbox_styles.items():
                style.layout(name,[(element,{'sticky':'nswe','children':style.layout(original)})])
            self.checkbox_theme = dark
        rx,ry = self.root.winfo_rootx(),self.root.winfo_rooty()
        for item in self.widgets:
            widget,photo,previous = item
            if not widget.winfo_exists() or not widget.winfo_ismapped():
                continue
            x,y = widget.winfo_rootx()-rx,widget.winfo_rooty()-ry
            w,h = widget.winfo_width(),widget.winfo_height()
            rectangle = (x,y,w,h,key)
            if rectangle == previous or w < 1 or h < 1:
                continue
            crop = self.backdrop.crop((x,y,x+w,y+h))
            cards = self.root.metric_cards
            if widget in cards or widget.master in cards:
                crop = Image.blend(crop,Image.new('RGB',(w,h),'#1e293b' if dark else '#ffffff'),.72)
                if widget in cards:
                    draw = ImageDraw.Draw(crop)
                    draw.rounded_rectangle((0,0,w-1,h-1),radius=self.root._dp(8),outline='#475569' if dark else '#cbd5e1')
            temporary = ImageTk.PhotoImage(crop,master=self.root)
            photo.configure(width=w,height=h)
            photo.tk.call(str(photo),'copy',str(temporary))
            # ttk image elements don't repaint when their source pixels change.
            # Reapply the existing style after filling the crop, without
            # changing its geometry or the widget's options.
            widget.configure(style=widget.cget('style'))
            item[2] = rectangle

    def close(self):
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None


class ThemeHint:
    def __init__(self, button, text):
        self.button,self.text = button,text
        self.job,self.window = None,None
        button.bind('<Enter>',self.enter,add='+')
        button.bind('<Leave>',self.hide,add='+')
        button.bind('<ButtonPress>',self.hide,add='+')
        button.bind('<FocusIn>',self.enter,add='+')
        button.bind('<FocusOut>',self.hide,add='+')

    def enter(self,event=None):
        self.hide()
        self.job = self.button.after(500,self.show)

    def show(self):
        self.job = None
        self.window = tk.Toplevel(self.button)
        self.window.overrideredirect(True)
        self.window.geometry(f'+{self.button.winfo_rootx()-100}+{self.button.winfo_rooty()+self.button.winfo_height()+6}')
        tk.Label(self.window,text=self.text(),bg='#0f172a',fg='white',padx=10,pady=6).pack()

    def hide(self,event=None):
        if self.job is not None:
            self.button.after_cancel(self.job)
            self.job = None
        if self.window is not None:
            self.window.destroy()
            self.window = None
