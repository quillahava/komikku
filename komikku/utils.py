# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from contextlib import closing
import datetime
from functools import lru_cache
from functools import wraps
from gettext import gettext as _
import gi
import html
import json
import keyring
from keyring.credentials import Credential
import logging
import math
import os
from PIL import Image
from PIL import ImageChops
import requests
import subprocess
import traceback

gi.require_version('Gdk', '4.0')
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

keyring.core.init_backend()

logger = logging.getLogger('komikku')


def create_picture_from_file(path, static_animation=False, subdivided=False):
    format, _width, _height = Pixbuf.get_file_info(path)
    if format is None:
        return None

    if 'image/gif' in format.get_mime_types() and not static_animation:
        return PictureAnimation.new_from_file(path)
    elif subdivided:
        return PictureSubdivided.new_from_file(path)
    else:
        return Picture.new_from_file(path)


def create_picture_from_resource(path):
    return Picture.new_from_resource(path)


def create_paintable_from_data(data, width=None, height=None, static_animation=False):
    mime_type, _result_uncertain = Gio.content_type_guess(None, data)
    if not mime_type:
        return None

    if mime_type == 'image/gif' and not static_animation:
        return PaintablePixbufAnimation.new_from_data(data)
    else:
        return PaintablePixbuf.new_from_data(data, width, height)


def create_paintable_from_file(path, width=None, height=None, static_animation=False):
    format, _width, _height = Pixbuf.get_file_info(path)
    if format is None:
        return None

    if 'image/gif' in format.get_mime_types() and not static_animation:
        return PaintablePixbufAnimation.new_from_file(path, width, height)
    else:
        return PaintablePixbuf.new_from_file(path, width, height)


def create_paintable_from_resource(path, width=None, height=None):
    return PaintablePixbuf.new_from_resource(path, width, height)


def crop_pixbuf(pixbuf, src_x, src_y, width, height):
    pixbuf_cropped = Pixbuf.new(Colorspace.RGB, pixbuf.get_has_alpha(), 8, width, height)
    pixbuf.copy_area(src_x, src_y, width, height, pixbuf_cropped, 0, 0)

    return pixbuf_cropped


def folder_size(path):
    if not os.path.exists(path):
        return 0

    res = subprocess.run(['du', '-sh', path], stdout=subprocess.PIPE, check=False)

    return res.stdout.split()[0].decode()


@lru_cache(maxsize=None)
def get_cache_dir():
    cache_dir_path = GLib.get_user_cache_dir()

    # Check if inside flatpak sandbox
    if is_flatpak():
        return cache_dir_path

    cache_dir_path = os.path.join(cache_dir_path, 'komikku')
    if not os.path.exists(cache_dir_path):
        os.mkdir(cache_dir_path)

    return cache_dir_path


@lru_cache(maxsize=None)
def get_data_dir():
    data_dir_path = GLib.get_user_data_dir()

    # Check if inside flatpak sandbox
    if is_flatpak():
        return data_dir_path

    base_path = data_dir_path
    data_dir_path = os.path.join(base_path, 'komikku')
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
    elif isinstance(e, ServerException):
        return e.message

    logger.info(traceback.format_exc())

    return None


def skip_past(haystack, needle):
    if (idx := haystack.find(needle)) >= 0:
        return idx + len(needle)

    return None


def subdivide_pixbuf(pixbuf, part_height):
    """Sub-divide a long vertical GdkPixbuf.Pixbuf into multiple GdkPixbuf.Pixbuf"""
    parts = []

    width = pixbuf.get_width()
    full_height = pixbuf.get_height()

    for index in range(math.ceil(full_height / part_height)):
        y = index * part_height
        height = part_height if y + part_height <= full_height else full_height - y

        part_pixbuf = Pixbuf.new(Colorspace.RGB, pixbuf.get_has_alpha(), 8, width, height)
        pixbuf.copy_area(0, y, width, height, part_pixbuf, 0, 0)
        parts.append(part_pixbuf)

    return parts


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
    def new_from_data(cls, data, width=None, height=None):
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
                pixbuf = Pixbuf.new_from_stream_at_scale(stream, width, height, True)

            stream.close()
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(None, pixbuf)

    @classmethod
    def new_from_file(cls, path, width=None, height=None):
        format, orig_width, orig_height = Pixbuf.get_file_info(path)
        if format is None:
            return None

        try:
            if (not width and not height) or 'image/gif' in format.get_mime_types():
                pixbuf = Pixbuf.new_from_file(path)
                if 'image/gif' in format.get_mime_types():
                    if width == -1:
                        ratio = orig_height / height
                        width = orig_width / ratio
                    elif height == -1:
                        ratio = orig_width / width
                        height = orig_height / ratio

                    pixbuf = pixbuf.scale_simple(width, height, InterpType.BILINEAR)
            else:
                pixbuf = Pixbuf.new_from_file_at_scale(path, width, height, True)
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
    def new_from_resource(cls, path, width=None, height=None):
        try:
            if not width and not height:
                pixbuf = Pixbuf.new_from_resource(path)
            else:
                pixbuf = Pixbuf.new_from_resource_at_scale(path, width, height, True)
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
            if bbox[2] - bbox[0] < self.orig_width or bbox[3] - bbox[1] < self.orig_height:
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
        delay = self.iter.get_delay_time()
        if delay == -1:
            return
        self.timeout_id = GLib.timeout_add(delay, self.__delay_cb)

        self.invalidate_contents()

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
        self.height = width

        self.invalidate_size()


class Picture(Gtk.Picture):
    def __init__(self, pixbuf):
        super().__init__()

        self.set_can_shrink(False)
        self.set_keep_aspect_ratio(True)

        self.set_paintable(pixbuf)

    @classmethod
    def new_from_data(cls, data):
        return cls(PaintablePixbuf.new_from_data(data))

    @classmethod
    def new_from_file(cls, path):
        return cls(PaintablePixbuf.new_from_file(path))

    @classmethod
    def new_from_pixbuf(cls, pixbuf):
        return cls(PaintablePixbuf.new_from_pixbuf(None))

    @classmethod
    def new_from_resource(cls, path):
        return cls(PaintablePixbuf.new_from_resource(path))

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

    def resize(self, width, height, cropped=False):
        self.props.paintable.resize(width, height, cropped)


class PictureAnimation(Gtk.Picture):
    def __init__(self, pixbuf):
        super().__init__()

        self.set_can_shrink(False)
        self.set_keep_aspect_ratio(True)

        self.set_paintable(pixbuf)

    @classmethod
    def new_from_data(cls, data):
        return cls(PaintablePixbufAnimation.new_from_data(data))

    @classmethod
    def new_from_file(cls, path):
        return cls(PaintablePixbufAnimation.new_from_file(path))

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

    def resize(self, width, height, _cropped=False):
        self.props.paintable.resize(width, height)


class PictureSubdivided(Gtk.Box):
    """
    A Gtk.Box containing an image subdivided into multiple Gtk.Picture.

    Useful to display long vertical images commonly used in Webtoons
    because images height are limited by GL_MAX_TEXTURE_SIZE.
    """

    def __init__(self, path, pixbuf):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.path = path
        # Pages of Webtoon pager have a minimum size (equal to reader view size)
        # In rare cases where an image is smaller than page, it must be centered vertically
        self.props.valign = Gtk.Align.CENTER

        # TODO: find a way to replace 4096 by GL_MAX_TEXTURE_SIZE value
        for pixbuf_tile in subdivide_pixbuf(pixbuf, 4096):
            picture = Gtk.Picture()
            picture.set_pixbuf(pixbuf_tile)
            picture.set_can_shrink(True)
            self.append(picture)

        self.orig_width = pixbuf.get_width()
        self.orig_height = pixbuf.get_height()

    @classmethod
    def new_from_file(cls, path):
        return cls(path, Pixbuf.new_from_file(path))

    def resize(self, width, height, _cropped=False):
        self.set_size_request(width, height)


class CustomCredential(Credential):
    """Custom credentials implementation with an additional 'address' attribute"""

    def __init__(self, username, password, address=None):
        self._username = username
        self._password = password
        self._address = address

    @property
    def address(self):
        return self._address

    @property
    def password(self):
        return self._password

    @property
    def username(self):
        return self._username


class KeyringHelper:
    """Simple helper to store servers accounts credentials using Python keyring library"""

    appid = 'info.febvre.Komikku'

    def __init__(self, fallback_keyring='plaintext'):
        if not self.is_disabled and not self.has_recommended_backend:
            if fallback_keyring == 'plaintext':
                keyring.set_keyring(PlaintextKeyring())

    @property
    def has_recommended_backend(self):
        return self.keyring is not None and not isinstance(self.keyring, keyring.backends.fail.Keyring)

    @property
    def is_disabled(self):
        return hasattr(keyring.backends, 'null') and isinstance(self.keyring, keyring.backends.null.Keyring)

    @property
    def keyring(self):
        current_keyring_backend = keyring.get_keyring()

        if isinstance(current_keyring_backend, keyring.backends.chainer.ChainerBackend):
            # Search SecretService backend
            for backend in current_keyring_backend.backends:
                if isinstance(backend, keyring.backends.SecretService.Keyring):
                    return backend

            return None

        return current_keyring_backend

    def get(self, service):
        if self.is_disabled:
            return None

        if isinstance(self.keyring, keyring.backends.SecretService.Keyring):
            collection = self.keyring.get_preferred_collection()

            credential = None
            with closing(collection.connection):
                items = collection.search_items({'service': service})
                for item in items:
                    self.keyring.unlock(item)
                    username = item.get_attributes().get('username')
                    if username is None:
                        # Try to find username in 'login' attribute instead of 'username'
                        # Backward compatibility with the previous implementation which used libsecret
                        username = item.get_attributes().get('login')
                    if username:
                        credential = CustomCredential(username, item.get_secret().decode('utf-8'), item.get_attributes().get('address'))
        else:
            # Fallback on PlaintextKeyring
            credential = self.keyring.get_credential(service, None)

        if credential is None or credential.username is None:
            return None

        return credential

    def store(self, service, username, password, address=None):
        if self.is_disabled:
            return

        if isinstance(self.keyring, keyring.backends.SecretService.Keyring):
            # At this time, SecretService is the only backend that support a collection of items with arbitrary attributes
            # Known working implementations are:
            # - GNOME Keyring
            # - KeePassXC Secret Service integration (tested, work well)

            # Freedesktop.org Secret Service specification was written by both GNOME and KDE projects together
            # but it’s supported by the GNOME Keyring only
            # ksecretservice (https://community.kde.org/KDE_Utils/ksecretsservice) exists but is unfinished and seems unmaintained

            collection = self.keyring.get_preferred_collection()

            label = f'{self.appid}: {username}@{service}'
            attributes = {
                'application': self.appid,
                'service': service,
                'username': username,
            }
            if address is not None:
                attributes['address'] = address

            with closing(collection.connection):
                # Delete previous credential if exists
                items = collection.search_items({'service': service})
                for item in items:
                    item.delete()

                collection.create_item(label, attributes, password)
        else:
            # Fallback on PlaintextKeyring
            self.keyring.set_password(service, username, password, address)


class PlaintextKeyring(keyring.backend.KeyringBackend):
    """Simple File Keyring with no encryption

    Used as fallback when no Keyring backend is found
    """

    priority = 1

    def __init__(self):
        super().__init__()

    @property
    def filename(self):
        return os.path.join(self.folder, 'plaintext.keyring')

    @property
    def folder(self):
        return os.path.join(get_data_dir(), 'keyrings')

    def _read(self):
        if not os.path.exists(self.filename):
            return {}

        with open(self.filename, 'r') as fp:
            return json.load(fp)

    def _save(self, data):
        if not os.path.exists(self.folder):
            os.mkdir(self.folder)

        with open(self.filename, 'w+') as fp:
            return json.dump(data, fp, indent=2)

    def get_credential(self, service, username):
        data = self._read()
        if service in data:
            return CustomCredential(data[service]['username'], data[service]['password'], data[service].get('address'))
        return None

    def get_password(self, service, username):
        pass

    def set_password(self, service, username, password, address=None):
        data = self._read()
        data[service] = dict(
            username=username,
            password=password,
        )
        if address is not None:
            data[service]['address'] = address
        self._save(data)
