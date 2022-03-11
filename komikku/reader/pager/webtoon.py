# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk

from komikku.reader.pager import BasePager
from komikku.reader.pager.page import Page


class WebtoonPager(Gtk.ScrolledWindow, BasePager):
    """Vertical smooth/continuous scrolling (a.k.a. infinite canvas) pager"""

    current_chapter_id = None
    current_page = None
    current_page_scroll_value = 0
    interactive = False
    nb_preloaded_pages = 1  # Number of preloaded pages before and after the center/visible page
    scroll_direction = None
    clamp_size = 800

    render_pages_counter = 10
    render_pages_timeout_id = 0

    ignore_scroll_value_changes = False

    def __init__(self, reader):
        Gtk.ScrolledWindow.__init__(self)
        BasePager.__init__(self, reader)

        self.get_hscrollbar().hide()
        self.get_vscrollbar().hide()
        self.set_kinetic_scrolling(False)

        self.vadj = self.get_vadjustment()

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.START)
        self.set_child(self.box)

        self.controller_scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.add_controller(self.controller_scroll)
        self.controller_scroll.connect('scroll', self.on_scroll)

        self.scroll_changed_handler_id = self.vadj.connect('notify::upper', self.on_scroll_changed)
        self.scroll_value_changed_handler_id = self.vadj.connect('value-changed', self.on_scroll_value_changed)

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
            prev = offsets[index]
            _minimal, natural = page.get_preferred_size()
            offsets.append(prev + natural.height)

        return offsets

    def add_page(self, position):
        pages = self.pages

        if position == Gtk.PositionType.TOP:
            pages[-1].clean()
            self.box.remove(pages[-1])

            page = pages[0]
            new_page = Page(self, page.chapter, page.index - 1)
            self.box.prepend(new_page)
        else:
            page = pages[-1]
            new_page = Page(self, page.chapter, page.index + 1)
            self.box.append(new_page)

            pages[0].clean()
            self.box.remove(pages[0])

        self.adjust_scroll()

        new_page.status_changed_handler_id = new_page.connect('notify::status', self.on_page_status_changed)
        new_page.connect('rendered', self.on_page_rendered)

    def adjust_scroll(self, value=None, emit_signal=True):
        if value is None:
            value = self.get_page_offset(self.current_page) + self.current_page_scroll_value

        if emit_signal:
            self.vadj.set_value(value)
            if self.vadj.get_value() == value:
                self.vadj.emit('value-changed')
        else:
            with self.vadj.handler_block(self.scroll_value_changed_handler_id):
                self.vadj.set_value(value)

    def clear(self):
        # self.disable_keyboard_and_mouse_click_navigation()

        page = self.box.get_first_child()
        while page:
            next_page = page.get_next_sibling()
            page.clean()
            self.box.remove(page)
            page = next_page

    def dispose(self):
        BasePager.dispose(self)
        GLib.source_remove(self.render_pages_timeout_id)
        self.clear()

    def get_page_offset(self, page):
        offset = 0
        for p in self.box:
            if p == page:
                break
            _minimal, natural = p.get_preferred_size()
            offset += natural.height

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

        for i in range(-self.nb_preloaded_pages, self.nb_preloaded_pages + 1):
            page = Page(self, chapter, page_index + i)
            page.status_changed_handler_id = page.connect('notify::status', self.on_page_status_changed)
            page.connect('rendered', self.on_page_rendered)
            self.box.append(page)
            if i == 0:
                self.current_page = page
                page.render()

        self.render_pages_timeout_id = GLib.timeout_add(100, self.render_pages)
        GLib.idle_add(self.update, self.current_page)

        self.set_interactive(True)

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != 'reader':
            return Gdk.EVENT_PROPAGATE

        modifiers = Gtk.accelerator_get_default_mod_mask()
        if (state & modifiers) != 0:
            return Gdk.EVENT_PROPAGATE

        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self.hide_cursor()
            self.scroll_direction = Gtk.DirectionType.DOWN
            self.ignore_scroll_value_changes = False
            self.vadj.set_value(self.vadj.get_value() + self.vadj.get_step_increment())
            return Gdk.EVENT_STOP

        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self.hide_cursor()
            self.scroll_direction = Gtk.DirectionType.UP
            self.ignore_scroll_value_changes = False
            self.vadj.set_value(self.vadj.get_value() - self.vadj.get_step_increment())
            return Gdk.EVENT_STOP

        if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
            self.hide_cursor()
            self.scroll_to_direction('left')
            return Gdk.EVENT_STOP

        if keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
            self.hide_cursor()
            self.scroll_to_direction('right')
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_page_status_changed(self, page, _param):
        if page.status == 'rendering':
            return

        if page.status == 'render':
            return

        self.adjust_scroll()

        self.render_pages_counter += 1

    def on_scroll(self, _controller, _dx, dy):
        if not self.interactive:
            # Disable scrolling
            return Gdk.EVENT_STOP

        self.ignore_scroll_value_changes = False

        self.scroll_direction = Gtk.DirectionType.UP if dy < 0 else Gtk.DirectionType.DOWN

        return Gdk.EVENT_PROPAGATE

    def on_scroll_changed(self, *args):
        # Called when a page is added, removed or rendered
        self.adjust_scroll()

    def on_scroll_value_changed(self, _vadj):
        if self.ignore_scroll_value_changes:
            return

        self.ignore_scroll_value_changes = True

        scroll_value = self.vadj.get_value()
        if self.scroll_direction is None or self.scroll_direction == Gtk.DirectionType.UP:
            position = self.get_position(scroll_value)
        else:
            position = self.get_position(scroll_value + self.reader.size.height)
        page = self.pages[position]

        if page != self.current_page:
            if not page.loadable:
                # Cancel scroll
                value = self.get_page_offset(self.current_page)
                if self.scroll_direction == Gtk.DirectionType.DOWN:
                    _minimal, natural = self.current_page.get_preferred_size()
                    value -= self.reader.size.height - natural.height
                self.adjust_scroll(value=value, emit_signal=False)

                if page.status == 'offlimit':
                    if self.scroll_direction == Gtk.DirectionType.DOWN:
                        message = _('It was the last chapter.')
                    else:
                        message = _('There is no previous chapter.')
                    self.window.show_notification(message, 2)

                return

            self.current_page = page
            self.current_page_scroll_value = scroll_value - self.get_page_offset(page)

            # Disable navigation: it will be re-enabled if page is loadable
            self.set_interactive(False)

            GLib.idle_add(self.update, page)
            GLib.idle_add(self.save_progress, page)

            self.add_page(Gtk.PositionType.TOP if self.scroll_direction == Gtk.DirectionType.UP else Gtk.PositionType.BOTTOM)
        else:
            self.current_page_scroll_value = scroll_value - self.get_page_offset(page)

    def render_pages(self):
        if self.render_pages_counter == 0:
            return GLib.SOURCE_CONTINUE

        pages = self.pages
        if self.scroll_direction == Gtk.DirectionType.DOWN:
            pages = reversed(pages)

        for page in pages:
            if page.status is None:
                page.render()
                self.render_pages_counter -= 1
            if self.render_pages_counter == 0:
                break

        return GLib.SOURCE_CONTINUE

    def scroll_to_direction(self, direction):
        value = self.vadj.get_value()

        if direction == 'right':
            self.scroll_direction = Gtk.DirectionType.DOWN
            value += self.reader.size.height * 2 / 3
        else:
            self.scroll_direction = Gtk.DirectionType.UP
            value -= self.reader.size.height * 2 / 3

        self.ignore_scroll_value_changes = False
        self.vadj.set_value(value)

    def set_interactive(self, interactive):
        self.interactive = interactive

    def set_orientation(self, _orientation):
        return

    def update(self, page, _index=None):
        if page not in self.pages:
            return GLib.SOURCE_REMOVE

        if not page.loadable and page.error is None:
            # Loop until page is loadable or page is on error
            return GLib.SOURCE_CONTINUE

        if page.loadable:
            self.set_interactive(True)

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
