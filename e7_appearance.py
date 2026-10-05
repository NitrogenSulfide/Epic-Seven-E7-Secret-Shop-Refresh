"""Static, locally composited scenery for Tk; no window or desktop transparency."""
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except ImportError:
    Image = None


def avatar_icon(master, asset_dir, size):
    if Image is None:
        return None
    try:
        with Image.open(asset_dir / 'blue-natto-minimal-mark.png') as source:
            icon = source.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(icon, master=master)
    except OSError:
        return None


def github_icon(master, asset_dir, size, dark, color=None):
    if Image is None:
        return None
    filename = 'github-white.png' if dark else 'github-black.png'
    try:
        with Image.open(asset_dir / filename) as source:
            icon = source.convert('RGBA')
            icon.thumbnail((size, size), Image.Resampling.LANCZOS)
            if color:
                tinted = Image.new('RGBA', icon.size, color)
                tinted.putalpha(icon.getchannel('A'))
                icon = tinted
        return ImageTk.PhotoImage(icon, master=master)
    except OSError:
        return None


def bug_icon(master, size):
    if Image is None:
        return None
    s = size * 3
    image = Image.new('RGBA', (s, s))
    draw = ImageDraw.Draw(image)
    blue, ink = '#60a5fa', '#2563eb'
    width = max(2, s // 14)
    for y in (.37, .55, .73):
        draw.line((s*.12, s*y, s*.88, s*y), fill=blue, width=width)
    draw.line((s*.35,s*.08,s*.43,s*.25), fill=blue, width=width)
    draw.line((s*.65,s*.08,s*.57,s*.25), fill=blue, width=width)
    draw.ellipse((s*.29,s*.21,s*.71,s*.89), fill=blue)
    draw.line((s*.5,s*.42,s*.5,s*.79), fill=ink, width=max(2,s//20))
    return ImageTk.PhotoImage(image.resize((size,size), Image.Resampling.LANCZOS), master=master)


def coffee_icon(master, size):
    if Image is None:
        return None
    s = size * 3
    image = Image.new('RGBA', (s, s))
    draw = ImageDraw.Draw(image)
    blue = '#60a5fa'
    draw.arc((s*.59, s*.31, s*.93, s*.71), 270, 90, fill=blue, width=max(2, s//12))
    draw.rounded_rectangle((s*.13, s*.27, s*.70, s*.79), radius=s*.12, fill=blue)
    draw.line((s*.10, s*.90, s*.82, s*.90), fill=blue, width=max(2, s//14))
    return ImageTk.PhotoImage(image.resize((size, size), Image.Resampling.LANCZOS), master=master)


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


def profile_avatar(master, assets, size):
    if Image is None:
        return None
    try:
        with Image.open(assets/'blue-natto-avatar.png') as source:
            avatar = ImageOps.fit(source.convert('RGBA'), (size,size), Image.Resampling.LANCZOS)
        mask = Image.new('L', (size,size))
        ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1), fill=255)
        avatar.putalpha(mask)
        return ImageTk.PhotoImage(avatar,master=master)
    except (OSError,tk.TclError):
        return None


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
        self.canvas_image = None
        self.canvas_photo = None
        self.canvas_rectangle = None
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
                    scene = source.convert('RGB')
                    self.sources[dark] = Image.blend(Image.new('RGB', scene.size, '#111827' if dark else '#f3f5f8'),
                                                    scene, .23 if dark else .20)
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
        # Root moves do not change the relative artwork coordinates.
        if event is not None and event.widget is self.root and self.cache_key == (
                self.root.winfo_width(), self.root.winfo_height(), self.root.dark_mode.get()):
            return
        if self.job is None:
            # Throttle instead of indefinitely postponing repaint during resizing.
            self.job = self.root.after(35 if event is not None else 0, self.render)

    def render(self):
        if self.job is not None:
            self.root.after_cancel(self.job)
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
            # Tint is already composed; soft background artwork needs no sharp
            # Lanczos resampling on every intermediate window size.
            self.backdrop = ImageOps.fit(self.sources[dark],(width,height),Image.Resampling.BILINEAR)
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
        # Paint the unused settings viewport too; use only the embedded controls
        # for its scrollregion, so this decoration cannot create a scrollbar.
        canvas = self.root.settings_canvas
        if canvas.winfo_ismapped():
            x, y = canvas.winfo_rootx()-rx, canvas.winfo_rooty()-ry
            rectangle = (x, y, canvas.winfo_width(), canvas.winfo_height(), key)
            if rectangle != self.canvas_rectangle:
                crop = self.backdrop.crop((x, y, x+rectangle[2], y+rectangle[3]))
                self.canvas_photo = ImageTk.PhotoImage(crop, master=self.root)
                if self.canvas_image is None:
                    self.canvas_image = canvas.create_image(0, 0, anchor='nw', tags='scenery')
                canvas.itemconfigure(self.canvas_image, image=self.canvas_photo)
                self.canvas_rectangle = rectangle
            canvas.coords(self.canvas_image, canvas.canvasx(0), canvas.canvasy(0))
            canvas.tag_lower(self.canvas_image)
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
