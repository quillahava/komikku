# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository.GdkPixbuf import PixbufAnimation

from komikku.activity_indicator import ActivityIndicator
from komikku.utils import create_cairo_surface_from_pixbuf
from komikku.utils import crop_pixbuf
from komikku.utils import Imagebuf
from komikku.utils import log_error_traceback


class Page(Gtk.ScrolledWindow):
    __gsignals__ = {
        'rendered': (GObject.SIGNAL_RUN_FIRST, None, (bool, )),
    }

    def __init__(self, pager, chapter, index):
        super().__init__()

        self.pager = pager
        self.reader = pager.reader
        self.window = self.reader.window

        self.chapter = chapter
        self.index = index
        self.path = None

        self._status = None    # rendering, render, rendered, offlimit, cleaned
        self.error = None      # connection error, server error or corrupt file error
        self.loadable = False  # loadable from disk or downloadable from server (chapter pages are known)
        self.cropped = False

        policy_type = Gtk.PolicyType.AUTOMATIC if self.reader.reading_mode != 'webtoon' else Gtk.PolicyType.NEVER
        self.set_policy(policy_type, policy_type)

        self.overlay = Gtk.Overlay()
        self.props.can_target = True
        self.props.hexpand = True
        self.props.vexpand = True
        self.set_child(self.overlay)

        self.image = Gtk.Picture()
        self.image.set_can_shrink(False)
        self.imagebuf = None
        self.overlay.set_child(self.image)

        # Activity indicator
        self.activity_indicator = ActivityIndicator()
        self.overlay.add_overlay(self.activity_indicator)

    @GObject.Property(type=str)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def animated(self):
        return self.imagebuf.animated

    @property
    def loaded(self):
        return self.pixbuf is not None

    def clean(self):
        if self.status is None:
            return

        self.status = 'cleaned'
        self.loadable = False
        self.imagebuf = None

    def on_button_retry_clicked(self, button):
        self.overlay.remove_overlay(button)
        self.render(retry=True)

    def render(self, retry=False):
        def complete(error_code, error_message):
            self.activity_indicator.stop()

            if error_code == 'server':
                on_error('server')
            elif error_code == 'connection':
                on_error('connection', error_message)
            elif error_code == 'offlimit':
                self.status = 'offlimit'
                return

            if self.status == 'cleaned' or self.get_parent() is None:
                # Page has been removed from pager
                return False

            self.status = 'render'
            self.set_image()
            self.status = 'rendered'
            self.emit('rendered', retry)

            return False

        def load_chapter(prior_chapter=None):
            if self.chapter is None:
                return 'error', 'offlimit', None

            if self.chapter.pages and self.index >= 0 and self.index < len(self.chapter.pages):
                return 'success', None, None

            if self.index < 0:
                # Page belongs to another (previous) chapter
                self.chapter = self.reader.manga.get_next_chapter(self.chapter, -1)
                if self.chapter is None:
                    return 'error', 'offlimit', None

            if not self.chapter.pages:
                try:
                    if not self.chapter.update_full():
                        return 'error', 'server', None
                except Exception as e:
                    return 'error', 'connection', log_error_traceback(e)

            if self.index > len(self.chapter.pages) - 1:
                # Page belongs to another (next) chapter
                prior_chapter = self.chapter
                self.chapter = self.reader.manga.get_next_chapter(self.chapter, 1)
                if self.chapter is None:
                    return 'error', 'offlimit', None

            if self.index < 0:
                self.index = len(self.chapter.pages) + self.index
            elif self.index > len(prior_chapter.pages if prior_chapter else self.chapter.pages) - 1:
                self.index = self.index - len(prior_chapter.pages)

            return load_chapter(prior_chapter)

        def on_error(kind, message=None):
            assert kind in ('connection', 'server', ), 'Invalid error kind'

            if message is not None:
                self.window.show_notification(message, 2)

            self.error = kind

            self.show_retry_button()

        def run():
            res, error_code, error_message = load_chapter()
            if res == 'error':
                GLib.idle_add(complete, error_code, error_message)
                return

            self.loadable = True

            page_path = self.chapter.get_page_path(self.index)
            if page_path is None:
                try:
                    page_path = self.chapter.get_page(self.index)
                    if page_path:
                        self.path = page_path
                    else:
                        error_code, error_message = 'server', None
                        on_error('server')
                except Exception as e:
                    error_code, error_message = 'connection', log_error_traceback(e)
            else:
                self.path = page_path

            GLib.idle_add(complete, error_code, error_message)

        if self.status is not None and self.error is None:
            return

        self.imagebuf = None
        self.status = 'rendering'
        self.error = None

        self.activity_indicator.start()

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def rescale(self):
        if self.status == 'rendered':
            self.set_image()

    def resize(self):
        if self.status == 'rendered':
            self.set_image()

    def set_image(self, crop=None):
        if self.imagebuf is None:
            if self.path is None:
                self.imagebuf = Imagebuf.new_from_resource('/info/febvre/Komikku/images/missing_file.png')
            else:
                self.imagebuf = Imagebuf.new_from_file(self.path)
                if self.imagebuf is None:
                    GLib.unlink(self.path)

                    self.show_retry_button()
                    self.window.show_notification(_('Failed to load image'), 2)

                    self.error = 'corrupt_file'
                    self.imagebuf = Imagebuf.new_from_resource('/info/febvre/Komikku/images/missing_file.png')

        # Crop image borders
        imagebuf = self.imagebuf.crop_borders() if self.reader.manga.borders_crop == 1 else self.imagebuf

        # Adjust image
        scaling = self.reader.scaling if self.reader.reading_mode != 'webtoon' else 'width'
        if self.reader.scaling != 'original':
            adapt_to_width_height = imagebuf.height / (imagebuf.width / self.reader.size.width)
            adapt_to_height_width = imagebuf.width / (imagebuf.height / self.reader.size.height)

            if not self.animated:
                if scaling == 'width' or (scaling == 'screen' and adapt_to_width_height <= self.reader.size.height):
                    # Adapt image to width
                    pixbuf = imagebuf.get_scaled_pixbuf(self.reader.size.width, adapt_to_width_height, False, self.window.hidpi_scale)
                elif scaling == 'height' or (scaling == 'screen' and adapt_to_height_width <= self.reader.size.width):
                    # Adapt image to height
                    pixbuf = imagebuf.get_scaled_pixbuf(adapt_to_height_width, self.reader.size.height, False, self.window.hidpi_scale)
            else:
                # NOTE: Special case of animated images (GIF)
                # They cannot be cropped, which would prevent navigation by 2-finger swipe gesture
                # Moreover, it's more comfortable to view them in their entirety (fit viewport)

                if adapt_to_width_height <= self.reader.size.height:
                    # Adapt image to width
                    pixbuf = imagebuf.get_scaled_pixbuf(self.reader.size.width, adapt_to_width_height, False, self.window.hidpi_scale)
                elif adapt_to_height_width <= self.reader.size.width:
                    # Adapt image to height
                    pixbuf = imagebuf.get_scaled_pixbuf(adapt_to_height_width, self.reader.size.height, False, self.window.hidpi_scale)
        else:
            pixbuf = imagebuf.get_pixbuf()

        if crop is not None:
            # The 'crop' argument allows the image to be cropped to keep only its visible part
            # Used during 2-fingers swipe gestures to disable Gtk.Scrolledwindow scrolling
            if crop in ('right', 'bottom'):
                pixbuf = crop_pixbuf(
                    pixbuf,
                    0, 0,
                    self.reader.size.width * self.window.hidpi_scale, self.reader.size.height * self.window.hidpi_scale
                )
            elif crop == 'left':
                pixbuf = crop_pixbuf(
                    pixbuf,
                    pixbuf.get_width() - self.reader.size.width * self.window.hidpi_scale, 0,
                    self.reader.size.width * self.window.hidpi_scale, self.reader.size.height * self.window.hidpi_scale
                )
            elif crop == 'top':
                pixbuf = crop_pixbuf(
                    pixbuf,
                    0, pixbuf.get_height() - self.reader.size.height * self.window.hidpi_scale,
                    self.reader.size.width * self.window.hidpi_scale, self.reader.size.height * self.window.hidpi_scale
                )
            self.cropped = True
        else:
            self.cropped = False

        if isinstance(pixbuf, PixbufAnimation):
            self.image.set_from_animation(pixbuf)
        else:
            if self.window.hidpi_scale != 1:
                surface = create_cairo_surface_from_pixbuf(pixbuf, self.window.hidpi_scale)
                self.image.set_from_surface(surface)
            else:
                self.image.set_pixbuf(pixbuf)

        if self.reader.reading_mode == 'webtoon':
            self.set_size_request(pixbuf.get_width() / self.window.hidpi_scale, pixbuf.get_height() / self.window.hidpi_scale)

    def show_retry_button(self):
        btn = Gtk.Button()
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect('clicked', self.on_button_retry_clicked)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        icon = Gtk.Image.new_from_icon_name('view-refresh-symbolic')
        icon.set_icon_size(Gtk.IconSize.LARGE)
        vbox.append(icon)
        vbox.append(Gtk.Label(label=_('Retry')))
        btn.set_child(vbox)

        self.overlay.add_overlay(btn)
