# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk

from komikku.reader.pager import BasePager
from komikku.reader.pager.page import Page


class WebtoonPager(Gtk.ScrolledWindow, BasePager):
    """Vertical smooth/continuous scrolling (a.k.a. infinite canvas) pager"""

    current_chapter_id = None
    current_page = None
    scroll_direction = None
    clamp_size = 800

    def __init__(self, reader):
        Gtk.ScrolledWindow.__init__(self)
        BasePager.__init__(self, reader)

        self.get_hscrollbar().hide()
        self.get_vscrollbar().hide()
        self.set_kinetic_scrolling(True)

        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(self.clamp_size)
        self.set_child(self.clamp)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.START)
        self.clamp.set_child(self.box)

        self.controller_scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.KINETIC)
        self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.add_controller(self.controller_scroll)
        self.controller_scroll.connect('scroll', self.on_scroll)

        self.vadj = self.get_vadjustment()

        self.zoom['active'] = False

    @property
    def pages(self):
        children = []
        for page in self.box:
            children.append(page)

        return children

    @property
    def pages_offsets(self):
        pages = self.pages

        offsets = [0]
        for index, page in enumerate(pages[:-1]):
            offsets.append(offsets[index] + page.height)

        return offsets

    def add_page(self, position):
        pages = self.pages

        if position == 'start':
            pages[-1].clean()
            self.box.remove(pages[-1])

            new_page = Page(self, pages[0].chapter, pages[0].index - 1)
            self.box.prepend(new_page)
            # New page is added on top, scroll position must be adjusted
            self.adjust_scroll(self.vadj.props.value + self.reader.size.height)
        else:
            pages[0].clean()
            self.box.remove(pages[0])
            # Top page is removed, scroll position must be adjusted
            self.adjust_scroll(self.vadj.props.value - pages[0].height)

            new_page = Page(self, pages[-1].chapter, pages[-1].index + 1)
            self.box.append(new_page)

        new_page.connect('notify::status', self.on_page_status_changed)
        new_page.connect('rendered', self.on_page_rendered)
        new_page.render()

    def adjust_scroll(self, value):
        self.vadj.set_value(value)

    def clear(self):
        page = self.box.get_first_child()
        while page:
            next_page = page.get_next_sibling()
            page.clean()
            self.box.remove(page)
            page = next_page

    def dispose(self):
        BasePager.dispose(self)
        self.clear()

    def get_page_offset(self, page):
        offset = 0
        for p in self.box:
            if p == page:
                break
            offset += page.height

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
        self.init(self.current_page.chapter, index)

    def init(self, chapter, page_index=None):
        self.clear()

        if page_index is None:
            if chapter.read:
                page_index = 0
            elif chapter.last_page_read_index is not None:
                page_index = chapter.last_page_read_index
            else:
                page_index = 0

        for i in range(-1, 2):
            page = Page(self, chapter, page_index + i)
            page.connect('notify::status', self.on_page_status_changed)
            page.connect('rendered', self.on_page_rendered)
            self.box.append(page)
            if i == 0:
                self.current_page = page
                page.render()

        def init_pages():
            self.adjust_scroll(self.reader.size.height)

            for index, page in enumerate(self.pages):
                page.render()

            GLib.idle_add(self.update, self.current_page, 1)

        GLib.timeout_add(150, init_pages)

    def on_btn_clicked(self, _gesture, _n_press, x, y):
        self.on_single_click(x, y)

        return Gdk.EVENT_STOP

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

    def on_page_status_changed(self, page, _param):
        if page.status != 'rendered' or not page.get_parent():
            return

        pages = self.pages
        if pages.index(page) < pages.index(self.current_page):
            # A page above current page were rendered, scroll position must be adjusted
            # Size increase must be added
            self.adjust_scroll(self.vadj.props.value + page.height - self.reader.size.height)

    def on_scroll(self, _controller, _dx, dy):
        self.scroll_direction = Gtk.DirectionType.UP if dy < 0 else Gtk.DirectionType.DOWN

        scroll_value = self.vadj.get_value()
        if self.scroll_direction == Gtk.DirectionType.UP:
            position = self.get_position(scroll_value)
        else:
            position = self.get_position(scroll_value + self.reader.size.height)
        page = self.pages[position]

        if page == self.current_page:
            return

        if page.status == 'offlimit':
            # Cancel scroll
            if page == self.pages[0]:
                value = self.reader.size.height
            else:
                value = self.get_page_offset(page) - self.reader.size.height
            self.adjust_scroll(value)

            if self.scroll_direction == Gtk.DirectionType.DOWN:
                message = _('It was the last chapter.')
            else:
                message = _('There is no previous chapter.')
            self.window.show_notification(message, 2)

            return True

        self.current_page = page

        GLib.idle_add(self.update, page, position)
        GLib.idle_add(self.save_progress, page)

    def on_single_click(self, x, _y):
        if x >= self.reader.size.width / 3 or x <= 2 * self.reader.size.width / 3:
            # Center part of the page: toggle controls
            self.reader.toggle_controls()

    def scroll_to_direction(self, direction):
        if direction == Gtk.DirectionType.DOWN:
            self.emit('scroll-child', Gtk.ScrollType.STEP_DOWN, False)
            self.on_scroll(None, None, 1)
        else:
            self.emit('scroll-child', Gtk.ScrollType.STEP_UP, False)
            self.on_scroll(None, None, -1)

    def set_orientation(self, _orientation):
        return

    def update(self, page, index=None):
        if self.window.page != 'reader':
            return GLib.SOURCE_REMOVE

        if not page.loadable and page.error is None:
            # Loop until page is loadable or page is on error
            return GLib.SOURCE_CONTINUE

        if page.loadable and index != 1:
            # Add next page depending of navigation direction
            self.add_page('start' if index == 0 else 'end')

        # Update title, initialize controls and notify user if chapter changed
        if self.current_chapter_id != page.chapter.id:
            self.current_chapter_id = page.chapter.id

            self.reader.update_title(page.chapter)
            self.window.show_notification(page.chapter.title, 2)
            self.reader.controls.init(page.chapter)

        if page.error:
            self.window.show_notification(_('This chapter is inaccessible.'), 2)

        # Update page number and controls page slider
        self.reader.update_page_number(page.index + 1, len(page.chapter.pages) if page.loadable else None)
        self.reader.controls.set_scale_value(page.index + 1)

        return GLib.SOURCE_REMOVE
