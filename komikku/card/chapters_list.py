# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
from gettext import ngettext as n_
import natsort

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from komikku.models import create_db_connection
from komikku.models import Download
from komikku.models import update_rows
from komikku.utils import html_escape


class ChapterItemWrapper(GObject.Object):
    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, chapter):
        GObject.Object.__init__(self)
        self.chapter = chapter
        self.download = None

    def emit_changed(self):
        self.emit('changed')


class ChaptersListModel(Gtk.SortListModel):
    def __init__(self, sort_func):
        self.sorter = Gtk.CustomSorter()
        self.sort_func = sort_func
        self.sorter.set_sort_func(self.sort_func)
        self.list_store = Gio.ListStore(item_type=ChapterItemWrapper)

        Gtk.SortListModel.__init__(self, model=self.list_store, sorter=self.sorter)

    def clear(self):
        self.list_store.remove_all()

    def invalidate_sort(self):
        self.sorter.set_sort_func(self.sort_func)

    def populate(self, chapters):
        items = []
        for chapter in chapters:
            items.append(ChapterItemWrapper(chapter))

        self.clear()
        self.list_store.splice(0, 0, items)


class ChaptersList:
    def __init__(self, card):
        self.card = card

        self.selection_last_selected_position = None
        self.selection_mode_range = False
        self.selection_positions = []
        self.selection_click_position = None

        self.factory = Gtk.SignalListItemFactory()
        self.factory.connect('setup', self.on_factory_setup)
        self.factory.connect('bind', self.on_factory_bind)

        self.list_model = ChaptersListModel(self.sort_func)
        self.model = Gtk.MultiSelection.new(self.list_model)
        self.selection_changed_handler_id = self.model.connect('selection-changed', self.on_selection_changed)

        self.listview = self.card.window.card_chapters_listview
        # Remove unwanted style class 'view' which changes background color in dark appearance!
        self.listview.remove_css_class('view')
        self.listview.set_factory(self.factory)
        self.listview.set_model(self.model)
        self.listview.set_show_separators(True)
        self.listview.set_single_click_activate(True)
        self.listview.connect('activate', self.on_row_activate)

        # Chapters selection mode ActionBar
        self.chapters_selection_mode_actionbar = self.card.window.card_chapters_selection_mode_actionbar
        self.card.window.card_chapters_selection_mode_menubutton.set_menu_model(self.card.builder.get_object('menu-card-selection-mode'))

        # Gesture to detect long press on mouse button 1 and enter in selection mode
        self.gesture_long_press = Gtk.GestureLongPress.new()
        self.gesture_long_press.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.gesture_long_press.set_touch_only(False)
        self.listview.add_controller(self.gesture_long_press)
        self.gesture_long_press.connect('pressed', self.on_long_press)

        self.card.window.downloader.connect('download-changed', self.update_chapter_item)

    @property
    def sort_order(self):
        return self.card.manga.sort_order or 'desc'

    def add_actions(self):
        # Menu actions in selection mode
        download_selected_chapters_action = Gio.SimpleAction.new('card.download-selected-chapters', None)
        download_selected_chapters_action.connect('activate', self.download_selected_chapters)
        self.card.window.application.add_action(download_selected_chapters_action)

        mark_selected_chapters_as_read_action = Gio.SimpleAction.new('card.mark-selected-chapters-read', None)
        mark_selected_chapters_as_read_action.connect('activate', self.toggle_selected_chapters_read_status, 1)
        self.card.window.application.add_action(mark_selected_chapters_as_read_action)

        mark_selected_chapters_as_unread_action = Gio.SimpleAction.new('card.mark-selected-chapters-unread', None)
        mark_selected_chapters_as_unread_action.connect('activate', self.toggle_selected_chapters_read_status, 0)
        self.card.window.application.add_action(mark_selected_chapters_as_unread_action)

        reset_selected_chapters_action = Gio.SimpleAction.new('card.reset-selected-chapters', None)
        reset_selected_chapters_action.connect('activate', self.reset_selected_chapters)
        self.card.window.application.add_action(reset_selected_chapters_action)

        select_all_chapters_action = Gio.SimpleAction.new('card.select-all-chapters', None)
        select_all_chapters_action.connect('activate', self.select_all)
        self.card.window.application.add_action(select_all_chapters_action)

        # Chapters menu actions
        download_chapter_action = Gio.SimpleAction.new('card.download-chapter', GLib.VariantType.new('q'))
        download_chapter_action.connect('activate', self.download_chapter)
        self.card.window.application.add_action(download_chapter_action)

        reset_chapter_action = Gio.SimpleAction.new('card.reset-chapter', GLib.VariantType.new('q'))
        reset_chapter_action.connect('activate', self.reset_chapter)
        self.card.window.application.add_action(reset_chapter_action)

        mark_chapter_as_read_action = Gio.SimpleAction.new('card.mark-chapter-read', GLib.VariantType.new('q'))
        mark_chapter_as_read_action.connect('activate', self.toggle_chapter_read_status, 1)
        self.card.window.application.add_action(mark_chapter_as_read_action)

        mark_chapter_as_unread_action = Gio.SimpleAction.new('card.mark-chapter-unread', GLib.VariantType.new('q'))
        mark_chapter_as_unread_action.connect('activate', self.toggle_chapter_read_status, 0)
        self.card.window.application.add_action(mark_chapter_as_unread_action)

        mark_previous_chapters_as_read_action = Gio.SimpleAction.new('card.mark-previous-chapters-read', GLib.VariantType.new('q'))
        mark_previous_chapters_as_read_action.connect('activate', self.set_previous_chapters_as_read)
        self.card.window.application.add_action(mark_previous_chapters_as_read_action)

    def download_chapter(self, _action, position):
        item = self.list_model.get_item(position.get_uint16())
        self.card.window.downloader.add([item.chapter], emit_signal=True)
        self.card.window.downloader.start()
        item.emit_changed()

    def download_selected_chapters(self, _action, _gparam):
        self.card.window.downloader.add(self.get_selected_chapters(), emit_signal=True)
        self.card.window.downloader.start()

        self.card.leave_selection_mode()

    def enter_selection_mode(self):
        self.chapters_selection_mode_actionbar.set_revealed(True)
        self.listview.set_single_click_activate(False)

        # Init selection with clicked row (stored in self.selection_click_position)
        self.on_selection_changed(None, None, None)

    def get_selected_chapters(self):
        chapters = []

        bitsec = self.model.get_selection()
        for index in range(bitsec.get_size()):
            position = bitsec.get_nth(index)
            if self.sort_order.endswith('desc'):
                chapters.insert(0, self.list_model.get_item(position).chapter)
            else:
                chapters.append(self.list_model.get_item(position).chapter)

        return chapters

    def leave_selection_mode(self):
        self.model.unselect_all()

        self.selection_last_selected_position = None
        self.selection_mode_range = False
        self.selection_positions = []

        self.listview.set_single_click_activate(True)
        self.chapters_selection_mode_actionbar.set_revealed(False)

    def on_factory_bind(self, _factory: Gtk.ListItemFactory, list_item: Gtk.ListItem):
        list_item.get_child().populate(list_item.get_item())

    def on_factory_setup(self, _factory: Gtk.ListItemFactory, list_item: Gtk.ListItem):
        list_item.set_child(ChaptersListRow(self.card))

    def on_long_press(self, _controller, _x, _y):
        if not self.card.selection_mode:
            self.card.enter_selection_mode()
        elif not self.selection_mode_range:
            self.selection_mode_range = True
            self.on_selection_changed(None, None, None)

    def on_row_activate(self, _listview, position):
        if self.card.selection_mode:
            # Prevent double-click row activation in selection mode
            return

        chapter = self.list_model.get_item(position).chapter
        self.card.window.reader.init(self.card.manga, chapter)

    def on_selection_changed(self, model, _position, _n_items):
        if not self.card.selection_mode:
            return

        # Here we try to allow multiple selection.
        # A short click selects or unselects a row.
        # A long press selects a range of rows (selection_last_selected_position => selection_click_position).
        # When a row is clicked, selection is lost so it must have been saved previously.
        # We build the new selection from the previous one +/- the clicked row or the previous one + a range of rows.
        if self.selection_click_position is not None:
            click_position = self.selection_click_position

            selected = Gtk.Bitset.new_empty()
            mask = Gtk.Bitset.new_empty()

            if not self.selection_mode_range:
                # Single row selection/unselection
                self.selection_click_position = None

                mask.add(click_position)
                if click_position not in self.selection_positions:
                    self.selection_positions.append(click_position)
                    self.selection_last_selected_position = click_position
                else:
                    self.selection_positions.remove(click_position)

                for position in self.selection_positions:
                    mask.add(position)
                    selected.add(position)
            else:
                # Range selection
                for position in self.selection_positions:
                    mask.add(position)

                if self.selection_last_selected_position < click_position:
                    for position in range(self.selection_last_selected_position, click_position + 1):
                        mask.add(position)
                else:
                    for position in range(click_position, self.selection_last_selected_position + 1):
                        mask.add(position)

                selected = mask

                # In selection mode range, event are emitted twice:
                # - First is a fake event `emitted` in on_long_press method
                # - Second is emitted when left click is released (in this case, model is not None)
                # State must be maintained until the second one because selection must be replayed
                if model:
                    self.selection_click_position = None
                    self.selection_last_selected_position = click_position
                    self.selection_mode_range = False

            with self.model.handler_block(self.selection_changed_handler_id):
                self.model.set_selection(selected, mask)

        self.selection_positions = []
        bitsec = self.model.get_selection()
        for index in range(bitsec.get_size()):
            self.selection_positions.append(bitsec.get_nth(index))

        number = len(self.selection_positions)
        if number:
            self.card.viewswitchertitle.set_subtitle(n_('{0} selected', '{0} selected', number).format(number))
        else:
            self.card.leave_selection_mode()

    def on_sort_order_changed(self, _action, variant):
        value = variant.get_string()
        if value == self.card.manga.sort_order:
            return

        self.card.manga.update(dict(sort_order=value))
        self.set_sort_order()

    def populate(self):
        self.list_model.populate(self.card.manga.chapters)

    def refresh(self, chapters):
        for chapter in chapters:
            self.update_chapter_item(chapter=chapter)

    def reset_selected_chapters(self, _action, _param):
        # Clear and reset selected chapters
        for chapter in self.get_selected_chapters():
            if Download.get_by_chapter_id(chapter.id) is not None:
                # Prevent reset of a chapter that is currently downloaded or scheduled for download
                continue

            chapter.reset()

        self.card.leave_selection_mode()

    def reset_chapter(self, _action, position):
        # Clear and reset chapter
        item = self.list_model.get_item(position.get_uint16())
        if Download.get_by_chapter_id(item.chapter.id) is not None:
            # Prevent reset of a chapter that is currently downloaded or scheduled for download
            return

        item.chapter.reset()
        item.emit_changed()

    def select_all(self, *args):
        if not self.card.selection_mode:
            self.card.enter_selection_mode()

        self.model.select_all()

    def set_previous_chapters_as_read(self, _action, position):
        chapters_ids = []
        chapters_data = []

        self.card.window.activity_indicator.start()

        item = self.list_model.get_item(position.get_uint16())
        rank = item.chapter.rank

        # First, update DB
        for item in self.list_model:
            chapter = item.chapter
            if chapter.rank >= rank:
                continue

            chapters_ids.append(chapter.id)
            chapters_data.append(dict(
                last_page_read_index=None,
                read_progress=None,
                read=True,
                recent=False,
            ))

        db_conn = create_db_connection()

        with db_conn:
            res = update_rows(db_conn, 'chapters', chapters_ids, chapters_data)

        db_conn.close()

        if res:
            # Then, if DB update succeeded, update chapters rows
            for item in self.list_model:
                chapter = item.chapter
                if chapter.rank >= rank:
                    continue

                chapter.last_page_read_index = None
                chapter.read = True
                chapter.recent = False

                item.emit_changed()

            self.card.window.activity_indicator.stop()
        else:
            self.card.window.activity_indicator.stop()
            self.card.window.show_notification(_('Failed to update chapters reading status'))

    def set_sort_order(self, invalidate=True):
        self.card.sort_order_action.set_state(GLib.Variant('s', self.sort_order))
        if invalidate:
            self.list_model.invalidate_sort()

    def sort_func(self, item1: ChapterItemWrapper, item2: ChapterItemWrapper, *args) -> int:
        """
        This function gets two children and has to return:
        - a negative integer if the firstone should come before the second one
        - zero if they are equal
        - a positive integer if the second one should come before the firstone
        """
        if self.sort_order in ('asc', 'desc'):
            if item1.chapter.rank > item2.chapter.rank:
                return -1 if self.sort_order == 'desc' else 1

            if item1.chapter.rank < item2.chapter.rank:
                return 1 if self.sort_order == 'desc' else -1

        elif self.sort_order in ('date-asc', 'date-desc') and item1.chapter.date and item2.chapter.date:
            if item1.chapter.date > item2.chapter.date and item1.chapter.id > item2.chapter.id:
                return -1 if self.sort_order == 'date-desc' else 1

            if item1.chapter.date < item2.chapter.date and item1.chapter.id < item2.chapter.id:
                return 1 if self.sort_order == 'date-desc' else -1

        elif self.sort_order in ('natural-asc', 'natural-desc'):
            lst = natsort.natsorted([item1.chapter.title, item2.chapter.title], alg=natsort.ns.INT | natsort.ns.IC)
            if lst[0] == item1.chapter.title:
                return 1 if self.sort_order == 'natural-desc' else -1

            return -1 if self.sort_order == 'natural-desc' else 1

        return 0

    def toggle_chapter_read_status(self, _action, position, read):
        item = self.list_model.get_item(position.get_uint16())
        chapter = item.chapter

        data = dict(
            last_page_read_index=None,
            read_progress=None,
            read=read,
            recent=False,
        )
        chapter.update(data)

        item.emit_changed()

    def toggle_selected_chapters_read_status(self, _action, _gparam, read):
        chapters_ids = []
        chapters_data = []

        self.card.window.activity_indicator.start()

        # First, update DB
        for chapter in self.get_selected_chapters():
            chapters_ids.append(chapter.id)
            chapters_data.append(dict(
                last_page_read_index=None,
                read_progress=None,
                read=read,
                recent=False,
            ))

        db_conn = create_db_connection()

        with db_conn:
            res = update_rows(db_conn, 'chapters', chapters_ids, chapters_data)

        db_conn.close()

        if res:
            # Then, if DB update succeeded, update chapters rows
            def update_chapters_rows():
                for chapter in self.get_selected_chapters():
                    chapter.last_page_read_index = None
                    chapter.read = read
                    chapter.recent = False

                    yield True

                self.card.leave_selection_mode()
                self.card.window.activity_indicator.stop()

            def run_generator(func):
                gen = func()
                GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_DEFAULT_IDLE)

            run_generator(update_chapters_rows)
        else:
            self.card.window.activity_indicator.stop()
            self.card.leave_selection_mode()
            self.card.window.show_notification(_('Failed to update chapters reading status'))

    def update_chapter_item(self, _downloader=None, download=None, chapter=None):
        """
        Update a specific chapter row
        - used when download status change (via signal from Downloader)
        - used when we come back from reader to update last page read
        """
        if chapter is None:
            chapter = download.chapter

        if self.card.window.page not in ('card', 'reader') or self.card.manga.id != chapter.manga_id:
            return

        position = -1
        for item in self.list_model:
            position += 1
            if item.chapter.id == chapter.id:
                item.chapter = chapter
                item.download = download
                item.emit_changed()
                break


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/card_chapters_list_row.ui')
class ChaptersListRow(Gtk.Box):
    __gtype_name__ = 'ChaptersListRow'

    primary_hbox = Gtk.Template.Child('primary_hbox')
    title_label = Gtk.Template.Child('title_label')
    scanlators_label = Gtk.Template.Child('scanlators_label')
    menubutton = Gtk.Template.Child('menubutton')
    secondary_hbox = Gtk.Template.Child('secondary_hbox')
    badge_label = Gtk.Template.Child('badge_label')
    subtitle_label = Gtk.Template.Child('subtitle_label')
    download_progress_progressbar = Gtk.Template.Child('download_progress_progressbar')
    download_stop_button = Gtk.Template.Child('download_stop_button')
    read_progress_label = Gtk.Template.Child('read_progress_label')

    def __init__(self, card):
        Gtk.Box.__init__(self)

        self.card = card
        self.chapter = None

        # Menu button
        self.menubutton_model = Gio.Menu()
        self.menubutton.set_menu_model(self.menubutton_model)
        self.menubutton.get_popover().connect('show', self.update_menu)

        # Gesture to detect click
        self.gesture_click = Gtk.GestureClick.new()
        self.gesture_click.set_button(0)
        self.add_controller(self.gesture_click)
        self.gesture_click.connect('pressed', self.on_button_clicked)

    @property
    def position(self):
        position = -1
        for item in self.card.chapters_list.list_model:
            position += 1
            if item.chapter.id == self.chapter.id:
                break

        return position

    def on_button_clicked(self, _gesture, _n_press, _x, _y):
        button = self.gesture_click.get_current_button()
        if button == 1:
            # Left button
            # Store row position
            self.card.chapters_list.selection_click_position = self.position
            return Gdk.EVENT_STOP

        if button == 3 and not self.card.selection_mode:
            # Right button
            # Store row position and enter selection mode
            self.card.chapters_list.selection_click_position = self.position
            self.card.enter_selection_mode()
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def populate(self, item: ChapterItemWrapper, update=False):
        self.chapter = item.chapter

        # Connect events
        if not update:
            item.connect('changed', self.populate, True)
            self.download_stop_button.connect('clicked', lambda _button, chapter: self.card.window.downloader.remove(chapter), self.chapter)

        self.title_label.set_label(self.chapter.title)
        self.title_label.remove_css_class('dim-label')
        self.title_label.remove_css_class('warning')
        if self.chapter.read:
            # Chapter reading ended
            self.title_label.add_css_class('dim-label')
        elif self.chapter.last_page_read_index is not None:
            # Chapter reading started
            self.title_label.add_css_class('warning')

        if self.chapter.scanlators:
            self.scanlators_label.set_markup(html_escape(', '.join(self.chapter.scanlators)))
            self.scanlators_label.set_visible(True)
        else:
            self.scanlators_label.set_text('')
            self.scanlators_label.set_visible(False)

        #
        # Recent badge, date, download status, page counter
        #
        show_secondary_hbox = False

        if self.chapter.recent == 1:
            self.badge_label.set_visible(True)
            show_secondary_hbox = True
        else:
            self.badge_label.set_visible(False)

        # Date + Download status (text or progress bar)
        download_status = None
        if self.chapter.downloaded:
            download_status = 'downloaded'
        else:
            if item.download is None:
                item.download = Download.get_by_chapter_id(self.chapter.id)
            if item.download:
                download_status = item.download.status

        text = [self.chapter.date.strftime(_('%m/%d/%Y'))] if self.chapter.date else []
        if download_status is not None and download_status != 'downloading':
            text.append(_(Download.STATUSES[download_status]).upper())

        self.subtitle_label.set_text(' · '.join(text))
        if text:
            show_secondary_hbox = True

        if download_status == 'downloading':
            show_secondary_hbox = True
            self.subtitle_label.set_hexpand(False)
            self.download_progress_progressbar.set_visible(True)
            self.download_stop_button.set_visible(True)
            self.read_progress_label.set_visible(False)

            # Set download progress
            self.download_progress_progressbar.set_fraction(item.download.percent / 100)
        else:
            self.subtitle_label.set_hexpand(True)
            self.download_progress_progressbar.set_visible(False)
            self.download_stop_button.set_visible(False)

            # Read progress: nb read / nb pages
            if not self.chapter.read:
                if self.chapter.last_page_read_index is not None:
                    show_secondary_hbox = True

                    # Nb read / nb pages
                    nb_pages = len(self.chapter.pages) if self.chapter.pages else '?'
                    self.read_progress_label.set_text(f'{self.chapter.last_page_read_index + 1}/{nb_pages}')
                    self.read_progress_label.set_visible(True)
                elif text:
                    self.read_progress_label.set_visible(False)
            elif text:
                self.read_progress_label.set_visible(False)

        if show_secondary_hbox:
            self.secondary_hbox.set_visible(True)
            self.primary_hbox.props.margin_top = 6
            self.primary_hbox.props.margin_bottom = 6
        else:
            self.secondary_hbox.set_visible(False)
            # Increase top and bottom margins so that all rows have the same height
            self.primary_hbox.props.margin_top = 17
            self.primary_hbox.props.margin_bottom = 16

    def update_menu(self, popover):
        if self.card.selection_mode:
            # Prevent popover to pop up in selection mode
            popover.popdown()
            return

        position = self.position
        self.menubutton_model.remove_all()

        section_menu_model = Gio.Menu()
        if not self.chapter.downloaded:
            menu_item = Gio.MenuItem.new(_('Download'))
            menu_item.set_action_and_target_value('app.card.download-chapter', GLib.Variant.new_uint16(position))
            section_menu_model.append_item(menu_item)
        if self.chapter.pages:
            menu_item = Gio.MenuItem.new(_('Clear and Reset'))
            menu_item.set_action_and_target_value('app.card.reset-chapter', GLib.Variant.new_uint16(position))
            section_menu_model.append_item(menu_item)

        section = Gio.MenuItem.new_section(None, section_menu_model)
        self.menubutton_model.append_item(section)

        section_menu_model = Gio.Menu()
        if not self.chapter.read:
            menu_item = Gio.MenuItem.new(_('Mark as Read'))
            menu_item.set_action_and_target_value('app.card.mark-chapter-read', GLib.Variant.new_uint16(position))
            section_menu_model.append_item(menu_item)
        if self.chapter.read or self.chapter.last_page_read_index is not None:
            menu_item = Gio.MenuItem.new(_('Mark as Unread'))
            menu_item.set_action_and_target_value('app.card.mark-chapter-unread', GLib.Variant.new_uint16(position))
            section_menu_model.append_item(menu_item)

        menu_item = Gio.MenuItem.new(_('Mark Previous Chapters as Read'))
        menu_item.set_action_and_target_value('app.card.mark-previous-chapters-read', GLib.Variant.new_uint16(position))
        section_menu_model.append_item(menu_item)

        section = Gio.MenuItem.new_section(None, section_menu_model)
        self.menubutton_model.append_item(section)
