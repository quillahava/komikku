# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from functools import cache
from functools import wraps
from gettext import gettext as _
import gi
import html
from io import BytesIO
import logging
import os
from PIL import Image
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
from gi.repository import Graphene
from gi.repository import Gsk
from gi.repository.GdkPixbuf import PixbufAnimation

COVER_WIDTH = 180
COVER_HEIGHT = 256

logger = logging.getLogger('komikku')


def check_cmdline_tool(cmd):
    try:
        p = subprocess.Popen(cmd, bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        out, _ = p.communicate()
    except Exception:
        return False, None
    else:
        return p.returncode == 0, out.decode('utf-8').strip()


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
    new_width, new_height = (COVER_WIDTH, COVER_HEIGHT)
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
    new_img.convert('RGB').save(new_buffer, 'JPEG', quality=65)

    return new_buffer.getvalue()


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


class CoverLoader(GObject.GObject):
    __gtype_name__ = 'CoverLoader'

    def __init__(self, path, texture, pixbuf, width=None, height=None):
        super().__init__()

        self.texture = texture
        self.pixbuf = pixbuf

        if texture:
            self.orig_width = self.texture.get_width()
            self.orig_height = self.texture.get_height()
        else:
            self.orig_width = self.pixbuf.get_width()
            self.orig_height = self.pixbuf.get_height()

        # Compute size
        if width is None and height is None:
            self.width = self.orig_width
            self.height = self.orig_height
        elif width is None or height is None:
            ratio = self.orig_width / self.orig_height
            if width is None:
                self.width = int(height * ratio)
                self.height = height
            else:
                self.width = width
                self.height = int(width / ratio)
        else:
            self.width = width
            self.height = height

    @classmethod
    def new_from_data(cls, data, width=None, height=None, static_animation=False):
        mime_type, _result_uncertain = Gio.content_type_guess(None, data)
        if not mime_type:
            return None

        try:
            if mime_type == 'image/gif' and not static_animation:
                stream = Gio.MemoryInputStream.new_from_data(data, None)
                pixbuf = PixbufAnimation.new_from_stream(stream)
                stream.close()
                texture = None
            else:
                pixbuf = None
                texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(None, texture, pixbuf, width, height)

    @classmethod
    def new_from_file(cls, path, width=None, height=None, static_animation=False):
        mime_type, _result_uncertain = Gio.content_type_guess(path, None)
        if not mime_type:
            return None

        try:
            if mime_type == 'image/gif' and not static_animation:
                pixbuf = PixbufAnimation.new_from_file(path)
                texture = None
            else:
                pixbuf = None
                texture = Gdk.Texture.new_from_filename(path)
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(path, texture, pixbuf, width, height)

    @classmethod
    def new_from_resource(cls, path, width=None, height=None):
        try:
            texture = Gdk.Texture.new_from_resource(path)
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(None, texture, None, width, height)

    def dispose(self):
        self.texture = None
        self.pixbuf = None


class PaintableCover(CoverLoader, Gdk.Paintable):
    __gtype_name__ = 'PaintableCover'

    corners_radius = 8

    def __init__(self, path, texture, pixbuf, width=None, height=None):
        CoverLoader.__init__(self, path, texture, pixbuf, width, height)

        self.animation_iter = None
        self.animation_timeout_id = None

        self.rect = Graphene.Rect().alloc()
        self.rounded_rect = Gsk.RoundedRect()
        self.rounded_rect_size = Graphene.Size().alloc()
        self.rounded_rect_size.init(self.corners_radius, self.corners_radius)

        if isinstance(self.pixbuf, PixbufAnimation):
            self.animation_iter = self.pixbuf.get_iter(None)
            self.animation_timeout_id = GLib.timeout_add(self.animation_iter.get_delay_time(), self.on_delay)

            self.invalidate_contents()

    def dispose(self):
        CoverLoader.dispose()
        self.animation_iter = None

    def do_get_intrinsic_height(self):
        return self.height

    def do_get_intrinsic_width(self):
        return self.width

    def do_snapshot(self, snapshot, width, height):
        self.rect.init(0, 0, width, height)

        if self.animation_iter:
            # Get next frame (animated GIF)
            timeval = GLib.TimeVal()
            timeval.tv_usec = GLib.get_real_time()
            self.animation_iter.advance(timeval)
            pixbuf = self.animation_iter.get_pixbuf()
            self.texture = Gdk.Texture.new_for_pixbuf(pixbuf)

        # Append cover (rounded)
        self.rounded_rect.init(self.rect, self.rounded_rect_size, self.rounded_rect_size, self.rounded_rect_size, self.rounded_rect_size)
        snapshot.push_rounded_clip(self.rounded_rect)
        snapshot.append_texture(self.texture, self.rect)
        snapshot.pop()  # remove the clip

    def on_delay(self):
        if self.animation_iter is None:
            return GLib.SOURCE_REMOVE

        delay = self.animation_iter.get_delay_time()
        if delay == -1:
            return GLib.SOURCE_REMOVE

        self.timeout_id = GLib.timeout_add(delay, self.on_delay)

        self.invalidate_contents()

        return GLib.SOURCE_REMOVE
