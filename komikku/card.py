# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
from gettext import ngettext as n_
import natsort
import time

from gi.repository import Adw
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from komikku.models import create_db_connection
from komikku.models import Category
from komikku.models import Download
from komikku.models import Settings
from komikku.models import update_rows
from komikku.utils import create_paintable_from_file
from komikku.utils import create_paintable_from_resource
from komikku.utils import folder_size
from komikku.utils import html_escape


class Card:
    manga = None
    selection_mode = False

    def __init__(self, window):
        self.window = window
        self.builder = window.builder
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/card.xml')
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/card_selection_mode.xml')

        self.viewswitchertitle = self.window.card_viewswitchertitle
        self.viewswitcherbar = self.window.card_viewswitcherbar

        self.stack = self.window.card_stack
        self.info_box = InfoBox(self)
        self.categories_list = CategoriesList(self)
        self.chapters_list = ChaptersList(self)

        self.viewswitchertitle.connect('notify::title-visible', self.on_viewswitchertitle_title_visible)
        self.window.card_resume_button.connect('clicked', self.on_resume_button_clicked)
        self.stack.connect('notify::visible-child', self.on_page_changed)
        self.window.updater.connect('manga-updated', self.on_manga_updated)
        self.window.connect('notify::page', self.on_shown)

    def add_actions(self):
        self.delete_action = Gio.SimpleAction.new('card.delete', None)
        self.delete_action.connect('activate', self.on_delete_menu_clicked)
        self.window.application.add_action(self.delete_action)

        self.update_action = Gio.SimpleAction.new('card.update', None)
        self.update_action.connect('activate', self.on_update_menu_clicked)
        self.window.application.add_action(self.update_action)

        variant = GLib.Variant.new_string('desc')
        self.sort_order_action = Gio.SimpleAction.new_stateful('card.sort-order', variant.get_type(), variant)
        self.sort_order_action.connect('activate', self.chapters_list.on_sort_order_changed)
        self.window.application.add_action(self.sort_order_action)

        self.open_in_browser_action = Gio.SimpleAction.new('card.open-in-browser', None)
        self.open_in_browser_action.connect('activate', self.on_open_in_browser_menu_clicked)
        self.window.application.add_action(self.open_in_browser_action)

        self.chapters_list.add_actions()

    def enter_selection_mode(self, *args):
        if self.selection_mode:
            return

        self.window.left_button.set_label(_('Cancel'))
        self.window.left_button.set_tooltip_text(_('Cancel'))
        self.window.right_button_stack.hide()
        self.window.menu_button.hide()

        self.selection_mode = True
        self.chapters_list.enter_selection_mode()

        self.viewswitchertitle.set_view_switcher_enabled(False)
        self.viewswitcherbar.set_reveal(False)

    def init(self, manga, transition=True, show=True):
        # Default page is `Info` page except when we come from Explorer
        self.stack.set_visible_child_name('chapters' if self.window.page == 'explorer' else 'info')

        self.manga = manga
        # Unref chapters to force a reload
        self.manga._chapters = None

        if manga.server.status == 'disabled':
            self.window.show_notification(
                _('NOTICE\n{0} server is not longer supported.\nPlease switch to another server.').format(manga.server.name)
            )

        if show:
            self.show()

    def leave_selection_mode(self, _param=None):
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.right_button_stack.show()
        self.window.menu_button.show()

        self.chapters_list.leave_selection_mode()
        self.selection_mode = False

        self.viewswitchertitle.set_view_switcher_enabled(True)
        self.viewswitcherbar.set_reveal(True)
        self.viewswitchertitle.set_subtitle('')

    def on_delete_menu_clicked(self, action, param):
        self.window.library.delete_mangas([self.manga, ])

    def on_manga_updated(self, updater, manga, nb_recent_chapters, nb_deleted_chapters, synced):
        if self.window.page == 'card' and self.manga.id == manga.id:
            self.manga = manga

            if manga.server.sync:
                self.window.show_notification(_('Read progress synchronization with server completed successfully'))

            if nb_recent_chapters > 0 or nb_deleted_chapters > 0 or synced:
                self.chapters_list.populate()

            self.info_box.populate()

    def on_open_in_browser_menu_clicked(self, action, param):
        if url := self.manga.server.get_manga_url(self.manga.slug, self.manga.url):
            Gtk.show_uri(None, url, time.time())
        else:
            self.window.show_notification(_('Failed to get manga URL'))

    def on_page_changed(self, _stack, _param):
        if self.selection_mode and self.stack.get_visible_child_name() != 'chapters':
            self.leave_selection_mode()

    def on_resize(self):
        self.info_box.on_resize()

    def on_resume_button_clicked(self, widget):
        chapters = []
        for i in range(self.chapters_list.list_model.get_n_items()):
            chapters.append(self.chapters_list.list_model.get_item(i).chapter)

        if self.chapters_list.sort_order.endswith('desc'):
            chapters.reverse()

        chapter = None
        for chapter_ in chapters:
            if not chapter_.read:
                chapter = chapter_
                break

        if not chapter:
            chapter = chapters[0]

        self.window.reader.init(self.manga, chapter)

    def on_shown(self, _window, _page):
        # Card can only be shown from library, explorer or history
        if self.window.page != 'card' or self.window.previous_page not in ('library', 'explorer', 'history'):
            return

        # Wait page is shown (transition is ended) to populate
        # Operation is resource intensive and could disrupt page transition
        self.populate()

    def on_update_menu_clicked(self, _action, _param):
        self.window.updater.add(self.manga)
        self.window.updater.start()

    def on_viewswitchertitle_title_visible(self, _viewswitchertitle, _param):
        if self.viewswitchertitle.get_title_visible() and not self.selection_mode:
            self.viewswitcherbar.set_reveal(True)
        else:
            self.viewswitcherbar.set_reveal(False)

    def populate(self):
        self.chapters_list.set_sort_order(invalidate=False)
        self.chapters_list.populate()
        self.categories_list.populate()

    def set_actions_enabled(self, enabled):
        self.delete_action.set_enabled(enabled)
        self.update_action.set_enabled(enabled)
        self.sort_order_action.set_enabled(enabled)

    def show(self, transition=True, reset=True):
        if reset:
            self.viewswitchertitle.set_title(self.manga.name)
            self.info_box.populate()

        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.left_extra_button_stack.hide()

        self.window.right_button_stack.set_visible_child_name('card')
        self.window.right_button_stack.show()

        self.window.menu_button.set_icon_name('view-more-symbolic')
        self.window.menu_button.show()

        self.open_in_browser_action.set_enabled(self.manga.server_id != 'local')

        self.window.show_page('card', transition=transition)

    def refresh(self, chapters):
        self.info_box.refresh()
        self.chapters_list.refresh(chapters)


class CategoriesList:
    def __init__(self, card):
        self.card = card
        self.window = card.window

        self.stack = self.window.card_categories_stack
        self.listbox = self.window.card_categories_listbox

    def clear(self):
        row = self.listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            self.listbox.remove(row)
            row = next_row

    def populate(self):
        self.clear()

        db_conn = create_db_connection()
        records = db_conn.execute('SELECT * FROM categories ORDER BY label ASC').fetchall()
        db_conn.close()

        if records:
            self.stack.set_visible_child_name('list')

            for record in records:
                category = Category.get(record['id'])

                action_row = Adw.ActionRow()
                action_row.set_title(category.label)
                action_row.set_activatable(True)

                switch = Gtk.Switch.new()
                switch.set_valign(Gtk.Align.CENTER)
                switch.set_halign(Gtk.Align.CENTER)
                switch.set_active(category.id in self.card.manga.categories)
                switch.connect('notify::active', self.on_category_activated, category.id)
                action_row.add_suffix(switch)
                action_row.set_activatable_widget(switch)

                self.listbox.append(action_row)
        else:
            self.stack.set_visible_child_name('empty')

    def on_category_activated(self, switch, _param, category_id):
        self.card.manga.toggle_category(category_id, switch.get_active())

        # Update the categories list in Library, just in case it's necessary to show/hide the 'Uncategorized' category
        self.window.library.categories_list.populate()

        # Update Library if the current selected category is the activated category or the 'Uncategorized' category
        if Settings.get_default().selected_category in (-1, category_id):
            self.window.library.populate()


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

    def add_actions(self, *args):
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

    def download_chapter(self, action, position):
        item = self.list_model.get_item(position.get_uint16())
        self.card.window.downloader.add([item.chapter], emit_signal=True)
        self.card.window.downloader.start()
        item.emit_changed()

    def download_selected_chapters(self, action, param):
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

    def on_factory_bind(self, factory: Gtk.ListItemFactory, list_item: Gtk.ListItem):
        list_item.get_child().populate(list_item.get_item())

    def on_factory_setup(self, factory: Gtk.ListItemFactory, list_item: Gtk.ListItem):
        list_item.set_child(ChaptersListRow(self.card))

    def on_long_press(self, _controller, x, y):
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

    def set_previous_chapters_as_read(self, action, position):
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

    def toggle_chapter_read_status(self, action, position, read):
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

    def toggle_selected_chapters_read_status(self, action, param, read):
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

    def update_chapter_item(self, downloader=None, download=None, chapter=None):
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

        # Gesture to detect click on mouse button 3 and enter in selection mode
        self.gesture_right_click = Gtk.GestureClick.new()
        self.gesture_right_click.set_button(3)
        self.add_controller(self.gesture_right_click)
        self.gesture_right_click.connect('released', self.on_right_button_clicked)

        # Gesture to detect mouse button 1 click event and store row position
        self.gesture_left_click = Gtk.GestureClick.new()
        self.gesture_left_click.set_button(1)
        self.add_controller(self.gesture_left_click)
        self.gesture_left_click.connect('pressed', self.on_left_button_clicked)

    @property
    def position(self):
        position = -1
        for item in self.card.chapters_list.list_model:
            position += 1
            if item.chapter.id == self.chapter.id:
                break

        return position

    def on_left_button_clicked(self, _gesture, n_press, _x, _y):
        self.card.chapters_list.selection_click_position = self.position

    def on_right_button_clicked(self, _gesture, _n_press, _x, _y):
        if self.card.selection_mode:
            return

        self.card.chapters_list.selection_click_position = self.position
        self.card.enter_selection_mode()

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
            self.scanlators_label.show()
        else:
            self.scanlators_label.set_text('')
            self.scanlators_label.hide()

        #
        # Recent badge, date, download status, page counter
        #
        show_secondary_hbox = False

        if self.chapter.recent == 1:
            self.badge_label.show()
            show_secondary_hbox = True
        else:
            self.badge_label.hide()

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
            self.download_progress_progressbar.show()
            self.download_stop_button.show()
            self.read_progress_label.hide()

            # Set download progress
            self.download_progress_progressbar.set_fraction(item.download.percent / 100)
        else:
            self.subtitle_label.set_hexpand(True)
            self.download_progress_progressbar.hide()
            self.download_stop_button.hide()

            # Read progress: nb read / nb pages
            if not self.chapter.read:
                if self.chapter.last_page_read_index is not None:
                    show_secondary_hbox = True

                    # Nb read / nb pages
                    nb_pages = len(self.chapter.pages) if self.chapter.pages else '?'
                    self.read_progress_label.set_text(f'{self.chapter.last_page_read_index + 1}/{nb_pages}')
                    self.read_progress_label.show()
                elif text:
                    self.read_progress_label.hide()
            elif text:
                self.read_progress_label.hide()

        if show_secondary_hbox:
            self.secondary_hbox.show()
            self.primary_hbox.props.margin_top = 6
            self.primary_hbox.props.margin_bottom = 6
        else:
            self.secondary_hbox.hide()
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
        section = Gio.MenuItem.new_section(None, section_menu_model)
        self.menubutton_model.append_item(section)
        if not self.chapter.downloaded:
            menu_item = Gio.MenuItem.new(_('Download'))
            menu_item.set_action_and_target_value('app.card.download-chapter', GLib.Variant.new_uint16(position))
            section_menu_model.append_item(menu_item)
        if self.chapter.pages:
            menu_item = Gio.MenuItem.new(_('Clear and Reset'))
            menu_item.set_action_and_target_value('app.card.reset-chapter', GLib.Variant.new_uint16(position))
            section_menu_model.append_item(menu_item)

        section_menu_model = Gio.Menu()
        section = Gio.MenuItem.new_section(None, section_menu_model)
        self.menubutton_model.append_item(section)
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


class InfoBox:
    def __init__(self, card):
        self.card = card
        self.window = card.window

        self.cover_box = self.window.card_cover_box
        self.name_label = self.window.card_name_label
        self.cover_image = self.window.card_cover_image
        self.authors_label = self.window.card_authors_label
        self.status_server_label = self.window.card_status_server_label
        self.resume2_button = self.window.card_resume2_button
        self.genres_label = self.window.card_genres_label
        self.scanlators_label = self.window.card_scanlators_label
        self.chapters_label = self.window.card_chapters_label
        self.last_update_label = self.window.card_last_update_label
        self.synopsis_label = self.window.card_synopsis_label
        self.size_on_disk_label = self.window.card_size_on_disk_label

        self.resume2_button.connect('clicked', self.card.on_resume_button_clicked)

        self.adapt_to_width()

    def adapt_to_width(self):
        if self.window.mobile_width:
            self.cover_box.set_orientation(Gtk.Orientation.VERTICAL)
            self.cover_box.props.spacing = 12

            self.name_label.props.halign = Gtk.Align.CENTER
            self.name_label.props.justify = Gtk.Justification.CENTER

            self.status_server_label.props.halign = Gtk.Align.CENTER
            self.status_server_label.props.justify = Gtk.Justification.CENTER

            self.authors_label.props.halign = Gtk.Align.CENTER
            self.authors_label.props.justify = Gtk.Justification.CENTER

            self.resume2_button.props.halign = Gtk.Align.CENTER
        else:
            self.cover_box.set_orientation(Gtk.Orientation.HORIZONTAL)
            self.cover_box.props.spacing = 24

            self.name_label.props.halign = Gtk.Align.START
            self.name_label.props.justify = Gtk.Justification.LEFT

            self.status_server_label.props.halign = Gtk.Align.START
            self.status_server_label.props.justify = Gtk.Justification.LEFT

            self.authors_label.props.halign = Gtk.Align.START
            self.authors_label.props.justify = Gtk.Justification.LEFT

            self.resume2_button.props.halign = Gtk.Align.START

    def on_resize(self):
        self.adapt_to_width()

    def populate(self):
        cover_width = 170
        manga = self.card.manga

        self.name_label.set_text(manga.name)

        if manga.cover_fs_path is None:
            paintable = create_paintable_from_resource('/info/febvre/Komikku/images/missing_file.png', cover_width, -1)
        else:
            paintable = create_paintable_from_file(manga.cover_fs_path, cover_width, -1)
            if paintable is None:
                paintable = create_paintable_from_resource('/info/febvre/Komikku/images/missing_file.png', cover_width, -1)

        self.cover_image.set_paintable(paintable)

        authors = html_escape(', '.join(manga.authors)) if manga.authors else _('Unknown author')
        self.authors_label.set_markup(authors)

        if manga.server_id != 'local':
            self.status_server_label.set_markup(
                '{0} · <a href="{1}">{2}</a> ({3})'.format(
                    _(manga.STATUSES[manga.status]) if manga.status else _('Unknown status'),
                    manga.server.get_manga_url(manga.slug, manga.url),
                    html_escape(manga.server.name),
                    manga.server.lang.upper()
                )
            )
        else:
            self.status_server_label.set_markup(
                '{0} · {1}'.format(
                    _('Unknown status'),
                    html_escape(_('Local'))
                )
            )

        if manga.genres:
            self.genres_label.set_markup(html_escape(', '.join(manga.genres)))
            self.genres_label.get_parent().get_parent().show()
        else:
            self.genres_label.get_parent().get_parent().hide()

        if manga.scanlators:
            self.scanlators_label.set_markup(html_escape(', '.join(manga.scanlators)))
            self.scanlators_label.get_parent().get_parent().show()
        else:
            self.scanlators_label.get_parent().get_parent().hide()

        self.chapters_label.set_markup(str(len(manga.chapters)))

        if manga.last_update:
            self.last_update_label.set_markup(manga.last_update.strftime(_('%m/%d/%Y')))
            self.last_update_label.get_parent().get_parent().show()
        else:
            self.last_update_label.get_parent().get_parent().hide()

        self.set_disk_usage()

        self.synopsis_label.set_markup(html_escape(manga.synopsis) if manga.synopsis else '-')

    def refresh(self):
        self.set_disk_usage()

    def set_disk_usage(self):
        self.size_on_disk_label.set_text(folder_size(self.card.manga.path) or '-')
