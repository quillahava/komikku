# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk

from komikku.models import Settings
from komikku.reader.pager import BasePager
from komikku.reader.pager.page import Page


class WebtoonPager(Adw.Bin, BasePager):
    """Vertical smooth/continuous scrolling (a.k.a. infinite canvas) pager"""

    add_page_lock = False
    current_chapter_id = None

    gesture_drag_offset = None
    scroll_direction = None
    scroll_page = None
    scroll_page_percentage = 0

    def __init__(self, reader):
        super().__init__()
        BasePager.__init__(self, reader)

        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(Settings.get_default().clamp_size)
        self.clamp.set_tightening_threshold(Settings.get_default().clamp_size)
        self.set_child(self.clamp)

        self.scrolledwindow = Gtk.ScrolledWindow()
        self.scrolledwindow.get_hscrollbar().hide()
        self.scrolledwindow.get_vscrollbar().hide()
        self.scrolledwindow.set_kinetic_scrolling(True)
        self.vadj = self.scrolledwindow.get_vadjustment()
        self.clamp.set_child(self.scrolledwindow)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.START)
        self.scrolledwindow.set_child(self.box)

        # Scroll controller
        self.controller_scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.KINETIC
        )
        self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.controller_scroll.connect('scroll', self.on_scroll)
        self.scrolledwindow.add_controller(self.controller_scroll)

        # Scrolling detection on touch screen
        self.gesture_drag = Gtk.GestureDrag.new()
        self.gesture_drag.connect('cancel', self.on_gesture_drag_cancel)
        self.gesture_drag.connect('drag-begin', self.on_gesture_drag_begin)
        self.gesture_drag.connect('drag-end', self.on_gesture_drag_end)
        self.gesture_drag.connect('drag-update', self.on_gesture_drag_update)
        self.gesture_drag.set_touch_only(True)
        self.scrolledwindow.add_controller(self.gesture_drag)

        self.zoom['active'] = False

    @property
    def pages(self):
        return list(self.box)

    @property
    def pages_offsets(self):
        offsets = [0]
        for index, page in enumerate(self.pages[:-1]):
            offsets.append(offsets[index] + page.height)

        return offsets

    @property
    def size(self):
        size = self.scrolledwindow.get_allocation()
        size.width = min(size.width, self.reader.size.width)

        return size

    def add_page(self, position, init=False):
        """
        Depending on the position parameter, add a page at start (top) or at end (bottom)

        At init, when first pages are added, no page is removed on opposite position
        """
        self.add_page_lock = True

        pages = self.pages
        top_page = pages[0]
        bottom_page = pages[-1]

        def remove_page():
            if len(self.pages) < 11:
                return

            if position == 'start':
                # Don't remove bottom page if visible
                if self.get_page_offset(bottom_page) <= self.vadj.props.value + self.vadj.props.page_size:
                    return

                # Remove bottom page
                bottom_page.clean()
                self.box.remove(bottom_page)
            else:
                # Don't remove top page if visible
                if self.get_page_offset(top_page) + top_page.height > self.vadj.props.value:
                    return

                # Remove top page
                scroll_value = self.vadj.props.value - top_page.height
                top_page.clean()
                self.box.remove(top_page)
                # Page removed at top, scroll position has been lost and must be re-adjusted
                self.adjust_scroll(scroll_value)

        if position == 'start':
            if not top_page.loadable or top_page.status == 'offlimit':
                self.add_page_lock = False
                return GLib.SOURCE_REMOVE

            new_page = Page(self, top_page.chapter, top_page.index - 1)
        else:
            if not bottom_page.loadable or bottom_page.status == 'offlimit':
                self.add_page_lock = False
                return GLib.SOURCE_REMOVE

            new_page = Page(self, bottom_page.chapter, bottom_page.index + 1)

        # At init, page on opposite side is not deleted
        if not init:
            remove_page()

        if position == 'start':
            scroll_value = self.vadj.get_value() + new_page.init_height
            self.box.prepend(new_page)
            # Page is added at top, scroll position has been lost and must be re-adjusted
            self.adjust_scroll(scroll_value)
        else:
            self.box.append(new_page)

        new_page.connect('notify::status', self.on_page_status_changed)
        new_page.connect('rendered', self.on_page_rendered)
        new_page.render()

        self.add_page_lock = False

        return GLib.SOURCE_REMOVE

    def add_pages_worker(self):
        """Monitors whether pages need to be added"""
        if self.add_page_lock:
            return GLib.SOURCE_CONTINUE

        # At init (until pages are scrollable), pages are added only at bottom
        # If pages were added at top, scroll position could not be maintained
        init = self.vadj.props.upper == self.vadj.props.page_size

        pages = self.pages

        if init or self.scroll_direction == Gtk.DirectionType.DOWN:
            bottom_page = pages[-1]
            bottom_page_offset = self.get_page_offset(bottom_page)
            # Add page at bottom only if bottom page is visible
            if bottom_page_offset <= self.vadj.props.value + self.vadj.props.page_size:
                self.add_page('end', init)

        if self.scroll_direction == Gtk.DirectionType.UP:
            top_page = pages[0]
            top_page_offset = self.get_page_offset(top_page)
            # Add page at top only if top page is visible
            if top_page_offset + top_page.height > self.vadj.props.value:
                self.add_page('start', init)

        return GLib.SOURCE_CONTINUE

    def adjust_scroll(self, value=None):
        if value is None:
            value = self.get_page_offset(self.scroll_page)
            if self.scroll_page_percentage:
                value += (self.scroll_page.height / 100) * self.scroll_page_percentage

        self.vadj.set_value(value)

    def clear(self):
        page = self.box.get_first_child()
        while page:
            next_page = page.get_next_sibling()
            page.clean()
            self.box.remove(page)
            page = next_page

    def dispose(self):
        GLib.Source.remove(self.add_pages_worker_id)
        self.clear()

        BasePager.dispose(self)

    def get_page_offset(self, page):
        offset = 0
        for p in self.box:
            if p == page:
                break
            offset += p.height

        return offset

    def get_position(self, scroll_value):
        pages_offsets = self.pages_offsets
        position = None

        for i, page_offset in enumerate(reversed(pages_offsets)):
            if scroll_value >= page_offset:
                position = len(pages_offsets) - 1 - i
                break

        return position

    def goto_page(self, index):
        self.init(self.scroll_page.chapter, index)

    def init(self, chapter, page_index=None):
        self.clear()

        if page_index is None:
            if chapter.read:
                page_index = 0
            elif chapter.last_page_read_index is not None:
                page_index = chapter.last_page_read_index
            else:
                page_index = 0

        page = Page(self, chapter, page_index)
        page.connect('notify::status', self.on_page_status_changed)
        page.connect('rendered', self.on_page_rendered)
        self.box.append(page)

        self.scroll_page = page
        self.current_page = page
        page.render()

        self.add_pages_worker_id = GLib.timeout_add(100, self.add_pages_worker)
        GLib.idle_add(self.update, self.current_page)

    def on_btn_clicked(self, _gesture, _n_press, x, y):
        self.on_single_click(x, y)

        return Gdk.EVENT_STOP

    def on_gesture_drag_begin(self, controller, start_x, start_y):
        self.gesture_drag_offset = 0

    def on_gesture_drag_cancel(self, controller, *args):
        controller.set_state(Gtk.EventSequenceState.DENIED)

    def on_gesture_drag_end(self, controller, _offset_x, _offset_y):
        controller.set_state(Gtk.EventSequenceState.DENIED)

    def on_gesture_drag_update(self, controller, offset_x, offset_y):
        controller.set_state(Gtk.EventSequenceState.CLAIMED)

        if abs(offset_y) <= abs(offset_x):
            # Ignore horizontal drag
            return

        offset = round(offset_y - self.gesture_drag_offset)
        if not offset:
            # Ignore null drag
            return

        self.adjust_scroll(self.vadj.props.value - offset)
        self.on_scroll(None, None, -offset)

        self.gesture_drag_offset = offset_y

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != 'reader':
            return Gdk.EVENT_PROPAGATE

        modifiers = Gtk.accelerator_get_default_mod_mask()
        if (state & modifiers) != 0:
            return Gdk.EVENT_PROPAGATE

        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down, Gdk.KEY_Right, Gdk.KEY_KP_Right):
            self.hide_cursor()
            self.scroll_to_direction(Gtk.DirectionType.DOWN)
            return Gdk.EVENT_STOP

        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up, Gdk.KEY_Left, Gdk.KEY_KP_Left):
            self.hide_cursor()
            self.scroll_to_direction(Gtk.DirectionType.UP)
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_page_rendered(self, page, retry):
        if not retry:
            return

        # After a retry, update the page and save the progress (if relevant)
        GLib.idle_add(self.update, page, 1)
        GLib.idle_add(self.save_progress, page)

    def on_page_status_changed(self, page, _param):
        if page.status != 'rendered':
            return

        self.add_page_lock = True
        pages = self.pages

        try:
            if pages.index(page) < pages.index(self.scroll_page):
                # A page above scroll_page were rendered, scroll position must be adjusted
                self.adjust_scroll(self.vadj.props.value + page.height - page.init_height)
        except Exception:
            pass

        self.add_page_lock = False

    def on_scroll(self, _controller, _dx, dy):
        pages = self.pages

        # Update scroll state
        self.scroll_direction = Gtk.DirectionType.UP if dy < 0 else Gtk.DirectionType.DOWN
        scroll_value_top = self.vadj.get_value()
        scroll_position_top = self.get_position(scroll_value_top)
        self.scroll_page = pages[scroll_position_top]
        scroll_page_value = scroll_value_top - self.get_page_offset(self.scroll_page)
        self.scroll_page_percentage = 100 * scroll_page_value / self.scroll_page.height

        # Hide controls
        self.reader.toggle_controls(False)

        if self.scroll_direction == Gtk.DirectionType.DOWN:
            current_page = pages[self.get_position(scroll_value_top + self.vadj.props.page_size)]
        else:
            current_page = pages[scroll_position_top]

        if not current_page.loadable:
            if current_page.status == 'offlimit':
                if self.scroll_direction == Gtk.DirectionType.UP:
                    scroll_page_value = self.get_page_offset(pages[1])
                    self.scroll_page_percentage = 0
                else:
                    scroll_page_value = self.get_page_offset(pages[-1]) - self.vadj.props.page_size
                    self.scroll_page_percentage = 100

                self.adjust_scroll(scroll_page_value)

                if self.scroll_direction == Gtk.DirectionType.DOWN:
                    message = _('It was the last chapter.')
                else:
                    message = _('There is no previous chapter.')
                self.window.show_notification(message, 1)

                return Gdk.EVENT_STOP

        if current_page != self.current_page:
            self.current_page = current_page
            GLib.idle_add(self.update, current_page)
            GLib.idle_add(self.save_progress, current_page)

    def on_single_click(self, x, _y):
        if x >= self.reader.size.width / 3 and x <= 2 * self.reader.size.width / 3:
            # Center part of the page: toggle controls
            self.reader.toggle_controls()

    def scroll_to_direction(self, direction):
        if direction == Gtk.DirectionType.DOWN:
            self.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_DOWN, False)
            self.on_scroll(None, None, 1)
        else:
            self.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_UP, False)
            self.on_scroll(None, None, -1)

    def set_orientation(self, _orientation):
        return

    def resize_pages(self, _pager=None, _orientation=None):
        BasePager.rescale_pages(self)
        self.adjust_scroll()

    def update(self, page, _direction=None):
        if self.window.page != 'reader' or self.current_page != page:
            return GLib.SOURCE_REMOVE

        if not page.loadable and page.error is None:
            # Loop until page is loadable or page is on error
            return GLib.SOURCE_CONTINUE

        # Update title, initialize controls and notify user if chapter changed
        if self.current_chapter_id != page.chapter.id:
            self.current_chapter_id = page.chapter.id

            self.reader.update_title(page.chapter)
            self.window.show_notification(page.chapter.title, 2)
            self.reader.controls.init(page.chapter)

        if not page.loadable:
            self.window.show_notification(_('This chapter is inaccessible.'), 2)

        # Update page number and controls page slider
        self.reader.update_page_numbering(page.index + 1, len(page.chapter.pages) if page.loadable else None)
        self.reader.controls.set_scale_value(page.index + 1)

        return GLib.SOURCE_REMOVE
