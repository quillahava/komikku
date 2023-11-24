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

    def __init__(self, reader):
        self.reader = reader
        self.window = reader.window

        # Controller to track pointer motion: used to hide pointer during keyboard navigation
        self.controller_motion = Gtk.EventControllerMotion.new()
        self.add_controller(self.controller_motion)
        self.controller_motion.connect('motion', self.on_pointer_motion)

    @property
    @abstractmethod
    def pages(self):
        raise NotImplementedError()

    @property
    @abstractmethod
    def size(self):
        raise NotImplementedError()

    def crop_pages_borders(self):
        raise NotImplementedError()

    @abstractmethod
    def goto_page(self, page_index):
        raise NotImplementedError()

    def hide_cursor(self):
        GLib.timeout_add(1000, self.set_cursor, Gdk.Cursor.new_from_name('none'))

    @abstractmethod
    def init(self):
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

    def rescale_pages(self):
        for page in self.pages:
            page.rescale()

    def save_progress(self, read_pages):
        """Save reading progress

        Accepts one or several pages which can be from different chapters"""

        if not isinstance(read_pages, list):
            read_pages = [read_pages,]

        for page in read_pages.copy():
            if page.status == 'disposed':
                # Page is no longer present in pager
                read_pages.remove(page)

        for page in read_pages.copy():
            # Loop as long as a page rendering is not ended
            if page.status in ('rendering', 'allocable'):
                return GLib.SOURCE_CONTINUE

            if page.status == 'offlimit' or page.error is not None:
                read_pages.remove(page)

        read_chapters = dict()
        for page in read_pages.copy():
            chapter = page.chapter
            if chapter.id not in read_chapters:
                read_chapters[chapter.id] = dict(
                    chapter=chapter,
                    pages=[],
                )
            read_chapters[chapter.id]['pages'].append(page.index)
            read_pages.remove(page)

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

        return GLib.SOURCE_REMOVE if not read_pages else GLib.SOURCE_CONTINUE

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

    __gtype_name__ = 'Pager'

    current_chapter_id = None

    def __init__(self, reader):
        Adw.Bin.__init__(self)
        BasePager.__init__(self, reader)

        self.carousel = Adw.Carousel()
        self.carousel.set_scroll_params(Adw.SpringParams.new(1, 0.025, 10))  # guesstimate
        self.carousel.set_allow_long_swipes(False)
        self.carousel.set_reveal_duration(0)
        self.set_child(self.carousel)

        self.page_changed_handler_id = self.carousel.connect('page-changed', self.on_page_changed)

        # Keyboard navigation
        self.key_pressed_handler_id = self.window.controller_key.connect('key-pressed', self.on_key_pressed)

        # Scroll controller
        self.controller_scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.add_controller(self.controller_scroll)
        self.controller_scroll.connect('scroll', self.on_scroll)

    @GObject.Property(type=bool, default=True)
    def interactive(self):
        return self.carousel.get_interactive()

    @interactive.setter
    def interactive(self, value):
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
            if page_end := self.carousel.get_nth_page(2):
                page_end.dispose()

            page = self.carousel.get_nth_page(0)
            direction = 1 if self.reader.reading_mode == 'right-to-left' else -1
            new_page = Page(self, page.chapter, page.index + direction)
            self.carousel.prepend(new_page)

            new_page.connect('rendered', self.on_page_rendered)
            new_page.scrolledwindow.connect('edge-overshot', self.on_page_edge_overshotted)
            new_page.render()
        else:
            page = self.carousel.get_nth_page(2)

            def append_after_remove(_carousel, _position):
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

            if page_start := self.carousel.get_nth_page(0):
                page_start.dispose()

    def adjust_page_placement(self, page):
        # Only if page is scrollable
        if not page.is_scrollable:
            return

        if self.reader.reading_mode == 'vertical':
            adj = page.scrolledwindow.get_vadjustment()
        else:
            adj = page.scrolledwindow.get_hadjustment()

        pages = list(self.pages)
        if page in pages:
            if self.current_page is None or page == self.current_page:
                adj.set_value(0 if self.reader.reading_mode == 'left-to-right' else adj.get_upper() - adj.get_page_size())
            elif pages.index(page) > pages.index(self.current_page):
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

    def crop_pages_borders(self):
        for page in self.pages:
            if page.picture and page.error is None:
                page.picture.crop = self.reader.borders_crop

    def dispose(self):
        self.window.controller_key.disconnect(self.key_pressed_handler_id)
        self.carousel.disconnect(self.page_changed_handler_id)
        self.clear()

    def goto_page(self, index):
        if self.carousel.get_nth_page(0).index == index and self.carousel.get_nth_page(0).chapter == self.current_page.chapter:
            self.scroll_to_direction('left', False)
        elif self.carousel.get_nth_page(2).index == index and self.carousel.get_nth_page(2).chapter == self.current_page.chapter:
            self.scroll_to_direction('right', False)
        else:
            self.init(self.current_page.chapter, index)

    def init(self, chapter, page_index=None):
        self.current_page = None
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

            # Left page
            left_page = Page(self, chapter, page_index + direction)
            self.carousel.prepend(left_page)
            left_page.connect('rendered', self.on_page_rendered)
            left_page.scrolledwindow.connect('edge-overshot', self.on_page_edge_overshotted)
            self.scroll_to_page(center_page, False, False)

            # Right page
            right_page = Page(self, chapter, page_index - direction)
            self.carousel.append(right_page)
            right_page.connect('rendered', self.on_page_rendered)
            right_page.scrolledwindow.connect('edge-overshot', self.on_page_edge_overshotted)

            left_page.render()
            right_page.render()

        # Hack: use a `GLib.timeout_add` to add first pages in carousel
        # Without it, `scroll_to` (with animate=False) doesn't work!
        GLib.timeout_add(150, init_pages)

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != self.reader.props.tag:
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
                if hadj.get_value() == 0:
                    self.scroll_to_direction('left')
                    return Gdk.EVENT_STOP

                page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_LEFT, False)
                return Gdk.EVENT_STOP

            if hadj.get_value() + hadj.get_page_size() == hadj.get_upper():
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
        # - partial/incomplete mouse drag
        # - come back from offlimit page
        # - come back from inaccessible chapter page

        page = self.carousel.get_nth_page(index)
        self.current_page = page

        # Allow navigating if page is not scrollable, disallow otherwise
        self.interactive = not page.is_scrollable
        # Restore zooming
        page.set_allow_zooming(True)

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
        # When page is scrollable, scroll events are consumed, so we must manage page changes in place of Adw.Carousel
        if self.reader.reading_mode in ('right-to-left', 'left-to-right'):
            # RTL/LTR
            if position in (Gtk.PositionType.LEFT, Gtk.PositionType.RIGHT):
                self.scroll_to_direction('left' if position == Gtk.PositionType.LEFT else 'right')
        else:
            # Vertical
            if position in (Gtk.PositionType.TOP, Gtk.PositionType.BOTTOM):
                self.scroll_to_direction('left' if position == Gtk.PositionType.TOP else 'right')

    def on_page_rendered(self, page, update, retry):
        if page.status == 'disposed':
            return

        if not update:
            GLib.idle_add(self.adjust_page_placement, page)

        if retry:
            index = self.carousel.get_position()
            self.on_page_changed(None, index)
            return

        if page == self.current_page:
            # Allow navigating if page is not scrollable, disallow otherwise
            self.interactive = not page.is_scrollable

    def on_scroll(self, _controller, dx, dy):
        modifiers = Gtk.accelerator_get_default_mod_mask()
        state = self.controller_scroll.get_current_event_state()
        if state & modifiers == Gdk.ModifierType.CONTROL_MASK:
            # Propagate event to page: allow zoom with Ctrl + mouse wheel
            return Gdk.EVENT_PROPAGATE

        page = self.current_page
        if page.is_scrollable:
            # Page is scrollable (horizontally or vertically)

            # Scroll events are consumed, so we must manage page changes in place of Adw.Carousel
            # In the scroll axis, page changes will be handled via 'edge-overshot' page event

            if page.is_hscrollable and not page.is_vscrollable and dy:
                if self.reader.reading_mode == 'right-to-left':
                    # Use vertical scroll event to scroll horizontally in page
                    page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_LEFT if dy > 0 else Gtk.ScrollType.STEP_RIGHT, False)
                    return Gdk.EVENT_STOP

                if self.reader.reading_mode == 'left-to-right':
                    # Use vertical scroll event to scroll horizontally in page
                    page.scrolledwindow.emit('scroll-child', Gtk.ScrollType.STEP_RIGHT if dy > 0 else Gtk.ScrollType.STEP_LEFT, False)
                    return Gdk.EVENT_STOP

                if self.reader.reading_mode == 'vertical' and dx == 0:
                    # Allow vertical navigation when page is horizontally scrollable
                    self.scroll_to_direction('left' if dy < 0 else 'right')
                    return Gdk.EVENT_STOP

            elif page.is_vscrollable and not page.is_hscrollable and dx:
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

        # Just before zomm gestures (KImage widget), touchscreen swipe or touchpad scrolling events can be accidentally produced.
        # As page is being changed, zooming should not occur.
        page.set_allow_zooming(False)

        # Propagate event to Adw.Carousel
        return Gdk.EVENT_PROPAGATE

    def on_single_click(self, x, _y):
        if x < self.reader.size.width / 3:
            # 1st third of the page
            self.scroll_to_direction('left')
        elif x > 2 * self.reader.size.width / 3:
            # Last third of the page
            self.scroll_to_direction('right')
        else:
            # Center part of the page: toggle controls
            self.reader.toggle_controls()

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
        if self.window.page != 'reader' or page.status == 'disposed' or page != self.current_page:
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
