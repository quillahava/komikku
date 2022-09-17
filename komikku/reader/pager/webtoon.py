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


class WebtoonPager(Gtk.ScrolledWindow, BasePager):
    """Vertical smooth/continuous scrolling (a.k.a. infinite canvas) pager"""

    current_chapter_id = None
    interactive = True

    gesture_drag_offset = None
    scroll_page = None
    scroll_direction = None
    scroll_page_percentage = 0
    scroll_page_value = 0
    scroll_status = None

    preloaded = 5  # number of preloaded pages before and after current page

    def __init__(self, reader):
        super().__init__()
        BasePager.__init__(self, reader)

        self.get_hscrollbar().hide()
        self.get_vscrollbar().hide()
        self.set_kinetic_scrolling(True)

        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(Settings.get_default().clamp_size)
        self.set_child(self.clamp)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.START)
        self.clamp.set_child(self.box)

        self.controller_scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.KINETIC
        )
        self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.add_controller(self.controller_scroll)

        self.controller_scroll.connect('decelerate', self.on_scroll_decelerate)
        self.controller_scroll.connect('scroll', self.on_scroll)

        # Scrolling detection on touch screen
        self.gesture_drag = Gtk.GestureDrag.new()
        self.gesture_drag.connect('cancel', self.on_gesture_drag_cancel)
        self.gesture_drag.connect('drag-begin', self.on_gesture_drag_begin)
        self.gesture_drag.connect('drag-end', self.on_gesture_drag_end)
        self.gesture_drag.connect('drag-update', self.on_gesture_drag_update)
        self.gesture_drag.set_touch_only(True)
        self.add_controller(self.gesture_drag)

        self.vadj = self.get_vadjustment()
        self.value_changed_handler_id = self.vadj.connect('value-changed', self.on_scroll_value_changed)

        self.zoom['active'] = False

    @property
    def pages(self):
        return list(self.box)

    @property
    def pages_offsets(self):
        pages = self.pages

        offsets = [0]
        for index, page in enumerate(pages[:-1]):
            offsets.append(offsets[index] + page.height)

        return offsets

    def add_pages(self, position, count=1, do_remove=True, init=False):
        """
        Allows to add one or more pages

        - Depending on the position parameter, pages are added at the beginning or at the end.
        - Unless do_remove = False, a page is removed on the opposite.
        - On init, when first pages are added, relative vertical adjustment is not working
          (we don't know when vertical adjustment will be modifiable and in which order pages will be added),
          so an absolute vertical adjustment is done each time a page is added.
        """
        pages = self.pages

        if position == 'start':
            if pages[0].index - 1 >= 0:
                if not pages[0].loadable and pages[0].error is None and not pages[0].status == 'offlimit':
                    return GLib.SOURCE_CONTINUE

                if not pages[0].loadable:
                    if init:
                        self.adjust_scroll()

                    self.interactive = True
                    return GLib.SOURCE_REMOVE

            if do_remove:
                pages[-1].clean()
                self.box.remove(pages[-1])

            new_page = Page(self, pages[0].chapter, pages[0].index - 1)
            self.box.prepend(new_page)
            # New page is added on top, scroll position must be adjusted
            self.adjust_scroll(self.vadj.props.value + new_page.init_height)
        else:
            if not pages[-1].loadable and pages[-1].error is None and not pages[-1].status == 'offlimit':
                return GLib.SOURCE_CONTINUE

            if not pages[-1].loadable:
                if init:
                    self.adjust_scroll()

                self.interactive = True
                return GLib.SOURCE_REMOVE

            if do_remove:
                height = pages[0].height
                pages[0].clean()
                self.box.remove(pages[0])
                # Top page is removed, scroll position must be adjusted
                self.adjust_scroll(self.vadj.props.value - height)

            new_page = Page(self, pages[-1].chapter, pages[-1].index + 1)
            self.box.append(new_page)

        if init:
            self.adjust_scroll()

        new_page.connect('notify::status', self.on_page_status_changed)
        new_page.connect('rendered', self.on_page_rendered)
        new_page.render()

        if count - 1 > 0:
            GLib.idle_add(self.add_pages, position, count - 1, do_remove, init)
        else:
            self.interactive = True
            return GLib.SOURCE_REMOVE

    def adjust_scroll(self, value=None):
        if value is None:
            value = self.get_page_offset(self.scroll_page)
            if self.scroll_page_percentage:
                value += (self.scroll_page.height / 100) * self.scroll_page_percentage

        with self.vadj.handler_block(self.value_changed_handler_id):
            self.vadj.props.value = value

    def clear(self):
        page = self.box.get_first_child()
        while page:
            next_page = page.get_next_sibling()
            page.clean()
            self.box.remove(page)
            page = next_page

    def dispose(self):
        self.vadj.disconnect(self.value_changed_handler_id)
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

        GLib.idle_add(self.add_pages, 'end', self.preloaded, False, True)
        GLib.idle_add(self.add_pages, 'start', self.preloaded, False, True)
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
        if self.window.page != 'reader' or not self.interactive:
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
        if page.status != 'rendered':
            return

        pages = self.pages

        try:
            if pages.index(page) < pages.index(self.scroll_page):
                # A page above current page were rendered, scroll position must be adjusted
                self.adjust_scroll(self.vadj.props.value + page.height - page.init_height)
        except Exception:
            pass

    def on_scroll(self, _controller, _dx, dy, decelerate=False):
        if not self.interactive:
            return Gdk.EVENT_STOP

        # Hide controls
        self.reader.toggle_controls(False)

        self.interactive = False

        scroll_value_top = self.vadj.get_value()

        if not decelerate:
            self.scroll_status = 'scroll'
            self.set_kinetic_scrolling(True)
        else:
            # Disable kinetic scrolling otherwise any changes to vadjustment's value would be ignored
            self.set_kinetic_scrolling(False)

        pages = self.pages
        scroll_position_top = self.get_position(scroll_value_top)
        page_top = pages[scroll_position_top]

        self.scroll_direction = Gtk.DirectionType.UP if dy < 0 else Gtk.DirectionType.DOWN
        if self.scroll_direction == Gtk.DirectionType.DOWN:
            current_page = pages[self.get_position(scroll_value_top + self.vadj.props.page_size)]
        else:
            current_page = pages[scroll_position_top]

        if not current_page.loadable:
            if current_page.status == 'offlimit':
                if self.scroll_direction == Gtk.DirectionType.UP:
                    self.scroll_page_value = self.get_page_offset(self.scroll_page)
                    self.scroll_page_percentage = 0
                else:
                    self.scroll_page_value = self.get_page_offset(self.current_page) + self.scroll_page.height - self.vadj.props.page_size
                    self.scroll_page_percentage = 100

                self.adjust_scroll(self.scroll_page_value)

                if self.scroll_direction == Gtk.DirectionType.DOWN:
                    message = _('It was the last chapter.')
                else:
                    message = _('There is no previous chapter.')
                self.window.show_notification(message, 1)

                self.interactive = True
                return Gdk.EVENT_STOP

        add_cond1 = self.scroll_direction == Gtk.DirectionType.DOWN and scroll_position_top > self.preloaded
        add_cond2 = self.scroll_direction == Gtk.DirectionType.UP and scroll_position_top < self.preloaded

        if page_top != self.scroll_page and (add_cond1 or add_cond2):
            delta = abs(scroll_position_top - self.pages.index(self.scroll_page))

            self.scroll_page = page_top

            do_remove = len(self.pages) == self.preloaded * 2 + 1
            GLib.idle_add(self.add_pages, 'start' if self.scroll_direction == Gtk.DirectionType.UP else 'end', delta, do_remove)
        else:
            if page_top != self.scroll_page:
                self.scroll_page = page_top
            self.interactive = True

        if current_page != self.current_page:
            self.current_page = current_page
            GLib.idle_add(self.update, current_page)
            GLib.idle_add(self.save_progress, current_page)

        self.scroll_page_value = scroll_value_top - self.get_page_offset(page_top)
        self.scroll_page_percentage = 100 * self.scroll_page_value / page_top.height

    def on_scroll_decelerate(self, _controller, _vel_x, _vel_y):
        self.scroll_status = 'decelerate'

    def on_scroll_value_changed(self, _vadj):
        if self.scroll_status == 'decelerate':
            # A decelerate scroll doesn't emit scroll events
            self.on_scroll(None, None, 1 if self.scroll_direction == Gtk.DirectionType.DOWN else -1, True)

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

        if page.error:
            self.window.show_notification(_('This chapter is inaccessible.'), 2)

        # Update page number and controls page slider
        self.reader.update_page_number(page.index + 1, len(page.chapter.pages) if page.loadable else None)
        self.reader.controls.set_scale_value(page.index + 1)

        return GLib.SOURCE_REMOVE
