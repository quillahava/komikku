# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import datetime
from functools import cache
from functools import wraps
from gettext import gettext as _
import gi
import html
from io import BytesIO
import logging
import os
from PIL import Image
from PIL import ImageChops
import requests
import subprocess
import traceback

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository.GdkPixbuf import Colorspace
from gi.repository.GdkPixbuf import InterpType
from gi.repository.GdkPixbuf import Pixbuf
from gi.repository.GdkPixbuf import PixbufAnimation

logger = logging.getLogger('komikku')


def check_cmdline_tool(cmd):
    try:
        p = subprocess.Popen(cmd, bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        out, _ = p.communicate()
    except Exception:
        return False, None
    else:
        return p.returncode == 0, out.decode('utf-8').strip()


def create_paintable_from_data(data, width=None, height=None, static_animation=False, preserve_aspect_ratio=True):
    mime_type, _result_uncertain = Gio.content_type_guess(None, data)
    if not mime_type:
        return None

    if mime_type == 'image/gif' and not static_animation:
        return PaintablePixbufAnimation.new_from_data(data)

    return PaintablePixbuf.new_from_data(data, width, height, preserve_aspect_ratio)


def create_paintable_from_file(path, width=None, height=None, static_animation=False, preserve_aspect_ratio=True):
    format_, _width, _height = Pixbuf.get_file_info(path)
    if format_ is None:
        return None

    if 'image/gif' in format_.get_mime_types() and not static_animation:
        return PaintablePixbufAnimation.new_from_file(path, width, height)

    return PaintablePixbuf.new_from_file(path, width, height, preserve_aspect_ratio)


def create_paintable_from_resource(path, width=None, height=None, preserve_aspect_ratio=True):
    return PaintablePixbuf.new_from_resource(path, width, height, preserve_aspect_ratio)


def crop_pixbuf(pixbuf, src_x, src_y, width, height):
    pixbuf_cropped = Pixbuf.new(Colorspace.RGB, pixbuf.get_has_alpha(), 8, width, height)
    pixbuf.copy_area(src_x, src_y, width, height, pixbuf_cropped, 0, 0)

    return pixbuf_cropped


def expand_and_resize_cover(buffer):
    """Convert and resize a cover (except animated GIF)

    Covers in landscape format are convert to portrait format"""

    def get_dominant_color(img):
        # Resize image to reduce number of colors
        colors = img.resize((150, 150), resample=0).getcolors(150 * 150)
        sorted_colors = sorted(colors, key=lambda t: t[0])

        return sorted_colors[-1][1]

    def remove_alpha(img):
        if img.mode not in ('P', 'RGBA'):
            return img

        img = img.convert('RGBA')
        background = Image.new('RGBA', img.size, (255, 255, 255))

        return Image.alpha_composite(background, img)

    img = Image.open(BytesIO(buffer))

    if img.format == 'GIF' and img.is_animated:
        return buffer

    width, height = img.size
    new_width, new_height = (360, 512)
    if width >= height:
        img = remove_alpha(img)

        new_ratio = new_height / new_width

        new_img = Image.new(img.mode, (width, int(width * new_ratio)), get_dominant_color(img))
        new_img.paste(img, (0, (int(width * new_ratio) - height) // 2))
        new_img.thumbnail((new_width, new_height), Image.LANCZOS)
    else:
        img.thumbnail((new_width, new_height), Image.LANCZOS)
        new_img = img

    new_buffer = BytesIO()
    new_img.convert('RGB').save(new_buffer, 'JPEG', quality=50)

    return new_buffer.getbuffer()


def folder_size(path):
    if not os.path.exists(path):
        return 0

    res = subprocess.run(['du', '-sh', path], stdout=subprocess.PIPE, check=False)

    return res.stdout.split()[0].decode()


@cache
def get_cache_dir():
    cache_dir_path = GLib.get_user_cache_dir()

    # Check if inside flatpak sandbox
    if is_flatpak():
        return cache_dir_path

    cache_dir_path = os.path.join(cache_dir_path, 'komikku')
    if not os.path.exists(cache_dir_path):
        os.mkdir(cache_dir_path)

    return cache_dir_path


@cache
def get_cached_data_dir():
    cached_data_dir_path = os.path.join(get_cache_dir(), 'tmp')
    if not os.path.exists(cached_data_dir_path):
        os.mkdir(cached_data_dir_path)

    return cached_data_dir_path


@cache
def get_data_dir():
    data_dir_path = GLib.get_user_data_dir()
    app_profile = Gio.Application.get_default().profile

    if not is_flatpak():
        base_path = data_dir_path
        data_dir_path = os.path.join(base_path, 'komikku')
        if app_profile == 'development':
            data_dir_path += '-devel'
        elif app_profile == 'beta':
            data_dir_path += '-beta'

        if not os.path.exists(data_dir_path):
            os.mkdir(data_dir_path)

            # Until version 0.11.0, data files (chapters, database) were stored in a wrong place
            from komikku.servers.utils import get_servers_list

            must_be_moved = ['komikku.db', 'komikku_backup.db', ]
            for server in get_servers_list(include_disabled=True):
                must_be_moved.append(server['id'])

            for name in must_be_moved:
                data_path = os.path.join(base_path, name)
                if os.path.exists(data_path):
                    os.rename(data_path, os.path.join(data_dir_path, name))

    # Create folder for 'local' server
    data_local_dir_path = os.path.join(data_dir_path, 'local')
    if not os.path.exists(data_local_dir_path):
        os.mkdir(data_local_dir_path)

    return data_dir_path


def html_escape(s):
    return html.escape(html.unescape(s), quote=False)


def if_network_available(func):
    """Decorator to disable an action when network is not avaibable"""

    @wraps(func)
    def wrapper(*args, **kwargs):

        window = args[0].parent if hasattr(args[0], 'parent') else args[0].window
        if not window.network_available:
            window.show_notification(_('You are currently offline'))
            return None

        return func(*args, **kwargs)

    return wrapper


def is_flatpak():
    return os.path.exists(os.path.join(GLib.get_user_runtime_dir(), 'flatpak-info'))


def log_error_traceback(e):
    from komikku.servers.exceptions import ServerException

    if isinstance(e, requests.exceptions.RequestException):
        return _('No Internet connection, timeout or server down')
    if isinstance(e, ServerException):
        return e.message

    logger.info(traceback.format_exc())

    return None


def skip_past(haystack, needle):
    if (idx := haystack.find(needle)) >= 0:
        return idx + len(needle)

    return None


def trunc_filename(filename):
    """Reduce filename length to 255 (common FS limit) if it's too long"""
    return filename.encode('utf-8')[:255].decode().strip()


class PaintablePixbuf(GObject.GObject, Gdk.Paintable):
    def __init__(self, path, pixbuf):
        super().__init__()

        self.cropped = False
        self.path = path
        self.pixbuf = pixbuf
        self.texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        self.texture_cropped = None

        self.orig_width = self.pixbuf.get_width()
        self.orig_height = self.pixbuf.get_height()
        self.width = self.orig_width
        self.height = self.orig_height

    @classmethod
    def new_from_data(cls, data, width=None, height=None, preserve_aspect_ratio=True):
        mime_type, _result_uncertain = Gio.content_type_guess(None, data)
        if not mime_type:
            return None

        try:
            stream = Gio.MemoryInputStream.new_from_data(data, None)

            if (not width and not height) or mime_type == 'image/gif':
                pixbuf = Pixbuf.new_from_stream(stream)
                if mime_type == 'image/gif':
                    if width == -1:
                        ratio = pixbuf.get_height() / height
                        width = pixbuf.get_width() / ratio
                    elif height == -1:
                        ratio = pixbuf.get_width() / width
                        height = pixbuf.get_height() / ratio

                    pixbuf = pixbuf.scale_simple(width, height, InterpType.BILINEAR)
            else:
                pixbuf = Pixbuf.new_from_stream_at_scale(stream, width, height, preserve_aspect_ratio)

            stream.close()
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(None, pixbuf)

    @classmethod
    def new_from_file(cls, path, width=None, height=None, preserve_aspect_ratio=True):
        format_, orig_width, orig_height = Pixbuf.get_file_info(path)
        if format_ is None:
            return None

        try:
            if (not width and not height) or 'image/gif' in format_.get_mime_types():
                pixbuf = Pixbuf.new_from_file(path)
                if 'image/gif' in format_.get_mime_types():
                    if width == -1:
                        ratio = orig_height / height
                        width = orig_width / ratio
                    elif height == -1:
                        ratio = orig_width / width
                        height = orig_height / ratio

                    pixbuf = pixbuf.scale_simple(width, height, InterpType.BILINEAR)
            else:
                pixbuf = Pixbuf.new_from_file_at_scale(path, width, height, preserve_aspect_ratio)
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(path, pixbuf)

    @classmethod
    def new_from_pixbuf(cls, pixbuf, width=None, height=None):
        if width and height:
            pixbuf = pixbuf.scale_simple(width, height, InterpType.BILINEAR)
        return cls(None, pixbuf)

    @classmethod
    def new_from_resource(cls, path, width=None, height=None, preserve_aspect_ratio=True):
        try:
            if not width and not height:
                pixbuf = Pixbuf.new_from_resource(path)
            else:
                pixbuf = Pixbuf.new_from_resource_at_scale(path, width, height, preserve_aspect_ratio)
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(None, pixbuf)

    def _compute_borders_crop_bbox(self):
        # TODO: Add a slider in settings
        threshold = 225

        def lookup(x):
            return 255 if x > threshold else 0

        im = Image.open(self.path).convert('L').point(lookup, mode='1')
        bg = Image.new(im.mode, im.size, 255)

        return ImageChops.difference(im, bg).getbbox()

    def dispose(self):
        self.pixbuf = None
        self.texture = None
        self.texture_cropped = None

    def do_get_intrinsic_height(self):
        return self.height

    def do_get_intrinsic_width(self):
        return self.width

    def do_snapshot(self, snapshot, width, height):
        def crop_borders():
            """"Crop white borders"""
            if self.path is None:
                return self.pixbuf

            bbox = self._compute_borders_crop_bbox()

            # Crop is possible if computed bbox is included in pixbuf
            if bbox is not None and (bbox[2] - bbox[0] < self.orig_width or bbox[3] - bbox[1] < self.orig_height):
                return crop_pixbuf(self.pixbuf, bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])

            return self.pixbuf

        if self.cropped and self.texture_cropped is None:
            self.texture_cropped = Gdk.Texture.new_for_pixbuf(crop_borders())

        if self.cropped:
            self.texture_cropped.snapshot(snapshot, width, height)
        else:
            self.texture.snapshot(snapshot, width, height)

    def resize(self, width, height, cropped=False):
        self.width = width
        self.height = height
        self.cropped = cropped

        self.invalidate_size()


class PaintablePixbufAnimation(GObject.GObject, Gdk.Paintable):
    def __init__(self, path, anim, width, height):
        super().__init__()

        self.anim = anim
        self.iter = self.anim.get_iter(None)
        self.path = path

        self.orig_width = self.anim.get_width()
        self.orig_height = self.anim.get_height()
        if width == -1:
            ratio = self.orig_height / height
            self.width = self.orig_width / ratio
            self.height = height
        elif height == -1:
            ratio = self.orig_width / width
            self.height = self.orig_height / ratio
            self.width = width
        else:
            self.width = width
            self.height = height

        self.__delay_cb()

    @classmethod
    def new_from_data(cls, data):
        stream = Gio.MemoryInputStream.new_from_data(data, None)
        anim = PixbufAnimation.new_from_stream(stream)
        stream.close()

        return cls(None, anim)

    @classmethod
    def new_from_file(cls, path, width=None, height=None):
        anim = PixbufAnimation.new_from_file(path)

        return cls(path, anim, width, height)

    def __delay_cb(self):
        if self.iter is None:
            return
        delay = self.iter.get_delay_time()
        if delay == -1:
            return
        self.timeout_id = GLib.timeout_add(delay, self.__delay_cb)

        self.invalidate_contents()

    def dispose(self):
        self.iter = None
        self.anim = None

    def do_get_intrinsic_height(self):
        return self.height

    def do_get_intrinsic_width(self):
        return self.width

    def do_snapshot(self, snapshot, width, height):
        _res, timeval = GLib.TimeVal.from_iso8601(datetime.datetime.utcnow().isoformat())
        self.iter.advance(timeval)
        pixbuf = self.iter.get_pixbuf()
        pixbuf = pixbuf.scale_simple(width, height, InterpType.BILINEAR)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        texture.snapshot(snapshot, width, height)

    def resize(self, width, height):
        self.width = width
        self.height = height

        self.invalidate_size()


class Picture(Gtk.Picture):
    def __init__(self, paintable):
        super().__init__()

        self.set_can_shrink(False)
        self.set_paintable(paintable)

    @classmethod
    def new_from_data(cls, data):
        if paintable := PaintablePixbuf.new_from_data(data):
            return cls(paintable)
        return None

    @classmethod
    def new_from_file(cls, path):
        if paintable := PaintablePixbuf.new_from_file(path):
            return cls(paintable)
        return None

    @classmethod
    def new_from_pixbuf(cls, pixbuf):
        if paintable := PaintablePixbuf.new_from_pixbuf(pixbuf):
            return cls(paintable)
        return None

    @classmethod
    def new_from_resource(cls, path):
        if paintable := PaintablePixbuf.new_from_resource(path):
            return cls(paintable)
        return None

    @property
    def height(self):
        return self.props.paintable.height

    @property
    def orig_height(self):
        return self.props.paintable.orig_height

    @property
    def orig_width(self):
        return self.props.paintable.orig_width

    @property
    def width(self):
        return self.props.paintable.width

    def dispose(self):
        paintable = self.get_paintable()
        self.set_paintable(None)
        paintable.dispose()

    def resize(self, width, height, cropped=False):
        self.props.paintable.resize(width, height, cropped)


class PictureAnimation(Gtk.Picture):
    def __init__(self, paintable):
        super().__init__()

        self.set_can_shrink(False)
        self.set_paintable(paintable)

    @classmethod
    def new_from_data(cls, data):
        if paintable := PaintablePixbufAnimation.new_from_data(data):
            return cls(paintable)
        return None

    @classmethod
    def new_from_file(cls, path):
        if paintable := PaintablePixbufAnimation.new_from_file(path):
            return cls(paintable)
        return None

    @property
    def height(self):
        return self.props.paintable.height

    @property
    def orig_height(self):
        return self.props.paintable.orig_height

    @property
    def orig_width(self):
        return self.props.paintable.orig_width

    @property
    def width(self):
        return self.props.paintable.width

    def dispose(self):
        paintable = self.get_paintable()
        self.set_paintable(None)
        paintable.dispose()

    def resize(self, width, height, _cropped=False):
        self.props.paintable.resize(width, height)
