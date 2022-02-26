# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from abc import abstractmethod
import datetime
from gettext import gettext as _
import threading

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository.GdkPixbuf import InterpType

from komikku.reader.pager.page import Page
from komikku.utils import create_cairo_surface_from_pixbuf
from komikku.utils import log_error_traceback


class BasePager:
    btn_press_handler_id = None
    btn_press_timeout_id = None
    key_press_handler_id = None
    default_double_click_time = Gtk.Settings.get_default().get_property('gtk-double-click-time')
    zoom = dict(active=False)

    def __init__(self, reader):
        self.reader = reader
        self.window = reader.window

        # Controller to track pointer motion: used to hide pointer during keyboard navigation
        self.controller_motion = Gtk.EventControllerMotion.new()
        self.controller_motion.connect('motion', self.on_pointer_motion)
        self.add_controller(self.controller_motion)

    @property
    @abstractmethod
    def pages(self):
        children = []
        child = self.get_first_child()
        while child:
            children.append(child)
            child = child.get_next_sibling()

        return children

    @abstractmethod
    def add_page(self, position):
        raise NotImplementedError()

    @abstractmethod
    def clear(self):
        page = self.get_first_child()
        while page:
            next_page = page.get_next_sibling()
            page.clean()
            self.remove(page)
            page = next_page

    def crop_pages_borders(self):
        for page in self.pages:
            if page.status == 'rendered' and page.error is None:
                page.set_image()

    @abstractmethod
    def goto_page(self, page_index):
        raise NotImplementedError()

    def hide_cursor(self):
        self.set_cursor(Gdk.Cursor.new_from_name('none'))

    @abstractmethod
    def init(self):
        raise NotImplementedError()

    @abstractmethod
    def on_key_pressed(self, _widget, event):
        raise NotImplementedError()

    def on_pointer_motion(self, _controller, x, y):
        if int(x) == x and int(y) == y:
            # Hack? Ignore events triggered by Gtk.Carousel during page changes
            return Gdk.EVENT_PROPAGATE

        if self.get_cursor():
            # Cursor is hidden during keyboard navigation
            # Make cursor visible again when mouse is moved
            self.set_cursor(None)

        return Gdk.EVENT_PROPAGATE

    def on_page_rendered(self, page, retry):
        if not retry:
            return

        GLib.idle_add(self.update, page, 1)
        GLib.idle_add(self.save_progress, page)

    def rescale_pages(self):
        self.zoom['active'] = False

        for page in self.pages:
            page.rescale()

    def resize_pages(self, _pager=None, _orientation=None):
        self.zoom['active'] = False

        for page in self.pages:
            page.resize()

    def save_progress(self, page):
        """Save reading progress"""

        if page not in self.pages:
            return GLib.SOURCE_REMOVE

        # Loop as long as the page rendering is not ended
        if page.status == 'rendering':
            return GLib.SOURCE_CONTINUE

        if page.status != 'rendered' or page.error is not None:
            return GLib.SOURCE_REMOVE

        chapter = page.chapter

        # Update manga last read time
        self.reader.manga.update(dict(last_read=datetime.datetime.utcnow()))

        # Mark page as read
        chapter.pages[page.index]['read'] = True

        # Check if chapter has been fully read
        chapter_is_read = True
        for chapter_page in reversed(chapter.pages):
            if not chapter_page.get('read'):
                chapter_is_read = False
                break

        # Update chapter
        chapter.update(dict(
            pages=chapter.pages,
            last_page_read_index=page.index,
            last_read=datetime.datetime.utcnow(),
            read=chapter_is_read,
            recent=0,
        ))

        self.sync_progress_with_server(page, chapter_is_read)

        return GLib.SOURCE_REMOVE

    @abstractmethod
    def scroll_to_direction(self, direction):
        raise NotImplementedError()

    def sync_progress_with_server(self, page, chapter_is_read):
        # Sync reading progress with server if function is supported
        chapter = page.chapter

        def run():
            try:
                res = chapter.manga.server.update_chapter_read_progress(
                    dict(
                        page=page.index + 1,
                        completed=chapter_is_read,
                    ),
                    self.reader.manga.slug, self.reader.manga.name, chapter.slug, chapter.url
                )
                if res != NotImplemented and not res:
                    # Failed to save progress
                    on_error('server')
            except Exception as e:
                on_error('connection', log_error_traceback(e))

        def on_error(_kind, message=None):
            if message is not None:
                self.window.show_notification(_(f'Failed to sync read progress with server:\n{message}'), 2)
            else:
                self.window.show_notification(_('Failed to sync read progress with server'), 2)

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()


class Pager(Adw.Bin, BasePager):
    """Classic page by page pager (LTR, RTL, vertical)"""

    _interactive = True
    current_chapter_id = None
    init_flag = False

    def __init__(self, reader):

        Adw.Bin.__init__(self, focusable=True)
        BasePager.__init__(self, reader)

        self.carousel = Adw.Carousel()
        self.carousel.set_scroll_params(Adw.SpringParams.new(0.1, 0.05, 1))  # guesstimate
        self.carousel.set_allow_long_swipes(False)
        self.set_child(self.carousel)

        self.carousel.connect('notify::orientation', self.resize_pages)
        self.carousel.connect('page-changed', self.on_page_changed)

        # Keyboard navigation
        self.controller_key = Gtk.EventControllerKey.new()
        self.add_controller(self.controller_key)
        self.controller_key.connect('key-pressed', self.on_key_pressed)

        # Navigation when a page is scrollable (vertically or horizontally)
        # This can occur when page scaling is `adapt-to-height` or 'adapt-to-width'.
        # In this cases, scroll events are consumed and we must manage page changes in place of Adw.Carousel.
        self.controller_scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.add_controller(self.controller_scroll)
        self.controller_scroll.connect('scroll', self.on_scroll)

        # Mouse click layout navigation
        self.reader.gesture_click.connect('released', self.on_btn_press)

    @property
    def current_page(self):
        return self.carousel.get_nth_page(self.carousel.get_position())

    @GObject.Property(type=bool, default=True)
    def interactive(self):
        return self._interactive

    @interactive.setter
    def interactive(self, value):
        self._interactive = value
        self.carousel.set_interactive(value)

    @property
    def pages(self):
        for index in range(self.carousel.get_n_pages()):
            yield self.carousel.get_nth_page(index)

    def add_page(self, position):
        if position == 'start':
            self.carousel.get_nth_page(2).clean()
            self.carousel.remove(self.carousel.get_nth_page(2))

            page = self.carousel.get_nth_page(0)
            direction = 1 if self.reader.reading_mode == 'right-to-left' else -1
            new_page = Page(self, page.chapter, page.index + direction)
            self.carousel.prepend(new_page)
        else:
            self.carousel.get_nth_page(0).clean()
            self.carousel.remove(self.carousel.get_nth_page(0))

            page = self.carousel.get_nth_page(self.carousel.get_n_pages() - 1)
            direction = -1 if self.reader.reading_mode == 'right-to-left' else 1
            new_page = Page(self, page.chapter, page.index + direction)
            self.carousel.append(new_page)

        new_page.connect('rendered', self.on_page_rendered)
        new_page.connect('edge-overshot', self.on_page_edge_overshotted)
        new_page.render()

    def clear(self):
        for index in reversed(range(self.carousel.get_n_pages())):
            page = self.carousel.get_nth_page(index)
            page.clean()
            self.carousel.remove(page)

    def goto_page(self, index):
        if self.carousel.get_nth_page(0).index == index and self.carousel.get_nth_page(0).chapter == self.current_page.chapter:
            self.scroll_to_direction('left')
        elif self.carousel.get_nth_page(2).index == index and self.carousel.get_nth_page(2).chapter == self.current_page.chapter:
            self.scroll_to_direction('right')
        else:
            self.init(self.current_page.chapter, index)

    def init(self, chapter, page_index=None):
        self.init_flag = True
        self.zoom['active'] = False

        self.reader.update_title(chapter)
        self.clear()

        if page_index is None:
            if chapter.read:
                page_index = 0
            elif chapter.last_page_read_index is not None:
                page_index = chapter.last_page_read_index
            else:
                page_index = 0

        direction = 1 if self.reader.reading_mode == 'right-to-left' else -1

        # Left page
        left_page = Page(self, chapter, page_index + direction)
        left_page.connect('rendered', self.on_page_rendered)
        left_page.connect('edge-overshot', self.on_page_edge_overshotted)
        self.carousel.append(left_page)

        # Center page
        center_page = Page(self, chapter, page_index)
        center_page.connect('rendered', self.on_page_rendered)
        center_page.connect('edge-overshot', self.on_page_edge_overshotted)
        self.carousel.append(center_page)
        center_page.render()

        # Right page
        right_page = Page(self, chapter, page_index - direction)
        right_page.connect('rendered', self.on_page_rendered)
        right_page.connect('edge-overshot', self.on_page_edge_overshotted)
        self.carousel.append(right_page)

        left_page.render()
        right_page.render()

        GLib.idle_add(self.carousel.scroll_to, center_page, False)

    def on_btn_press(self, _gesture, _n_press, x, y):
        if not self.interactive:
            return

        if self.btn_press_timeout_id is None:  # and event.type == Gdk.EventType.BUTTON_PRESS:
            # Schedule single click event to be able to detect double click
            self.btn_press_timeout_id = GLib.timeout_add(self.default_double_click_time + 100, self.on_single_click, x, y)

        # elif event.type == Gdk.EventType._2BUTTON_PRESS:
        #     # Remove scheduled single click event
        #     if self.btn_press_timeout_id:
        #         GLib.source_remove(self.btn_press_timeout_id)
        #         self.btn_press_timeout_id = None
        #
        #     GLib.idle_add(self.on_double_click, event.copy())

        return Gdk.EVENT_STOP

    def on_double_click(self, x, y):
        # Zoom/unzoom
        if self.reader.reading_mode == 'webtoon':
            return

        def on_adjustment_change(hadj, vadj, h_value, v_value):
            hadj.disconnect(handler_id)

            def adjust_scroll():
                hadj.set_value(h_value)
                vadj.set_value(v_value)

            GLib.idle_add(adjust_scroll)

        page = self.current_page

        if page.status != 'rendered' or page.error is not None or page.animated:
            return

        hadj = page.scrolledwindow.get_hadjustment()
        vadj = page.scrolledwindow.get_vadjustment()

        if self.zoom['active'] is False:
            self.set_interactive(False)

            pixbuf = page.imagebuf.get_pixbuf()

            # Record hadjustment and vadjustment values
            self.zoom['orig_hadj_value'] = hadj.get_value()
            self.zoom['orig_vadj_value'] = vadj.get_value()

            # Adjust image's width to 2x window's width
            factor = 2
            orig_width = page.image.get_pixbuf().get_width() / self.window.hidpi_scale
            orig_height = page.image.get_pixbuf().get_height() / self.window.hidpi_scale
            zoom_width = self.reader.size.width * factor
            zoom_height = orig_height * (zoom_width / orig_width)
            ratio = zoom_width / orig_width

            if orig_width <= self.reader.size.width:
                rel_x = x - (self.reader.size.width - orig_width) / 2
            else:
                rel_x = x + hadj.get_value()
            if orig_height <= self.reader.size.height:
                rel_y = y - (self.reader.size.height - orig_height) / 2
            else:
                rel_y = y + vadj.get_value()

            h_value = rel_x * ratio - x
            v_value = rel_y * ratio - y

            handler_id = hadj.connect('changed', on_adjustment_change, vadj, h_value, v_value)

            scaled_pixbuf = pixbuf.scale_simple(
                zoom_width * self.window.hidpi_scale, zoom_height * self.window.hidpi_scale, InterpType.BILINEAR)

            if self.window.hidpi_scale != 1:
                page.image.set_from_surface(create_cairo_surface_from_pixbuf(scaled_pixbuf, self.window.hidpi_scale))
            else:
                page.image.set_from_pixbuf(scaled_pixbuf)

            self.zoom['active'] = True
        else:
            self.set_interactive(True)

            handler_id = hadj.connect(
                'changed', on_adjustment_change, vadj, self.zoom['orig_hadj_value'], self.zoom['orig_vadj_value'])

            page.set_image()

            self.zoom['active'] = False

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != 'reader' or not self.interactive:
            return Gdk.EVENT_PROPAGATE

        modifiers = Gtk.accelerator_get_default_mod_mask()
        if (state & modifiers) != 0:
            return Gdk.EVENT_PROPAGATE

        if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left, Gdk.KEY_Right, Gdk.KEY_KP_Right):
            # Hide mouse cursor when using keyboard navigation
            self.hide_cursor()

            page = self.current_page
            hadj = page.get_hadjustment()

            if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
                if hadj.get_value() == 0 and self.zoom['active'] is False:
                    self.scroll_to_direction('left')
                    return Gdk.EVENT_STOP

                page.emit('scroll-child', Gtk.ScrollType.STEP_LEFT, False)
                return Gdk.EVENT_STOP

            if hadj.get_value() + self.reader.size.width == hadj.get_upper() and self.zoom['active'] is False:
                self.scroll_to_direction('right')
                return Gdk.EVENT_STOP

            page.emit('scroll-child', Gtk.ScrollType.STEP_RIGHT, False)
            return Gdk.EVENT_STOP

        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up, Gdk.KEY_Down, Gdk.KEY_KP_Down):
            # Hide mouse cursor when using keyboard navigation
            self.hide_cursor()

            page = self.current_page
            vadj = page.get_vadjustment()

            if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
                if self.reader.reading_mode == 'vertical' and vadj.get_value() + self.reader.size.height == vadj.get_upper():
                    self.scroll_to_direction('right')
                    return Gdk.EVENT_STOP

                # If image height is greater than viewport height, arrow keys should scroll page down
                # Emit scroll signal: one step down
                page.emit('scroll-child', Gtk.ScrollType.STEP_DOWN, False)
                return Gdk.EVENT_STOP

            if self.reader.reading_mode == 'vertical' and vadj.get_value() == 0:
                self.scroll_to_direction('left')

                # After switching pages, go to the end of the page that is now the current page
                vadj = self.current_page.get_vadjustment()
                vadj.set_value(vadj.get_upper() - self.reader.size.height)
                return Gdk.EVENT_STOP

            # If image height is greater than viewport height, arrow keys should scroll page up
            # Emit scroll signal: one step up
            page.emit('scroll-child', Gtk.ScrollType.STEP_UP, False)
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_page_changed(self, _carousel, index):
        if index == 1 and not self.init_flag:
            # Partial/incomplete mouse drag
            return

        self.init_flag = False
        page = self.carousel.get_nth_page(index)

        if page.status == 'offlimit':
            GLib.idle_add(self.carousel.scroll_to, self.carousel.get_nth_page(1), True)

            if page.index == -1:
                message = _('There is no previous chapter.')
            else:
                message = _('It was the last chapter.')
            self.window.show_notification(message, interval=2)

            return

        # Disable navigation: will be re-enabled if page is loadable
        self.interactive = False

        # Bug here: see https://gitlab.gnome.org/GNOME/libadwaita/-/issues/430
        GLib.idle_add(self.update, page, index)
        GLib.idle_add(self.save_progress, page)

    def on_page_edge_overshotted(self, _page, position):
        # When page is scrollable, scroll events are consumed, so we must manage page changes in place of Adw.Carousel.
        # Use cases:
        # 1. Reading mode is `RTL` or `LTR`, page can be scrolled horizontally (page scaling is adapted to height) but not vertically
        # 2. Reading mode is `vertical`, page can be scrolled vertically (page scaling is adapted to width) but not horizontally

        if not self.interactive:
            return

        if self.reader.reading_mode in ('right-to-left', 'left-to-right'):
            if position in (Gtk.PositionType.TOP, Gtk.PositionType.BOTTOM):
                return

            self.scroll_to_direction('left' if position == Gtk.PositionType.LEFT else 'right')

        elif self.reader.reading_mode == 'vertical':
            if position in (Gtk.PositionType.LEFT, Gtk.PositionType.RIGHT):
                return

            self.scroll_to_direction('left' if position == Gtk.PositionType.TOP else 'right')

    def on_scroll(self, _controller, dx, dy):
        # When page is scrollable, scroll events are consumed, so we must manage page changes in place of Adw.Carousel.
        #
        # Use cases:
        # 1. Reading mode is `RTL` or `LTR`, page can be scrolled vertically (page scaling is adapted to width) but not horizontally
        # 2. Reading mode is `vertical` and page can be scrolled horizontally (page scaling is adapted to height) but not vertically
        # In both cases, we can't rely on `edge-overshot` event.

        if not self.current_page.props.can_target or not self.interactive:
            return

        if self.reader.reading_mode in ('right-to-left', 'left-to-right') and self.reader.scaling == 'width' and dx:
            self.scroll_to_direction('left' if dx < 0 else 'right')

        elif self.reader.reading_mode == 'vertical' and self.reader.scaling == 'height' and dy:
            self.scroll_to_direction('left' if dy < 0 else 'right')

    def on_single_click(self, x, _y):
        self.btn_press_timeout_id = None

        if x < self.reader.size.width / 3:
            # 1st third of the page
            if self.zoom['active']:
                return False

            self.scroll_to_direction('left')
        elif x > 2 * self.reader.size.width / 3:
            # Last third of the page
            if self.zoom['active']:
                return False

            self.scroll_to_direction('right')
        else:
            # Center part of the page: toggle controls
            self.reader.toggle_controls()

        return False

    def reverse_pages(self):
        left_page = self.carousel.get_nth_page(0)
        right_page = self.carousel.get_nth_page(2)

        self.carousel.reorder(left_page, 2)
        self.carousel.reorder(right_page, 0)

    def scroll_to_direction(self, direction):
        if direction == 'left':
            page = self.carousel.get_nth_page(0)
        elif direction == 'right':
            page = self.carousel.get_nth_page(self.carousel.get_n_pages() - 1)

        if page.status == 'offlimit':
            # We reached first or last chapter
            if direction == 'left':
                message = _('It was the last chapter.')
            elif direction == 'right':
                message = _('There is no previous chapter.')
            self.window.show_notification(message, interval=2)

            return

        if page == self.current_page:
            # Can occur during a quick keyboard navigation (when holding down an arrow key)
            return

        # Disable keyboard and mouse navigation: will be re-enabled if page is loadable
        self.interactive = False

        self.carousel.scroll_to(page, True)

    def set_orientation(self, orientation):
        self.carousel.set_orientation(orientation)

    def update(self, page, index):
        if self.window.page != 'reader':
            return GLib.SOURCE_REMOVE

        if not page.loadable and page.error is None:
            # Loop until page is loadable or page is on error
            return GLib.SOURCE_CONTINUE

        if page.loadable:
            self.interactive = True

            if index != 1:
                # Add next page depending of navigation direction
                self.add_page('start' if index == 0 else 'end')
        elif page.index == 0:
            self.window.show_notification(_('This chapter is inaccessible.'), 2)

        # Update title, initialize controls and notify user if chapter changed
        if self.current_chapter_id != page.chapter.id:
            self.current_chapter_id = page.chapter.id
            self.reader.update_title(page.chapter)
            self.window.show_notification(page.chapter.title, 2)
            self.reader.controls.init(page.chapter)

        # Update page number and controls page slider
        self.reader.update_page_number(page.index + 1, len(page.chapter.pages) if page.loadable else None)
        self.reader.controls.set_scale_value(page.index + 1)

        return GLib.SOURCE_REMOVE
