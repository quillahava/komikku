# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from komikku.activity_indicator import ActivityIndicator
from komikku.utils import create_picture_from_file
from komikku.utils import create_picture_from_resource
from komikku.utils import log_error_traceback
from komikku.utils import PaintablePixbufAnimation


class Page(Gtk.Overlay):
    __gsignals__ = {
        'rendered': (GObject.SIGNAL_RUN_FIRST, None, (bool, )),
    }

    def __init__(self, pager, chapter, index):
        super().__init__(hexpand=True, vexpand=True)

        self.pager = pager
        self.reader = pager.reader
        self.window = self.reader.window

        self.chapter = self.init_chapter = chapter
        self.index = self.init_index = index
        self.init_height = None
        self.path = None

        self._status = None     # rendering, rendered, offlimit, cleaned
        self._error = None      # connection error, server error or corrupt file error
        self._loadable = False  # loadable from disk or downloadable from server (chapter pages are known)

        self.scrolledwindow = Gtk.ScrolledWindow()

        if self.reader.reading_mode == 'webtoon':
            self.scrolledwindow.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            self.init_height = self.reader.size.height
            self.set_size_request(-1, self.init_height)
        else:
            self.scrolledwindow.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            self.scrolledwindow.set_kinetic_scrolling(True)
            self.scrolledwindow.set_overlay_scrolling(True)

        self.set_child(self.scrolledwindow)

        self.picture = None

        # Activity indicator
        self.activity_indicator = ActivityIndicator()
        self.add_overlay(self.activity_indicator)

    @GObject.Property(type=str)
    def error(self):
        return self._error

    @error.setter
    def error(self, value):
        self._error = value

    @GObject.Property(type=float)
    def height(self):
        _minimal, natural = self.get_preferred_size()
        return natural.height

    @GObject.Property(type=bool, default=False)
    def loadable(self):
        return self._loadable

    @loadable.setter
    def loadable(self, value):
        self._loadable = value

    @GObject.Property(type=str)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def animated(self):
        return isinstance(self.picture.get_paintable(), PaintablePixbufAnimation)

    def clean(self):
        if self.status is None:
            return

        self.status = 'cleaned'
        self.loadable = False

    def on_button_retry_clicked(self, button):
        self.remove_overlay(button)

        self.chapter = self.init_chapter
        self.index = self.init_index
        self.picture = None

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

            if self.reader.reading_mode == 'webtoon' and not self.error:
                # Removed minimum size restriction except in case of error
                self.set_size_request(-1, -1)

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

    def set_image(self, size=None):
        if self.picture is None:
            if self.path is None:
                picture = create_picture_from_resource('/info/febvre/Komikku/images/missing_file.png')
            else:
                picture = create_picture_from_file(self.path, subdivided=self.reader.reading_mode == 'webtoon')
                if picture is None:
                    GLib.unlink(self.path)

                    self.show_retry_button()
                    self.window.show_notification(_('Failed to load image'), 2)

                    self.error = 'corrupt_file'
                    picture = create_picture_from_resource('/info/febvre/Komikku/images/missing_file.png')
        else:
            picture = self.picture

        if size is None:
            scaling = self.reader.scaling if self.reader.reading_mode != 'webtoon' else 'width'
            if self.reader.scaling != 'original':
                max_width = self.reader.size.width
                if self.reader.reading_mode == 'webtoon':
                    max_width = min(max_width, self.reader.pager.clamp_size)
                max_height = self.reader.size.height

                adapt_to_width_height = picture.orig_height // (picture.orig_width / max_width)
                adapt_to_height_width = picture.orig_width // (picture.orig_height / max_height)

                if scaling == 'width' or (scaling == 'screen' and adapt_to_width_height <= max_height):
                    # Adapt image to width
                    picture.resize(max_width, adapt_to_width_height, self.reader.manga.borders_crop)
                elif scaling == 'height' or (scaling == 'screen' and adapt_to_height_width <= max_width):
                    # Adapt image to height
                    picture.resize(adapt_to_height_width, max_height, self.reader.manga.borders_crop)
            else:
                picture.resize(picture.orig_width, picture.orig_height, cropped=self.reader.manga.borders_crop)
        else:
            picture.resize(size[0], size[1], cropped=self.reader.manga.borders_crop)

        if self.picture is None:
            self.picture = picture
            self.scrolledwindow.set_child(picture)

        # Determine if page can receive pointer events
        if not self.error:
            if self.reader.reading_mode == 'webtoon':
                self.scrolledwindow.props.can_target = False
                self.props.can_target = False
            elif picture.width > self.reader.size.width or picture.height > self.reader.size.height:
                # Allows page to be scrollable
                self.scrolledwindow.props.can_target = True
                self.props.can_target = True
            else:
                self.scrolledwindow.props.can_target = False
                self.props.can_target = False
        else:
            # Allows `Retry` button to be clickable
            self.props.can_target = True
            self.scrolledwindow.props.can_target = False

    def show_retry_button(self):
        btn = Gtk.Button()
        btn.add_css_class('suggested-action')
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect('clicked', self.on_button_retry_clicked)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        icon = Gtk.Image.new_from_icon_name('view-refresh-symbolic')
        icon.set_icon_size(Gtk.IconSize.LARGE)
        vbox.append(icon)
        vbox.append(Gtk.Label(label=_('Retry')))
        btn.set_child(vbox)

        self.add_overlay(btn)
