# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from komikku.activity_indicator import ActivityIndicator
from komikku.reader.pager.image import KImage
from komikku.utils import log_error_traceback


class Page(Gtk.Overlay):
    __gtype_name__ = 'Page'
    __gsignals__ = {
        'rendered': (GObject.SignalFlags.RUN_FIRST, None, (bool, bool, )),
    }

    def __init__(self, pager, chapter, index):
        super().__init__(hexpand=True, vexpand=True)

        self.pager = pager
        self.reader = pager.reader
        self.window = self.reader.window

        self.chapter = self.init_chapter = chapter
        self.data = None
        self.index = self.init_index = index
        self.path = None
        self.picture = None
        self.retry_button = None

        self._status = None    # rendering, allocable, rendered, offlimit, disposed
        self.error = None      # connection error, server error, corrupt file error
        self.loadable = False  # loadable from disk or downloadable from server (chapter pages are known)

        if self.reader.reading_mode != 'webtoon':
            self.scrollable = True
            self.scrolledwindow = Gtk.ScrolledWindow()
            self.scrolledwindow.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            self.scrolledwindow.set_kinetic_scrolling(True)
            self.scrolledwindow.set_overlay_scrolling(True)

            self.set_child(self.scrolledwindow)
        else:
            self.scrollable = False

        # Activity indicator
        self.activity_indicator = ActivityIndicator()
        self.add_overlay(self.activity_indicator)

    @property
    def height(self):
        return self.get_allocation().height

    @property
    def is_hscrollable(self):
        if self.scrollable:
            adj = self.scrolledwindow.get_hadjustment()
            return adj.props.upper > adj.props.page_size

        return False

    @property
    def is_scrollable(self):
        return self.is_hscrollable or self.is_vscrollable

    @property
    def is_vscrollable(self):
        if self.scrollable:
            adj = self.scrolledwindow.get_vadjustment()
            return adj.props.upper > adj.props.page_size

        return False

    @GObject.Property(type=str)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    def dispose(self):
        self.status = 'disposed'

        if self.picture:
            self.picture.dispose()

        if self.reader.reading_mode != 'webtoon':
            self.get_parent().remove(self)
        else:
            self.unparent()

    def on_button_retry_clicked(self, _button):
        self.chapter = self.init_chapter
        self.index = self.init_index

        self.retry_button.set_visible(False)

        self.render(retry=True)

    def on_clicked(self, _picture, x, y):
        self.reader.pager.on_single_click(x, y)

    def on_rendered(self, _picture, update, retry):
        self.status = 'rendered'
        self.emit('rendered', update, retry)

    def on_zoom_begin(self, _picture):
        self.reader.pager.interactive = False
        self.reader.toggle_controls(False)

    def on_zoom_end(self, _picture):
        self.reader.pager.interactive = True

    def render(self, retry=False):
        def complete(error_code, error_message):
            if self.reader.reading_mode != 'webtoon':
                self.activity_indicator.stop()

            if error_code in ('connection', 'server'):
                on_error(error_code, error_message)
                if retry:
                    return
            elif error_code == 'offlimit':
                self.status = 'offlimit'
                return

            if self.status == 'disposed':
                # Page has been removed from pager
                return False

            self.set_image(retry)

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

        if self.reader.reading_mode != 'webtoon':
            self.activity_indicator.start()

        if self.reader.manga.server_id != 'local':
            thread = threading.Thread(target=run)
            thread.daemon = True
            thread.start()
        else:
            run()

    def rescale(self):
        if self.picture is None:
            return

        self.picture.scaling = self.reader.scaling
        self.picture.landscape_zoom = self.reader.landscape_zoom

    def set_allow_zooming(self, allow):
        if self.reader.reading_mode == 'webtoon':
            return

        if self.picture is None:
            return

        self.picture.set_allow_zooming(allow)

    def set_image(self, retry=False):
        if self.path is None and self.data is None:
            picture = KImage.new_from_resource('/info/febvre/Komikku/images/missing_file.png')
        else:
            can_zoom = self.scrollable
            if self.path:
                picture = KImage.new_from_file(
                    self.path, self.reader.scaling, self.reader.borders_crop, self.reader.landscape_zoom, can_zoom
                )
            else:
                picture = KImage.new_from_data(
                    self.data['buffer'], self.reader.scaling, self.reader.borders_crop, self.reader.landscape_zoom, can_zoom
                )

            if picture is None:
                GLib.unlink(self.path)

                self.show_retry_button()
                self.window.show_notification(_('Failed to load image'), 2)

                self.error = 'corrupt_file'
                picture = KImage.new_from_resource('/info/febvre/Komikku/images/missing_file.png')

        picture.connect('clicked', self.on_clicked)
        picture.connect('rendered', self.on_rendered, retry)
        picture.connect('zoom-begin', self.on_zoom_begin)
        picture.connect('zoom-end', self.on_zoom_end)

        if self.picture:
            self.picture.dispose()

        self.picture = picture
        self.status = 'allocable'
        if self.scrollable:
            self.scrolledwindow.set_child(self.picture)
        else:
            self.set_child(self.picture)

    def show_retry_button(self):
        if self.retry_button is None:
            self.retry_button = Gtk.Button()
            self.retry_button.add_css_class('suggested-action')
            self.retry_button.set_valign(Gtk.Align.CENTER)
            self.retry_button.set_halign(Gtk.Align.CENTER)
            self.retry_button.connect('clicked', self.on_button_retry_clicked)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            icon = Gtk.Image.new_from_icon_name('view-refresh-symbolic')
            icon.set_icon_size(Gtk.IconSize.LARGE)
            vbox.append(icon)
            vbox.append(Gtk.Label(label=_('Retry')))
            self.retry_button.set_child(vbox)

            self.add_overlay(self.retry_button)

        self.retry_button.set_visible(True)
