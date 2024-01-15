# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import logging

import gi

gi.require_version('Gtk', '4.0')

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Graphene
from gi.repository import Gsk
from gi.repository import Gtk

logger = logging.getLogger('komikku')

PRELOAD = 5  # in widget height unit
SCROLL_CLICK_PERCENTAGE = 2 / 3
SCROLL_DRAG_FACTOR = 2


class KInfiniteCanvas(Gtk.Widget, Gtk.Scrollable):
    __gtype_name__ = 'KInfiniteCanvas'
    __gsignals__ = {
        'controls-zone-clicked': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'keyboard-navigation': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'offlimit': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'page-requested': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, pager):
        super().__init__()

        self.pager = pager

        self.__hadj = None
        self.__vadj = None

        self.scroll_adjusting_delta = 0
        self.scroll_direction = None
        self.scroll_drag_offset = 0

        self.is_scroll_adjusting = False
        self.is_scroll_by_increment = False
        self.is_scroll_decelerating = False

        self.current_page_top = None
        self.current_page_bottom = None

        self.prev_width = None
        self.canvas_height = 0

        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.connect_signals()
        self.add_controllers()

    @property
    def canvas_width(self):
        return self.widget_width

    @GObject.Property(type=Gtk.Adjustment)
    def hadjustment(self):
        return self.__hadj

    @hadjustment.setter
    def hadjustment(self, adj):
        self.__hadj = adj

    @GObject.Property(type=Gtk.ScrollablePolicy, default=Gtk.ScrollablePolicy.MINIMUM)
    def hscroll_policy(self):
        return Gtk.ScrollablePolicy.MINIMUM

    @property
    def max_vadjustment_value(self):
        return max(self.canvas_height - self.widget_height, 0)

    @property
    def pages(self):
        pages = []
        page = self.get_first_child()
        while page:
            pages.append(page)
            page = page.get_next_sibling()

        return pages

    @GObject.Property(type=Gtk.Adjustment)
    def vadjustment(self):
        return self.__vadj

    @vadjustment.setter
    def vadjustment(self, adj):
        self.vadjustment_value_changed_handler_id = adj.connect('value-changed', lambda adj: self.queue_allocate())
        self.__vadj = adj

    @GObject.Property(type=Gtk.ScrollablePolicy, default=Gtk.ScrollablePolicy.MINIMUM)
    def vscroll_policy(self):
        return Gtk.ScrollablePolicy.MINIMUM

    @property
    def widget_height(self):
        return self.get_height()

    @property
    def widget_width(self):
        return self.get_width()

    def add_controllers(self):
        # Scroll controller
        self.controller_scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.KINETIC
        )
        self.controller_scroll.connect('decelerate', self.on_scroll_decelerate)
        self.controller_scroll.connect('scroll', self.on_scroll)
        self.add_controller(self.controller_scroll)

        # Gesture drag controller
        self.gesture_drag = Gtk.GestureDrag.new()
        self.gesture_drag.connect('drag-begin', self.on_gesture_drag_begin)
        self.gesture_drag.connect('drag-end', self.on_gesture_drag_end)
        self.gesture_drag.connect('drag-update', self.on_gesture_drag_update)
        self.pager.add_controller(self.gesture_drag)

        # Gesture click controller: Navigation layout
        self.gesture_click = Gtk.GestureClick.new()
        self.gesture_click.set_button(1)
        self.gesture_click.connect('released', self.on_gesture_click_released)
        self.add_controller(self.gesture_click)

    def add_or_remove_page(self):
        if not self.get_first_child() or self.is_scroll_decelerating or self.is_scroll_adjusting or self.is_scroll_by_increment:
            return

        first_page = self.get_first_child()
        last_page = self.get_last_child()
        if self.scroll_direction in (Gtk.DirectionType.DOWN, None):
            if last_page.loadable and last_page._ic_position + last_page._ic_height < self.widget_height * (PRELOAD + 1):
                self.emit('page-requested', 'end')
                return

            if first_page.loadable and first_page._ic_position + first_page._ic_height < -self.widget_height * PRELOAD:
                self.remove(first_page)
                return

        if self.scroll_direction in (Gtk.DirectionType.UP, None):
            if first_page.loadable and first_page._ic_position > -self.widget_height * PRELOAD:
                self.emit('page-requested', 'start')
                return

            if last_page.loadable and last_page._ic_position > self.widget_height * (PRELOAD + 1):
                self.remove(last_page)
                return

        if self.scroll_direction is None:
            # Set a default scroll direction at end of init
            self.scroll_direction = Gtk.DirectionType.DOWN

    def append(self, page):
        """ Adds page at end """
        last_page = self.get_last_child()

        page._ic_height = self.get_height()
        page._ic_position = last_page._ic_position + last_page._ic_height if last_page else 0

        page.insert_before(self, None)

        page.connect('rendered', self.on_page_rendered)
        page.render()

    def cancel_deceleration(self):
        # Assume parent of `self` is a Gtk.ScrolledWindow
        self.get_parent().set_kinetic_scrolling(False)
        self.get_parent().set_kinetic_scrolling(True)

    def clear(self):
        page = self.get_last_child()
        while page:
            prev_page = page.get_prev_sibling()
            page.dispose()
            page = prev_page

        self.scroll_direction = None
        self.queue_allocate()

    def configure_adjustments(self):
        if self.vadjustment is None:
            return

        lower = 0
        if first_page := self.get_first_child():
            if first_page.status == 'offlimit' and self.scroll_direction in (None, Gtk.DirectionType.UP):
                # Offlimit start
                lower += self.widget_height
                if first_page._ic_position == -self.widget_height and self.scroll_direction:
                    self.emit('offlimit', 'start')

        upper = self.canvas_height
        if last_page := self.get_last_child():
            if last_page.status == 'offlimit' and self.scroll_direction in (None, Gtk.DirectionType.DOWN):
                # Offlimit end
                upper -= self.widget_height
                if last_page._ic_position == self.widget_height and self.scroll_direction:
                    self.emit('offlimit', 'end')

        self.vadjustment.configure(
            max(min(self.vadjustment.props.value + self.scroll_adjusting_delta, self.max_vadjustment_value), 0),
            lower,
            upper,
            self.widget_height * 0.1,
            self.widget_height * 0.9,
            min(self.widget_height, self.canvas_height)
        )
        self.scroll_adjusting_delta = 0

    def connect_signals(self):
        if self.vadjustment:
            self.vadjustment_value_changed_handler_id = self.vadjustment.connect('value-changed', lambda adj: self.queue_allocate())

        # Keyboard navigation
        self.key_pressed_handler_id = self.pager.window.controller_key.connect('key-pressed', self.on_key_pressed)

    def disconnect_signals(self):
        self.vadjustment.disconnect(self.vadjustment_value_changed_handler_id)
        self.pager.window.controller_key.disconnect(self.key_pressed_handler_id)

    def dispose(self):
        self.disconnect_signals()
        self.remove_controllers()
        self.clear()

    def do_size_allocate(self, width, height, baseline, adjusted=False):
        # Keep scrolling position when resized horizontally
        if self.prev_width and self.prev_width != width:
            self.vadjustment.props.value = width * self.vadjustment.props.value / self.prev_width
            self.prev_width = width
            self.do_size_allocate(width, height, baseline, adjusted)
            return

        self.prev_width = width
        self.current_page_top = None
        self.current_page_bottom = None

        page = self.get_first_child()
        if page is None:
            # Empty! Probably in destruction.
            return

        size = 0
        scroll_offset = self.vadjustment.props.value + self.scroll_adjusting_delta

        while page:
            page._ic_position = size - scroll_offset

            if page.picture and not page.error:
                _, page_height, _, _ = page.picture.do_measure(Gtk.Orientation.VERTICAL, width)
            else:
                page_height = height

            page._ic_height = page_height

            if not self.current_page_top and page._ic_position <= 0 and page._ic_position + page._ic_height > 0:
                self.current_page_top = page
            if not self.current_page_bottom and page._ic_position <= height and page._ic_position + page._ic_height > height:
                self.current_page_bottom = page

            if page.status in ('rendering', 'allocable') and not page.activity_indicator.spinner.get_spinning():
                visible = page._ic_position >= 0 and page._ic_position < height
                visible |= page._ic_position + page_height > 0 and page._ic_position + page_height <= height
                visible |= page._ic_position < 0 and page._ic_position + page_height > height
                if visible:
                    page.activity_indicator.start()

            position = Graphene.Point()
            position.init(0, page._ic_position)

            transform = Gsk.Transform.translate(Gsk.Transform.new(), position)
            page.allocate(width, page_height, baseline, transform)

            size += page_height
            page = page.get_next_sibling()

        self.canvas_height = size
        self.configure_adjustments()
        self.is_scroll_adjusting = False

        self.add_or_remove_page()

    def on_gesture_click_released(self, _gesture, n_press, x, y):
        if n_press != 1:
            return

        if x < self.canvas_width / 3:
            # First third: scroll up
            self.scroll_by_increment(-self.vadjustment.props.page_size * SCROLL_CLICK_PERCENTAGE)
        elif x > 2 * self.canvas_width / 3:
            # Last third: scroll down
            self.scroll_by_increment(self.vadjustment.props.page_size * SCROLL_CLICK_PERCENTAGE)
        else:
            # Second third: controls zone
            self.emit('controls-zone-clicked')

    def on_gesture_drag_begin(self, _controller, _start_x, _start_y):
        self.scroll_drag_offset = 0

        # If deceleration is not cancelled gestures become buggy!
        # So, no deceleration on touch screen :-(
        self.cancel_deceleration()

    def on_gesture_drag_end(self, _controller, _offset_x, _offset_y):
        self.cancel_deceleration()

    def on_gesture_drag_update(self, _controller, _offset_x, offset_y):
        if abs(offset_y) < 1:
            # Ignore drags that are only clicks
            # Occurs when a `Retry` button is activated
            return

        self.scroll_direction = Gtk.DirectionType.UP if offset_y > 0 else Gtk.DirectionType.DOWN
        self.vadjustment.props.value -= (offset_y - self.scroll_drag_offset) * SCROLL_DRAG_FACTOR
        self.scroll_drag_offset = offset_y

        self.gesture_drag.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.pager.window.page != self.pager.reader.props.tag:
            return Gdk.EVENT_PROPAGATE

        modifiers = Gtk.accelerator_get_default_mod_mask()
        if (state & modifiers) != 0:
            return Gdk.EVENT_PROPAGATE

        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down, Gdk.KEY_Right, Gdk.KEY_KP_Right, Gdk.KEY_space):
            self.emit('keyboard-navigation')
            self.scroll_by_type(Gtk.ScrollType.STEP_DOWN)
            return Gdk.EVENT_STOP

        elif keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up, Gdk.KEY_Left, Gdk.KEY_KP_Left):
            self.emit('keyboard-navigation')
            self.scroll_by_type(Gtk.ScrollType.STEP_UP)
            return Gdk.EVENT_STOP

        elif keyval == Gdk.KEY_Page_Down:
            self.emit('keyboard-navigation')
            self.scroll_by_increment(self.vadjustment.props.page_size * SCROLL_CLICK_PERCENTAGE)
            return Gdk.EVENT_STOP

        elif keyval == Gdk.KEY_Page_Up:
            self.emit('keyboard-navigation')
            self.scroll_by_increment(-self.vadjustment.props.page_size * SCROLL_CLICK_PERCENTAGE)
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_page_rendered(self, page, update, retry):
        if not update:
            page.activity_indicator.stop()

            if retry:
                # No idea why this reset is necessary
                self.gesture_drag.reset()

    def on_page_status_changed(self, page, _status, init_height):
        if page.status not in ('allocable', 'offlimit'):
            return

        if page.status == 'allocable':
            # As soon as page height is known
            # Adjust scroll value if page has been prepended and still above scroll position
            if page._ic_position < 0:
                _, page_height, _, _ = page.picture.do_measure(Gtk.Orientation.VERTICAL, self.get_width())
                self.scroll_adjusting_delta = page_height - init_height
                self.queue_allocate()
        else:
            # Offlimit: vadjustment lower or upper value must be updated
            self.configure_adjustments()
            self.is_scroll_adjusting = False

    def on_scroll(self, _controller, _dx, dy):
        self.is_scroll_decelerating = False
        self.scroll_direction = Gtk.DirectionType.UP if dy < 0 else Gtk.DirectionType.DOWN

        # Scroll deltas unit Gdk.ScrollUnit.SURFACE occurs with touchpads under Wayland
        unit_multiple_factor = 1 if self.controller_scroll.get_unit() == Gdk.ScrollUnit.SURFACE else self.vadjustment.props.step_increment
        self.vadjustment.props.value = min(
            self.vadjustment.props.upper - self.vadjustment.props.page_size,
            max(
                0,
                self.vadjustment.props.value + dy * unit_multiple_factor
            )
        )

        return Gdk.EVENT_STOP

    def on_scroll_decelerate(self, _controller, vx, vy):
        self.is_scroll_decelerating = True

    def prepend(self, page):
        """ Adds a new page at start """
        self.is_scroll_adjusting = True

        page._ic_height = self.get_height()
        page._ic_position = self.get_first_child()._ic_position - page._ic_height

        page.insert_before(self, self.get_first_child())
        self.vadjustment.props.value += page._ic_height

        page.connect('rendered', self.on_page_rendered)
        page.connect('notify::status', self.on_page_status_changed, page._ic_height)
        page.render()

    def print(self):
        print('\n===============================')
        count = 0
        page = self.get_first_child()
        while page:
            index = page.index + 1 or '?'
            chapter_title = page.chapter.title if page.chapter else '?'
            print(f'{count + 1:2}: p={int(page._ic_position):5} | h={int(page._ic_height):5} | {index:3} {chapter_title}')
            count += 1
            page = page.get_next_sibling()
        print('================================')

    def remove(self, page):
        """ Removes a page """
        page.dispose()

        if self.scroll_direction == Gtk.DirectionType.DOWN:
            self.vadjustment.props.value -= page._ic_height

    def remove_controllers(self):
        self.remove_controller(self.controller_scroll)
        self.remove_controller(self.gesture_click)
        self.pager.remove_controller(self.gesture_drag)

    def scroll_by_increment(self, increment, duration=500):
        self.is_scroll_decelerating = False
        self.is_scroll_by_increment = True
        self.scroll_direction = Gtk.DirectionType.UP if increment < 0 else Gtk.DirectionType.DOWN

        start = self.vadjustment.props.value
        end = start + increment

        clock = self.get_frame_clock()
        start_time = clock.get_frame_time()
        end_time = start_time + duration * 1000

        def ease_out_cubic(t):
            return (t - 1) ** 3 + 1

        def on_finish():
            self.is_scroll_by_increment = False

            self.queue_allocate()

        def tick_callback(_self, clock):
            now = clock.get_frame_time()

            if now < end_time and self.vadjustment.props.value != end:
                t = (now - start_time) / (end_time - start_time)
                t = ease_out_cubic(t)
                self.vadjustment.props.value = start + t * (end - start)

                return GLib.SOURCE_CONTINUE

            self.vadjustment.props.value = end

            GLib.idle_add(on_finish)

            return GLib.SOURCE_REMOVE

        self.add_tick_callback(tick_callback)

    def scroll_by_type(self, type):
        self.is_scroll_decelerating = False
        self.scroll_direction = Gtk.DirectionType.UP if type == Gtk.ScrollType.STEP_UP else Gtk.DirectionType.DOWN

        # Assume parent is a Gtk.ScrolledWindow
        self.get_parent().emit('scroll-child', type, False)
