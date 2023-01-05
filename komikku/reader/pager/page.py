# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from komikku.activity_indicator import ActivityIndicator
from komikku.utils import create_picture_from_data
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
        self.data = None
        self.index = self.init_index = index
        self.init_height = None
        self.path = None
        self.picture = None

        self._status = None    # rendering, rendered, offlimit, disposed
        self.error = None      # connection error, server error, corrupt file error
        self.loadable = False  # loadable from disk or downloadable from server (chapter pages are known)

        if self.reader.reading_mode == 'webtoon':
            # No Gtk.ScrolledWindow because it creates issues in pager
            self.scrolledwindow = None
            self.init_height = self.reader.size.height
            self.set_size_request(-1, self.init_height)
        else:
            self.scrolledwindow = Gtk.ScrolledWindow()
            self.scrolledwindow.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            self.scrolledwindow.set_kinetic_scrolling(True)
            self.scrolledwindow.set_overlay_scrolling(True)

            self.set_child(self.scrolledwindow)

        # Activity indicator
        self.activity_indicator = ActivityIndicator()
        self.add_overlay(self.activity_indicator)

    @property
    def animated(self):
        return isinstance(self.picture.get_paintable(), PaintablePixbufAnimation)

    @property
    def height(self):
        if self.reader.reading_mode == 'webtoon' and self.picture:
            return self.picture.height

        return self.get_allocation().height

    @property
    def hscrollable(self):
        adj = self.scrolledwindow.get_hadjustment()
        return adj.props.upper > adj.props.page_size

    @property
    def scrollable(self):
        return self.hscrollable or self.vscrollable

    @GObject.Property(type=str)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def vscrollable(self):
        adj = self.scrolledwindow.get_vadjustment()
        return adj.props.upper > adj.props.page_size

    def dispose(self):
        self.status = 'disposed'
        self.get_parent().remove(self)

    def on_button_retry_clicked(self, button):
        self.remove_overlay(button)

        self.chapter = self.init_chapter
        self.index = self.init_index
        self.picture = None

        self.render(retry=True)

    def render(self, retry=False):
        def complete(error_code, error_message):
            self.activity_indicator.stop()

            if error_code in ('connection', 'server'):
                on_error(error_code, error_message)
            elif error_code == 'offlimit':
                self.status = 'offlimit'
                return

            if self.status == 'disposed':
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

            if self.reader.manga.server_id != 'local':
                page_path = self.chapter.get_page_path(self.index)
                if page_path is None:
                    try:
                        page_path = self.chapter.get_page(self.index)
                        if page_path:
                            self.path = page_path
                        else:
                            error_code, error_message = 'server', None
                    except Exception as e:
                        error_code, error_message = 'connection', log_error_traceback(e)
                else:
                    self.path = page_path
            else:
                try:
                    self.data = self.chapter.get_page_data(self.index)
                except Exception as e:
                    error_code, error_message = 'server', log_error_traceback(e)

            GLib.idle_add(complete, error_code, error_message)

        if self.status is not None and self.error is None:
            return

        self.status = 'rendering'
        self.error = None

        self.activity_indicator.start()

        if self.reader.manga.server_id != 'local':
            thread = threading.Thread(target=run)
            thread.daemon = True
            thread.start()
        else:
            run()

    def rescale(self):
        if self.status == 'rendered':
            self.set_image()

    def resize(self):
        if self.status == 'rendered':
            self.set_image()

    def set_image(self, size=None):
        if self.picture is None:
            if self.path is None and self.data is None:
                picture = create_picture_from_resource('/info/febvre/Komikku/images/missing_file.png')
            else:
                if self.path:
                    picture = create_picture_from_file(self.path, subdivided=self.reader.reading_mode == 'webtoon')
                else:
                    picture = create_picture_from_data(self.data['buffer'], subdivided=self.reader.reading_mode == 'webtoon')

                if picture is None:
                    GLib.unlink(self.path)

                    self.show_retry_button()
                    self.window.show_notification(_('Failed to load image'), 2)

                    self.error = 'corrupt_file'
                    picture = create_picture_from_resource('/info/febvre/Komikku/images/missing_file.png')
        else:
            picture = self.picture

        if size is None:
            if self.reader.scaling != 'original':
                if self.reader.landscape_zoom and self.reader.scaling == 'screen' and picture.orig_width > picture.orig_height:
                    # When page is landscape and scaling is 'screen', scale/zoom page to fit height
                    scaling = 'height'
                else:
                    scaling = self.reader.scaling

                max_width = self.pager.size.width
                max_height = self.pager.size.height

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
            if self.reader.reading_mode == 'webtoon':
                self.set_child(picture)
            else:
                self.scrolledwindow.set_child(picture)

        # Determine if page can receive pointer events
        if not self.error:
            if self.reader.reading_mode == 'webtoon':
                self.props.can_target = False
            elif picture.width > self.pager.size.width or picture.height > self.pager.size.height:
                # Allows page to be scrollable
                self.scrolledwindow.props.can_target = True
                self.props.can_target = True
            else:
                self.scrolledwindow.props.can_target = False
                self.props.can_target = False
        else:
            # Allows `Retry` button to be clickable
            self.props.can_target = True
            if self.reader.reading_mode != 'webtoon':
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
