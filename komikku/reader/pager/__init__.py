# Copyright (C) 2019-2023 Valéry Febvre
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

from komikku.reader.pager.page import Page
from komikku.utils import log_error_traceback


class BasePager:
    autohide_controls = True
    default_double_click_time = Gtk.Settings.get_default().get_property('gtk-double-click-time')
    zoom = dict(active=False)

    def __init__(self, reader):
        self.reader = reader
        self.window = reader.window

        # Keyboard navigation
        self.key_pressed_handler_id = self.window.controller_key.connect('key-pressed', self.on_key_pressed)

        # Controller to track pointer motion: used to hide pointer during keyboard navigation
        self.controller_motion = Gtk.EventControllerMotion.new()
        self.add_controller(self.controller_motion)
        self.controller_motion.connect('motion', self.on_pointer_motion)

        # Gesture click controller: layout navigation, zoom
        # Note: Should be added to desired widget in derived class
        self.gesture_click = Gtk.GestureClick.new()
        self.gesture_click.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        self.gesture_click.set_exclusive(True)
        self.gesture_click.set_button(1)
        self.gesture_click.connect('released', self.on_btn_clicked)

        # Gesture zoom controller
        # Note: Should be added to desired widget in derived class
        self.gesture_zoom = Gtk.GestureZoom.new()
        self.gesture_zoom.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        self.gesture_zoom.connect('begin', self.on_gesture_zoom_begin)
        self.gesture_zoom.connect('end', self.on_gesture_zoom_end)
        self.gesture_zoom.connect('scale-changed', self.on_gesture_zoom_scale_changed)

    @property
    @abstractmethod
    def pages(self):
        raise NotImplementedError()

    @property
    @abstractmethod
    def size(self):
        raise NotImplementedError()

    @abstractmethod
    def add_page(self, position):
        raise NotImplementedError()

    @abstractmethod
    def clear(self):
        raise NotImplementedError()

    def crop_pages_borders(self):
        for page in self.pages:
            if page.status == 'rendered' and page.error is None:
                page.set_image()

    def dispose(self):
        self.window.controller_key.disconnect(self.key_pressed_handler_id)

    @abstractmethod
    def goto_page(self, page_index):
        raise NotImplementedError()

    def hide_cursor(self):
        GLib.timeout_add(1000, self.set_cursor, Gdk.Cursor.new_from_name('none'))

    @abstractmethod
    def init(self):
        raise NotImplementedError()

    @abstractmethod
    def on_btn_clicked(self, _widget, event):
        raise NotImplementedError()

    @abstractmethod
    def on_gesture_zoom_begin(self, _gesture, _sequence):
        raise NotImplementedError()

    @abstractmethod
    def on_gesture_zoom_end(self, _gesture, _sequence):
        raise NotImplementedError()

    @abstractmethod
    def on_gesture_zoom_scale_changed(self, _gesture, scale):
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

    @abstractmethod
    def on_page_rendered(self, page, retry):
        raise NotImplementedError()

    @abstractmethod
    def on_single_click(self, x, _y):
        raise NotImplementedError()

    def rescale_pages(self):
        self.zoom['active'] = False

        for page in self.pages:
            page.rescale()

    def resize_pages(self, _pager=None, _orientation=None):
        self.zoom['active'] = False

        for page in self.pages:
            page.resize()

    def save_progress(self, read_pages):
        """Save reading progress

        Accepts one or several pages which can be from different chapters"""

        if type(read_pages) != list:
            read_pages = [read_pages]

        for page in read_pages.copy():
            if page.status == 'disposed':
                # Page is no longer present in pager
                read_pages.remove(page)

        if not read_pages:
            return GLib.SOURCE_REMOVE

        for page in read_pages.copy():
            # Loop as long as a page rendering is not ended
            if page.status == 'rendering':
                return GLib.SOURCE_CONTINUE

            if page.status != 'rendered' or page.error is not None:
                read_pages.remove(page)

        if not read_pages:
            return GLib.SOURCE_REMOVE

        read_chapters = dict()
        for page in read_pages:
            chapter = page.chapter
            if chapter.id not in read_chapters:
                read_chapters[chapter.id] = dict(
                    chapter=chapter,
                    pages=[],
                )
            read_chapters[chapter.id]['pages'].append(page.index)

        # Update manga last read time
        self.reader.manga.update(dict(last_read=datetime.datetime.utcnow()))

        # Update chapters read progress
        for read_chapter in read_chapters.values():
            chapter = read_chapter['chapter']
            pages = read_chapter['pages']

            if not chapter.read:
                # Add chapter to the list of chapters consulted
                # Used by Card page to update chapters rows
                self.reader.chapters_consulted.add(chapter)

                read_progress = chapter.read_progress
                if read_progress is None:
                    # Init and fill with '0'
                    read_progress = '0' * len(chapter.pages)

                # Mark current page as read
                for index in pages:
                    read_progress = read_progress[:index] + '1' + read_progress[index + 1:]
                chapter_is_read = '0' not in read_progress
                if chapter_is_read:
                    read_progress = None

                # Update chapter
                chapter.update(dict(
                    last_page_read_index=page.index if not chapter_is_read else None,
                    last_read=datetime.datetime.utcnow(),
                    read_progress=read_progress,
                    read=chapter_is_read,
                    recent=0,
                ))

                for index in pages:
                    self.sync_progress_with_server(chapter, index)

        return GLib.SOURCE_REMOVE

    @abstractmethod
    def scroll_to_direction(self, direction):
        raise NotImplementedError()

    def sync_progress_with_server(self, chapter, index):
        # Sync reading progress with server if function is supported
        def run():
            try:
                res = chapter.manga.server.update_chapter_read_progress(
                    dict(
                        page=index + 1,
                        completed=chapter.read,
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

    btn_clicked_timeout_id = None

    def __init__(self, reader):
        Adw.Bin.__init__(self)
        BasePager.__init__(self, reader)

        self.carousel = Adw.Carousel()
        self.carousel.set_scroll_params(Adw.SpringParams.new(1, 0.05, 10))  # guesstimate
        self.carousel.set_allow_long_swipes(False)
        self.carousel.set_reveal_duration(0)
        self.set_child(self.carousel)

        self.carousel.connect('notify::orientation', self.resize_pages)
        self.page_changed_handler_id = self.carousel.connect('page-changed', self.on_page_changed)

        # Scroll controller
        self.controller_scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.add_controller(self.controller_scroll)
        self.controller_scroll.connect('scroll', self.on_scroll)

        # Gesture click controller: layout navigation, zoom
        self.carousel.add_controller(self.gesture_click)

        # Gesture zoom controller
        self.carousel.add_controller(self.gesture_zoom)

    @GObject.Property(type=bool, default=True)
    def interactive(self):
        return self._interactive

    @interactive.setter
    def interactive(self, value):
        self._interactive = value
        self.carousel.set_interactive(value)

    @property
    def page_change_in_progress(self):
        return self.carousel.get_progress() != 1

    @property
    def pages(self):
        for index in range(self.carousel.get_n_pages()):
            yield self.carousel.get_nth_page(index)

    @property
    def size(self):
        return self.get_allocation()

    def add_page(self, position):
        if position == 'start':
            self.carousel.get_nth_page(2).dispose()

            page = self.carousel.get_nth_page(0)
            direction = 1 if self.reader.reading_mode == 'right-to-left' else -1
            new_page = Page(self, page.chapter, page.index + direction)
            self.carousel.prepend(new_page)

            new_page.connect('rendered', self.on_page_rendered)
            new_page.scrolledwindow.connect('edge-overshot', self.on_page_edge_overshotted)
            new_page.render()
        else:
            page = self.carousel.get_nth_page(2)

            def append_after_remove(*args):
                if self.carousel.get_position() != 1:
                    return

                self.carousel.disconnect(position_handler_id)

                direction = -1 if self.reader.reading_mode == 'right-to-left' else 1
                new_page = Page(self, page.chapter, page.index + direction)
                self.carousel.append(new_page)

                new_page.connect('rendered', self.on_page_rendered)
                new_page.scrolledwindow.connect('edge-overshot', self.on_page_edge_overshotted)
                new_page.render()

            # Hack: use a workaround to not lose position
            # Cf. issue https://gitlab.gnome.org/GNOME/libadwaita/-/issues/430
            position_handler_id = self.carousel.connect('notify::position', append_after_remove)

            self.carousel.get_nth_page(0).dispose()

    def adjust_page_placement(self, page):
        # Only if page is scrollable
        if not page.scrollable:
            return

        if self.reader.reading_mode == 'vertical':
            adj = page.scrolledwindow.get_vadjustment()
        else:
            adj = page.scrolledwindow.get_hadjustment()

        pages = list(self.pages)
        if pages.index(page) > pages.index(self.current_page):
            adj.set_value(0)
        else:
            adj.set_value(adj.get_upper() - adj.get_page_size())

        if self.reader.reading_mode == 'vertical':
            # Center page horizontally
            hadj = page.scrolledwindow.get_hadjustment()
            hadj.set_value((hadj.get_upper() - hadj.get_page_size()) / 2)

    def clear(self):
        page = self.carousel.get_first_child()
        while page:
            next_page = page.get_next_sibling()
            page.dispose()
            page = next_page

    def dispose(self):
        self.carousel.disconnect(self.page_changed_handler_id)
        BasePager.dispose(self)
        self.clear()

    def goto_page(self, index):
        if self.carousel.get_nth_page(0).index == index and self.carousel.get_nth_page(0).chapter == self.current_page.chapter:
            self.scroll_to_direction('left', False)
        elif self.carousel.get_nth_page(2).index == index and self.carousel.get_nth_page(2).chapter == self.current_page.chapter:
            self.scroll_to_direction('right', False)
        else:
            self.init(self.current_page.chapter, index)

    def init(self, chapter, page_index=None):
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

        def init_pages():
            # Center page
            center_page = Page(self, chapter, page_index)
            self.carousel.append(center_page)
            center_page.connect('rendered', self.on_page_rendered)
            center_page.scrolledwindow.connect('edge-overshot', self.on_page_edge_overshotted)
            center_page.render()
            self.current_page = center_page

            # Left page
            left_page = Page(self, chapter, page_index + direction)
            self.carousel.prepend(left_page)
            left_page.connect('rendered', self.on_page_rendered)
            left_page.scrolledwindow.connect('edge-overshot', self.on_page_edge_overshotted)

            # Right page
            right_page = Page(self, chapter, page_index - direction)
            self.carousel.append(right_page)
            right_page.connect('rendered', self.on_page_rendered)
            right_page.scrolledwindow.connect('edge-overshot', self.on_page_edge_overshotted)

            left_page.render()
            right_page.render()

            GLib.idle_add(self.scroll_to_page, center_page, False, False)

        # Hack: use a `GLib.timeout_add + GLib.idle_add` to add first pages in carousel
        # Without it, the `scroll_to` (with velocity=0) doesn't work!
        # Cf. issue https://gitlab.gnome.org/GNOME/libadwaita/-/issues/457
        GLib.timeout_add(150, init_pages)

    def on_btn_clicked(self, _gesture, n_press, x, y):
        if n_press == 1 and self.btn_clicked_timeout_id is None:
            # Schedule single click event to be able to detect double click
            self.btn_clicked_timeout_id = GLib.timeout_add(self.default_double_click_time, self.on_single_click, x, y)

        elif n_press == 2:
            # Remove scheduled single click event
            if self.btn_clicked_timeout_id:
                GLib.source_remove(self.btn_clicked_timeout_id)
                self.btn_clicked_timeout_id = None

            page = self.current_page
            hadj = page.scrolledwindow.get_hadjustment()
            vadj = page.scrolledwindow.get_vadjustment()

            if not self.zoom['active']:
                if page.status != 'rendered' or page.error is not None or page.animated:
                    return

                self.interactive = False
                self.zoom['start_width'] = page.picture.width
                self.zoom['start_height'] = page.picture.height
                self.zoom['start_hadj_value'] = hadj.get_value()
                self.zoom['start_vadj_value'] = vadj.get_value()
                self.zoom['x'] = x
                self.zoom['y'] = y
                self.zoom['active'] = True

                self.zoom_page()
            else:
                self.zoom['active'] = False
                self.interactive = True

                hadj.set_value(self.zoom['start_hadj_value'])
                vadj.set_value(self.zoom['start_vadj_value'])

                page.set_image([self.zoom['start_width'], self.zoom['start_height']])

        return Gdk.EVENT_STOP

    def on_gesture_zoom_end(self, _gesture, _sequence):
        page = self.current_page
        if page.picture.width == self.zoom['orig_width'] and page.picture.height == self.zoom['orig_height']:
            self.zoom['active'] = False
            self.interactive = True

        self.gesture_zoom.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_gesture_zoom_begin(self, _gesture, _sequence):
        page = self.current_page

        if page.status != 'rendered' or page.error is not None or page.animated:
            return

        self.interactive = False

        if not self.zoom['active']:
            self.zoom['orig_width'] = page.picture.width
            self.zoom['orig_height'] = page.picture.height
        self.zoom['start_width'] = page.picture.width
        self.zoom['start_height'] = page.picture.height

        _active, x, y = self.gesture_zoom.get_bounding_box_center()
        self.zoom['x'] = x
        self.zoom['y'] = y
        self.zoom['start_hadj_value'] = page.scrolledwindow.get_hadjustment().get_value()
        self.zoom['start_vadj_value'] = page.scrolledwindow.get_vadjustment().get_value()
        self.zoom['active'] = True

        self.gesture_zoom.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_gesture_zoom_scale_changed(self, _gesture, scale):
        self.zoom_page(scale, True)

        self.gesture_zoom.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != 'reader':
            return Gdk.EVENT_PROPAGATE

        if self.page_change_in_progress:
            return Gdk.EVENT_PROPAGATE

        modifiers = Gtk.accelerator_get_default_mod_mask()
        if (state & modifiers) != 0:
            return Gdk.EVENT_PROPAGATE

        if keyval == Gdk.KEY_space:
            keyval = Gdk.KEY_Left if self.reader.reading_mode == 'right-to-left' else Gdk.KEY_Right

        page = self.current_page
        if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left, Gdk.KEY_Right, Gdk.KEY_KP_Right):
            # Hide mouse cursor when using keyboard navigation
            self.hide_cursor()

            hadj = page.scrolledwindow.get_hadjustment()

            if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
                if hadj.get_value() == 0 and self.interactive:
                    self.scroll_to_direction('left')
                    return Gdk.EVENT_STOP

                page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_LEFT, False)
                return Gdk.EVENT_STOP

            if hadj.get_value() + hadj.get_page_size() == hadj.get_upper() and self.interactive:
                self.scroll_to_direction('right')
                return Gdk.EVENT_STOP

            page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_RIGHT, False)
            return Gdk.EVENT_STOP

        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up, Gdk.KEY_Down, Gdk.KEY_KP_Down):
            # Hide mouse cursor when using keyboard navigation
            self.hide_cursor()

            vadj = page.scrolledwindow.get_vadjustment()

            if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
                if self.reader.reading_mode == 'vertical' and vadj.get_value() + vadj.get_page_size() == vadj.get_upper():
                    self.scroll_to_direction('right')
                    return Gdk.EVENT_STOP

                # If image height is greater than viewport height, arrow keys should scroll page down
                # Emit scroll signal: one step down
                page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_DOWN, False)
                return Gdk.EVENT_STOP

            if self.reader.reading_mode == 'vertical' and vadj.get_value() == 0:
                self.scroll_to_direction('left')

                return Gdk.EVENT_STOP

            # If image height is greater than viewport height, arrow keys should scroll page up
            # Emit scroll signal: one step up
            page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_UP, False)
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_page_changed(self, _carousel, index):
        # index != 1 except when:
        # - come back from inaccessible chapter page
        # - partial/incomplete mouse drag
        # - come back from offlimit page

        page = self.carousel.get_nth_page(index)
        self.current_page = page

        if page.status == 'offlimit':
            GLib.idle_add(self.scroll_to_page, self.carousel.get_nth_page(1), True, False)

            if page.index == -1:
                message = _('There is no previous chapter.')
            else:
                message = _('It was the last chapter.')
            self.window.show_notification(message, 2)

            return

        if index != 1:
            if self.autohide_controls:
                # Hide controls
                self.reader.toggle_controls(False)
            else:
                self.autohide_controls = True

            # Hide page numbering if chapter pages are not yet known
            if not page.loadable:
                self.reader.update_page_numbering()

        GLib.idle_add(self.update, page, index)
        GLib.timeout_add(100, self.save_progress, page)

    def on_page_edge_overshotted(self, _scrolledwindow, position):
        if not self.interactive:
            return

        # When page is scrollable, scroll events are consumed, so we must manage page changes in place of Adw.Carousel
        if self.reader.reading_mode in ('right-to-left', 'left-to-right'):
            # RTL/LTR
            if position in (Gtk.PositionType.LEFT, Gtk.PositionType.RIGHT):
                self.scroll_to_direction('left' if position == Gtk.PositionType.LEFT else 'right')
        else:
            # Vertical
            if position in (Gtk.PositionType.TOP, Gtk.PositionType.BOTTOM):
                self.scroll_to_direction('left' if position == Gtk.PositionType.TOP else 'right')

    def on_page_rendered(self, page, retry):
        if page.status == 'disposed':
            return

        if not retry:
            GLib.idle_add(self.adjust_page_placement, page)
            return

        self.on_page_changed(None, self.carousel.get_position())

    def on_scroll(self, _controller, dx, dy):
        if not self.interactive:
            return Gdk.EVENT_PROPAGATE

        page = self.current_page
        if page.scrollable:
            # Page is scrollable (horizontally or vertically)

            # Scroll events are consumed, so we must manage page changes in place of Adw.Carousel
            # In the scroll axis, page changes will be handled via 'edge-overshot' page event

            if page.hscrollable and not page.vscrollable and dy:
                if self.reader.reading_mode == 'right-to-left':
                    # Use vertical scroll event to scroll horizontally in page
                    page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_LEFT if dy > 0 else Gtk.ScrollType.STEP_RIGHT, False)
                    return Gdk.EVENT_STOP

                elif self.reader.reading_mode == 'left-to-right':
                    # Use vertical scroll event to scroll horizontally in page
                    page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_RIGHT if dy > 0 else Gtk.ScrollType.STEP_LEFT, False)
                    return Gdk.EVENT_STOP

                elif self.reader.reading_mode == 'vertical' and dx == 0:
                    # Allow vertical navigation when page is horizontally scrollable
                    self.scroll_to_direction('left' if dy < 0 else 'right')
                    return Gdk.EVENT_STOP

            elif page.vscrollable and not page.hscrollable and dx:
                if self.reader.reading_mode in ('right-to-left', 'left-to-right') and dy == 0:
                    # Allow horizontal navigation when page is vertically scrollable
                    self.scroll_to_direction('left' if dx < 0 else 'right')
                    return Gdk.EVENT_STOP

        else:
            # Page is not scrollable

            if self.reader.reading_mode == 'right-to-left' and dy and dx == 0:
                # Navigation must be inverted in RTL reading mode
                # Do page change in the place of Adw.carousel
                self.scroll_to_direction('left' if dy > 0 else 'right')
                return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_single_click(self, x, _y):
        self.btn_clicked_timeout_id = None

        if x < self.reader.size.width / 3:
            # 1st third of the page
            if not self.interactive:
                return False

            self.scroll_to_direction('left')
        elif x > 2 * self.reader.size.width / 3:
            # Last third of the page
            if not self.interactive:
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

        for page in self.pages:
            self.adjust_page_placement(page)

    def scroll_to_direction(self, direction, autohide_controls=True):
        if self.page_change_in_progress:
            return

        position = self.carousel.get_position()
        page = None

        if direction == 'left' and position > 0:
            page = self.carousel.get_nth_page(position - 1)
        elif direction == 'right' and position < 2:
            page = self.carousel.get_nth_page(position + 1)

        if page:
            self.scroll_to_page(page, True, autohide_controls)

    def scroll_to_page(self, page, animate=True, autohide_controls=True):
        self.autohide_controls = autohide_controls
        self.carousel.scroll_to(page, animate)

    def set_orientation(self, orientation):
        self.carousel.set_orientation(orientation)

    def update(self, page, index):
        if self.window.page != 'reader' or page.status == 'disposed':
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
            self.window.show_notification(page.chapter.title, 3)
            self.reader.controls.init(page.chapter)

        if not page.loadable:
            self.window.show_notification(_('This chapter is inaccessible.'), 2)

        # Update page number and controls page slider
        self.reader.update_page_numbering(page.index + 1, len(page.chapter.pages) if page.loadable else None)
        self.reader.controls.set_scale_value(page.index + 1)

        return GLib.SOURCE_REMOVE

    def zoom_page(self, scale=2, gesture=False):
        start_width = self.zoom['start_width']
        start_height = self.zoom['start_height']
        x = self.zoom['x']
        y = self.zoom['y']

        zoom_width = int(start_width * scale)
        zoom_height = int(start_height * scale)

        if gesture:
            if zoom_width < self.zoom['orig_width']:
                zoom_width = self.zoom['orig_width']
                zoom_height = self.zoom['orig_height']

            elif self.gesture_zoom.get_device().get_source() == Gdk.InputSource.TOUCHSCREEN:
                # Move image to follow zoom position on touchscreen
                _active, x2, y2 = self.gesture_zoom.get_bounding_box_center()
                x -= x2 - x
                y -= y2 - y

        if start_width <= self.reader.size.width:
            rel_x = x - (self.reader.size.width - start_width) / 2
        else:
            rel_x = x + self.zoom['start_hadj_value']
        if start_height <= self.reader.size.height:
            rel_y = y - (self.reader.size.height - start_height) / 2
        else:
            rel_y = y + self.zoom['start_vadj_value']

        h_value = rel_x * scale - x
        v_value = rel_y * scale - y

        page = self.current_page
        hadj = page.scrolledwindow.get_hadjustment()
        vadj = page.scrolledwindow.get_vadjustment()
        hadj.configure(
            h_value,
            0,
            max(self.reader.size.width, zoom_width),
            hadj.props.step_increment,
            hadj.props.page_increment,
            self.reader.size.width
        )
        vadj.configure(
            v_value,
            0,
            max(self.reader.size.height, zoom_height),
            vadj.props.step_increment,
            vadj.props.page_increment,
            self.reader.size.height
        )

        page.set_image([zoom_width, zoom_height])
