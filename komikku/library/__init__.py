# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
from gettext import ngettext
import threading
import time

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from komikku.library.categories_list import CategoriesList
from komikku.library.thumbnail import Thumbnail
from komikku.models import Category
from komikku.models import CategoryVirtual
from komikku.models import create_db_connection
from komikku.models import Manga
from komikku.models import Settings
from komikku.models import update_rows


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/library.ui')
class LibraryPage(Adw.NavigationPage):
    __gtype_name__ = 'LibraryPage'

    left_button = Gtk.Template.Child('left_button')
    categories_togglebutton = Gtk.Template.Child('categories_togglebutton')
    title = Gtk.Template.Child('title')
    search_button = Gtk.Template.Child('search_button')
    menu_button = Gtk.Template.Child('menu_button')

    searchbar = Gtk.Template.Child('searchbar')
    searchbar_separator = Gtk.Template.Child('searchbar_separator')
    search_menu_button = Gtk.Template.Child('search_menu_button')
    search_entry = Gtk.Template.Child('searchentry')
    overlaysplitview = Gtk.Template.Child('overlaysplitview')
    stack = Gtk.Template.Child('stack')
    categories_stack = Gtk.Template.Child('categories_stack')
    categories_listbox = Gtk.Template.Child('categories_listbox')
    categories_edit_mode_buttonbox = Gtk.Template.Child('categories_edit_mode_buttonbox')
    categories_edit_mode_cancel_button = Gtk.Template.Child('categories_edit_mode_cancel_button')
    categories_edit_mode_ok_button = Gtk.Template.Child('categories_edit_mode_ok_button')
    flowbox = Gtk.Template.Child('flowbox')
    selection_mode_actionbar = Gtk.Template.Child('selection_mode_actionbar')
    selection_mode_menubutton = Gtk.Template.Child('selection_mode_menubutton')

    start_page_progressbar = Gtk.Template.Child('start_page_progressbar')
    start_page_logo_image = Gtk.Template.Child('start_page_logo_image')
    start_page_title_label = Gtk.Template.Child('start_page_title_label')
    start_page_discover_button = Gtk.Template.Child('start_page_discover_button')

    page = None
    populating = False
    selected_filters = []
    selection_mode = False
    selection_mode_range = False
    selection_mode_last_thumbnail_index = None
    thumbnails_cover_size = None

    def __init__(self, window):
        Adw.NavigationPage.__init__(self)

        self.window = window
        self.builder = window.builder
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/main.xml')
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/library_search.xml')
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/library_selection_mode.xml')

        self.selected_filters = Settings.get_default().library_selected_filters

        self.connect('shown', self.on_shown)

        # Header bar
        self.left_button.connect('clicked', self.on_left_button_clicked)
        self.menu_button.set_menu_model(self.builder.get_object('menu'))
        # Focus is lost after showing popover submenu (bug?)
        self.menu_button.get_popover().connect('closed', lambda _popover: self.menu_button.grab_focus())

        # Search
        self.search_menu_button.set_menu_model(self.builder.get_object('menu-library-search'))
        if self.selected_filters:
            self.search_menu_button.add_css_class('accent')
        self.search_entry.connect('activate', self.on_search_entry_activated)
        self.search_entry.connect('changed', self.search)
        self.searchbar.bind_property(
            'search-mode-enabled', self.search_button, 'active',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.searchbar.bind_property(
            'search-mode-enabled', self.searchbar_separator, 'visible',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.searchbar.connect_entry(self.search_entry)
        self.searchbar.set_key_capture_widget(self.window)

        # Overlay split view (provide overlay sidebar)
        self.overlaysplitview.connect('notify::show-sidebar', self.on_overlaysplitview_revealed)
        self.overlaysplitview.bind_property(
            'show-sidebar', self.categories_togglebutton, 'active',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )

        self.categories_list = CategoriesList(self)

        # Thumbnails Flowbox
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.connect('child-activated', self.on_manga_thumbnail_activated)
        self.flowbox.connect('selected-children-changed', self.update_title)
        self.flowbox.connect('unselect-all', self.leave_selection_mode)

        # Selection mode ActionBar
        self.selection_mode_menubutton.set_menu_model(self.builder.get_object('menu-library-selection-mode'))

        # Gestures for multi-selection mode
        self.window.controller_key.connect('key-pressed', self.on_key_pressed)

        self.gesture_click = Gtk.GestureClick.new()
        self.gesture_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.gesture_click.set_button(3)
        self.gesture_click.connect('released', self.on_manga_thumbnail_right_click)
        self.flowbox.add_controller(self.gesture_click)

        self.gesture_long_press = Gtk.GestureLongPress.new()
        self.gesture_long_press.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.gesture_long_press.set_touch_only(False)
        self.gesture_long_press.connect('pressed', self.on_gesture_long_press_activated)
        self.flowbox.add_controller(self.gesture_long_press)

        self.window.updater.connect('manga-updated', self.on_manga_updated)

        def _filter(thumbnail):
            manga = thumbnail.manga
            selected_category = Settings.get_default().selected_category

            if selected_category != CategoryVirtual.ALL:
                if selected_category == CategoryVirtual.UNCATEGORIZED:
                    # Virtual category 'Uncategorized' is selected
                    ret = not manga.categories
                else:
                    # Categorized
                    ret = selected_category in manga.categories
            else:
                # All
                ret = True

            if ret:
                term = self.search_entry.get_text().lower()

                # Search in name
                ret = term in manga.name.lower()

                # Search in server name
                ret = ret or term in manga.server.name.lower()

                # Search in genres (exact match)
                ret = ret or term in [genre.lower() for genre in manga.genres]

                # Optional menu filters
                if ret and 'downloaded' in self.selected_filters:
                    ret = manga.nb_downloaded_chapters > 0
                if ret and 'unread' in self.selected_filters:
                    ret = manga.nb_unread_chapters > 0
                if ret and 'recents' in self.selected_filters:
                    ret = manga.nb_recent_chapters > 0

            if not ret and thumbnail._selected:
                # Unselect thumbnail if it's selected
                self.flowbox.unselect_child(thumbnail)
                thumbnail._selected = False

            thumbnail._filtered = not ret

            return ret

        def _sort(thumbnail1, thumbnail2):
            """
            This function gets two children and has to return:
            - a negative integer if the firstone should come before the second one
            - zero if they are equal
            - a positive integer if the second one should come before the firstone
            """
            manga1 = thumbnail1.manga
            manga2 = thumbnail2.manga

            sort_order = Settings.get_default().library_sort_order
            if sort_order == 'latest-read-desc':
                if manga1.last_read > manga2.last_read:
                    return -1

                if manga1.last_read < manga2.last_read:
                    return 1

            elif sort_order == 'latest-updated-desc':
                if manga1.last_update is None or manga2.last_update is None:
                    if manga1.last_update is not None and manga2.last_update is None:
                        return -1
                    if manga1.last_update is None and manga2.last_update is not None:
                        return 1

                    # Both are None, fall back on alphabetical sorting (ascendant)
                    if manga1.name > manga2.name:
                        return 1
                    if manga1.name < manga2.name:
                        return -1

                    return 0

                if manga1.last_update > manga2.last_update:
                    return -1

                if manga1.last_update < manga2.last_update:
                    return 1

            elif sort_order == 'alphanum-asc':
                if manga1.name > manga2.name:
                    return 1

                if manga1.name < manga2.name:
                    return -1

            return 0

        self.flowbox.set_filter_func(_filter)
        self.flowbox.set_sort_func(_sort)

        self.window.navigationview.add(self)

    def add_actions(self):
        add_action = Gio.SimpleAction.new('add', None)
        add_action.connect('activate', self.on_left_button_clicked)
        self.window.application.add_action(add_action)

        # Menu actions
        update_action = Gio.SimpleAction.new('library.update', None)
        update_action.connect('activate', self.update_all)
        self.window.application.add_action(update_action)

        variant = GLib.Variant.new_string(Settings.get_default().library_sort_order)
        self.sort_order_action = Gio.SimpleAction.new_stateful('library.sort-order', variant.get_type(), variant)
        self.sort_order_action.connect('activate', self.on_sort_order_changed)
        self.window.application.add_action(self.sort_order_action)

        download_manager_action = Gio.SimpleAction.new('library.download-manager', None)
        download_manager_action.connect('activate', self.open_download_manager)
        self.window.application.add_action(download_manager_action)

        categories_editor_action = Gio.SimpleAction.new('library.categories-editor', None)
        categories_editor_action.connect('activate', self.open_categories_editor)
        self.window.application.add_action(categories_editor_action)

        history_action = Gio.SimpleAction.new('library.history', None)
        history_action.connect('activate', self.open_history)
        self.window.application.add_action(history_action)

        # Search menu actions
        search_downloaded_action = Gio.SimpleAction.new_stateful(
            'library.search.downloaded', None, GLib.Variant('b', 'downloaded' in self.selected_filters)
        )
        search_downloaded_action.connect('change-state', self.on_search_menu_action_changed)
        self.window.application.add_action(search_downloaded_action)

        search_unread_action = Gio.SimpleAction.new_stateful(
            'library.search.unread', None, GLib.Variant('b', 'unread' in self.selected_filters)
        )
        search_unread_action.connect('change-state', self.on_search_menu_action_changed)
        self.window.application.add_action(search_unread_action)

        search_recents_action = Gio.SimpleAction.new_stateful(
            'library.search.recents', None, GLib.Variant('b', 'recents' in self.selected_filters)
        )
        search_recents_action.connect('change-state', self.on_search_menu_action_changed)
        self.window.application.add_action(search_recents_action)

        # ActionBar actions in selection mode
        update_selected_action = Gio.SimpleAction.new('library.update-selected', None)
        update_selected_action.connect('activate', self.update_selected)
        self.window.application.add_action(update_selected_action)

        delete_selected_action = Gio.SimpleAction.new('library.delete-selected', None)
        delete_selected_action.connect('activate', self.delete_selected)
        self.window.application.add_action(delete_selected_action)

        download_selected_action = Gio.SimpleAction.new('library.download-selected', None)
        download_selected_action.connect('activate', self.download_selected)
        self.window.application.add_action(download_selected_action)

        mark_selected_read_action = Gio.SimpleAction.new('library.mark-selected-read', None)
        mark_selected_read_action.connect('activate', self.toggle_selected_read_status, 1)
        self.window.application.add_action(mark_selected_read_action)

        mark_selected_unread_action = Gio.SimpleAction.new('library.mark-selected-unread', None)
        mark_selected_unread_action.connect('activate', self.toggle_selected_read_status, 0)
        self.window.application.add_action(mark_selected_unread_action)

        edit_categories_selected_action = Gio.SimpleAction.new('library.edit-categories-selected', None)
        edit_categories_selected_action.connect('activate', self.edit_categories_selected)
        self.window.application.add_action(edit_categories_selected_action)

        select_all_action = Gio.SimpleAction.new('library.select-all', None)
        select_all_action.connect('activate', self.select_all)
        self.window.application.add_action(select_all_action)

    def compute_thumbnails_cover_size(self):
        default_width = Thumbnail.default_width
        default_height = Thumbnail.default_height

        container_width = self.window.get_width() or self.window.props.default_width

        if container_width / default_width != container_width // default_width:
            nb = container_width // default_width + 1
            width = container_width // nb
        else:
            width = default_width
        width -= Thumbnail.padding * 2 + Thumbnail.margin * 2

        height = (width * default_height) // default_width

        self.thumbnails_cover_size = (width, height)

    def delete_mangas(self, mangas):
        def confirm_callback():
            # Stop Downloader & Updater
            self.window.downloader.stop()
            self.window.updater.stop()

            while self.window.downloader.running or self.window.updater.running:
                time.sleep(0.1)
                continue

            # Safely delete mangas in DB
            for manga in mangas:
                manga.delete()

            # Restart Downloader & Updater
            self.window.downloader.start()
            self.window.updater.start()

            # Finally, update library
            for manga in mangas:
                self.remove_thumbnail(manga)

            if self.window.page == 'card':
                self.window.navigationview.pop()
            else:
                self.leave_selection_mode()

            if not self.flowbox.get_first_child():
                # Library is now empty
                self.populate()

        if self.window.page == 'card':
            message = _('Are you sure you want to delete this manga?')
        else:
            message = _('Are you sure you want to delete selected mangas?')
        self.window.confirm(
            _('Delete?'),
            message,
            _('Delete'),
            confirm_callback,
            confirm_appearance=Adw.ResponseAppearance.DESTRUCTIVE
        )

    def delete_selected(self, _action, _param):
        self.delete_mangas([thumbnail.manga for thumbnail in self.flowbox.get_selected_children()])

    def download_selected(self, _action, _param):
        def confirm_callback():
            chapters = []
            for thumbnail in self.flowbox.get_selected_children():
                for chapter in thumbnail.manga.chapters:
                    chapters.append(chapter)

            self.leave_selection_mode()

            self.window.downloader.add(chapters)
            self.window.downloader.start()

        message = _('Are you sure you want to download all chapters of selected mangas?')
        self.window.confirm(
            _('Download?'),
            message,
            _('Download'),
            confirm_callback,
            confirm_appearance=Adw.ResponseAppearance.SUGGESTED
        )

    def edit_categories_selected(self, _action, _param):
        # Edit categories of selected mangas
        self.categories_list.set_edit_mode(True)
        self.overlaysplitview.set_show_sidebar(True)

    def enter_selection_mode(self):
        self.selection_mode = True
        self.update_headerbar_buttons()

        self.flowbox.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.selection_mode_actionbar.set_revealed(True)

    def leave_selection_mode(self, _param=None):
        self.selection_mode = False
        self.update_headerbar_buttons()

        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        for thumbnail in self.flowbox:
            thumbnail._selected = False

        self.selection_mode_actionbar.set_revealed(False)
        self.overlaysplitview.set_show_sidebar(False)

    def on_left_button_clicked(self, action_or_button=None, _param=None):
        if not self.selection_mode:
            self.window.explorer.show()
        else:
            self.leave_selection_mode()

    def on_gesture_long_press_activated(self, _gesture, x, y):
        """Allow to enter in selection mode with a long press on a thumbnail"""
        if not self.selection_mode:
            self.enter_selection_mode()
        else:
            # Enter in 'Range' selection mode
            # Long press on a manga then long press on another to select everything in between
            self.selection_mode_range = True

        selected_thumbnail = self.flowbox.get_child_at_pos(x, y)
        self.on_manga_thumbnail_activated(None, selected_thumbnail)

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != self.props.tag:
            return Gdk.EVENT_PROPAGATE

        modifiers = state & Gtk.accelerator_get_default_mod_mask()
        if not self.selection_mode:
            # Allow to enter in selection mode with <SHIFT>+Arrow key
            arrow_keys = (
                Gdk.KEY_Up, Gdk.KEY_KP_Up,
                Gdk.KEY_Down, Gdk.KEY_KP_Down,
                Gdk.KEY_Left, Gdk.KEY_KP_Left,
                Gdk.KEY_Right, Gdk.KEY_KP_Right
            )
            if modifiers != Gdk.ModifierType.SHIFT_MASK or keyval not in arrow_keys:
                return Gdk.EVENT_PROPAGATE

            thumbnail = self.flowbox.get_focus_child() or self.flowbox.get_first_child()
            if thumbnail is not None:
                self.enter_selection_mode()
                self.on_manga_thumbnail_activated(None, thumbnail)
        else:
            if keyval == Gdk.KEY_Escape or (modifiers == Gdk.ModifierType.ALT_MASK and keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left)):
                self.leave_selection_mode()

        return Gdk.EVENT_PROPAGATE

    def on_manga_added(self, manga):
        """Called from 'Card' when user clicks on `+ Add to Library` button"""
        db_conn = create_db_connection()
        nb_mangas = db_conn.execute('SELECT count(*) FROM mangas WHERE in_library = 1').fetchone()[0]
        db_conn.close()

        if nb_mangas == 1:
            # Library was previously empty
            self.populate()
        else:
            thumbnail = Thumbnail(self, manga, *self.thumbnails_cover_size)
            self.flowbox.prepend(thumbnail)

    def on_manga_thumbnail_activated(self, _flowbox, thumbnail):
        if self.selection_mode:
            if self.selection_mode_range and self.selection_mode_last_thumbnail_index is not None:
                # Range selection mode: select all mangas between last selected manga and clicked manga
                walk_index = self.selection_mode_last_thumbnail_index
                last_index = thumbnail.get_index()

                while walk_index != last_index:
                    walk_thumbnail = self.flowbox.get_child_at_index(walk_index)
                    if walk_thumbnail and not walk_thumbnail._selected and not walk_thumbnail._filtered:
                        self.flowbox.select_child(walk_thumbnail)
                        walk_thumbnail._selected = True

                    if walk_index < last_index:
                        walk_index += 1
                    else:
                        walk_index -= 1

            self.selection_mode_range = False

            if thumbnail._selected:
                self.flowbox.unselect_child(thumbnail)
                self.selection_mode_last_thumbnail_index = None
                thumbnail._selected = False
            else:
                self.flowbox.select_child(thumbnail)
                self.selection_mode_last_thumbnail_index = thumbnail.get_index()
                thumbnail._selected = True

            if len(self.flowbox.get_selected_children()) == 0:
                self.leave_selection_mode()
        else:
            self.window.card.init(thumbnail.manga)

    def on_manga_thumbnail_right_click(self, _gesture, _n_press, x, y):
        """Allow to enter in selection mode with a right click on a thumbnail"""
        if self.selection_mode:
            return Gdk.EVENT_PROPAGATE

        thumbnail = self.flowbox.get_child_at_pos(x, y)
        if thumbnail is not None:
            self.enter_selection_mode()
            self.on_manga_thumbnail_activated(None, thumbnail)
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_manga_updated(self, _obj, manga, _result):
        self.refresh_on_manga_state_changed(manga)

    def on_overlaysplitview_revealed(self, _overlaysplitview, _param):
        if self.overlaysplitview.get_show_sidebar():
            self.categories_list.populate()
        else:
            self.categories_list.set_edit_mode(False)

    def on_resize(self):
        if self.page == 'start_page':
            return

        def do_resize():
            self.compute_thumbnails_cover_size()

            for thumbnail in self.flowbox:
                thumbnail.resize(*self.thumbnails_cover_size)

        # Wait until there are no higher priority events pending to the default main loop
        GLib.idle_add(do_resize)

    def on_search_entry_activated(self, _entry):
        """Open first manga in search when <Enter> is pressed"""
        thumbnail = self.flowbox.get_child_at_pos(0, 0)
        if thumbnail:
            self.on_manga_thumbnail_activated(None, thumbnail)

    def on_search_menu_action_changed(self, action, variant):
        value = variant.get_boolean()
        action.set_state(GLib.Variant('b', value))
        name = action.props.name.split('.')[-1]

        if value:
            self.selected_filters.add(name)
        else:
            self.selected_filters.remove(name)
        Settings.get_default().library_selected_filters = self.selected_filters

        if self.selected_filters:
            self.search_menu_button.add_css_class('accent')
        else:
            self.search_menu_button.remove_css_class('accent')

        self.flowbox.invalidate_filter()

    def on_shown(self, _page):
        if self.searchbar.get_search_mode():
            self.search_entry.grab_focus()

    def on_sort_order_changed(self, _action, variant):
        value = variant.get_string()
        if value == Settings.get_default().library_sort_order:
            return

        Settings.get_default().library_sort_order = value
        self.set_sort_order()

    def open_categories_editor(self, _action, _gparam):
        self.window.categories_editor.show()

    def open_download_manager(self, _action, _gparam):
        self.window.download_manager.show()

    def open_history(self, _action, _gparam):
        self.window.history.show()

    def populate(self):
        if self.populating:
            return True

        self.populating = True

        self.show_page('start_page')

        db_conn = create_db_connection()

        self.update_title(db_conn=db_conn)

        mangas_rows = db_conn.execute('SELECT id FROM mangas WHERE in_library = 1 ORDER BY last_read DESC').fetchall()
        db_conn.close()

        paintable = Gdk.Texture.new_from_resource('/info/febvre/Komikku/images/logo.png')
        self.start_page_logo_image.set_from_paintable(paintable)

        if len(mangas_rows) == 0:
            # Update start page title, hide loading progress bar and show 'Discover' button
            self.start_page_progressbar.set_visible(False)
            self.start_page_title_label.set_markup('<span weight="bold">' + _('Welcome to Komikku') + '</span>')
            self.start_page_discover_button.set_visible(True)

            self.populating = False

            return

        self.start_page_progressbar.set_visible(True)
        self.start_page_title_label.set_markup('<span weight="bold">' + _('Loading…') + '</span>')
        self.start_page_discover_button.set_visible(False)

        # Clear library flowbox
        thumbnail = self.flowbox.get_first_child()
        while thumbnail:
            next_thumbnail = thumbnail.get_next_sibling()
            self.flowbox.remove(thumbnail)
            thumbnail = next_thumbnail

        def run():
            db_conn = create_db_connection()

            for index, row in enumerate(mangas_rows):
                thumbnail = Thumbnail(self, Manga.get(row['id'], db_conn=db_conn), *self.thumbnails_cover_size)
                thumbnails.append(thumbnail)

                GLib.idle_add(self.start_page_progressbar.set_fraction, (index + 1) / len(mangas_rows))

            db_conn.close()
            GLib.idle_add(complete)

        def complete():
            self.show_page('flowbox')

            for thumbnail in thumbnails:
                self.flowbox.append(thumbnail)

            self.populating = False

        # Populate flowbox
        self.compute_thumbnails_cover_size()
        thumbnails = []

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def refresh_on_manga_state_changed(self, manga):
        # Update thumbnail if badges are displayed
        if Settings.get_default().library_badges:
            self.update_thumbnail(manga)

        # Update filtering if filters are selected
        if self.selected_filters:
            self.flowbox.invalidate_filter()

    def remove_thumbnail(self, manga):
        # Remove manga thumbnail in flowbox
        thumbnail = self.flowbox.get_first_child()
        while thumbnail:
            if thumbnail.manga.id == manga.id:
                self.flowbox.remove(thumbnail)
                break
            thumbnail = thumbnail.get_next_sibling()

    def search(self, _search_entry):
        self.flowbox.invalidate_filter()

    def select_all(self, _action=None, _param=None):
        if self.page != 'flowbox':
            return

        if not self.selection_mode:
            self.enter_selection_mode()

        for thumbnail in self.flowbox:
            if not thumbnail._selected and not thumbnail._filtered:
                thumbnail._selected = True
                self.flowbox.select_child(thumbnail)

    def set_sort_order(self, invalidate=True):
        self.sort_order_action.set_state(GLib.Variant('s', Settings.get_default().library_sort_order))
        if invalidate:
            self.flowbox.invalidate_sort()

    def show_page(self, name):
        if self.page == name:
            return

        self.page = name

        self.stack.set_visible_child_name(name)
        self.update_headerbar_buttons()

    def toggle_search_mode(self):
        self.searchbar.set_search_mode(not self.searchbar.get_search_mode())

    def toggle_selected_read_status(self, _action, _param, read):
        chapters_ids = []
        chapters_data = []

        self.window.activity_indicator.start()

        for thumbnail in self.flowbox.get_selected_children():
            for chapter in thumbnail.manga.chapters:
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

        self.window.activity_indicator.stop()

        if not res:
            self.window.show_notification(_('Failed to update reading status'))
        else:
            if Settings.get_default().library_badges:
                for thumbnail in self.flowbox.get_selected_children():
                    thumbnail.update()

            self.leave_selection_mode()

            if self.selected_filters:
                self.flowbox.invalidate_filter()

    def update_all(self, _action, _param):
        self.window.updater.update_library()

    def update_headerbar_buttons(self):
        if self.page == 'flowbox':
            if self.selection_mode:
                self.left_button.set_label(_('Cancel'))
                self.left_button.set_tooltip_text(_('Cancel'))
                self.search_button.set_visible(False)
                self.menu_button.set_visible(False)
            else:
                self.left_button.set_tooltip_text(_('Add New Comic'))
                self.left_button.set_icon_name('list-add-symbolic')
                self.search_button.set_visible(True)
                self.menu_button.set_visible(True)

            self.categories_togglebutton.set_visible(True)
        else:
            self.categories_togglebutton.set_visible(False)
            self.search_button.set_visible(False)
            self.menu_button.set_visible(True)

    def update_selected(self, _action, _param):
        self.window.updater.add([thumbnail.manga for thumbnail in self.flowbox.get_selected_children()])
        self.window.updater.start()

        self.leave_selection_mode()

    def update_thumbnail(self, manga):
        for thumbnail in self.flowbox:
            if thumbnail.manga.id == manga.id:
                thumbnail.update(manga)
                break

    def update_title(self, *args, db_conn=None):
        nb_selected = len(self.flowbox.get_selected_children()) if self.selection_mode else 0
        if nb_selected > 0:
            title = ngettext('{0} selected', '{0} selected', nb_selected).format(nb_selected)
        else:
            if (category_id := Settings.get_default().selected_category) != CategoryVirtual.ALL:
                if category_id == CategoryVirtual.UNCATEGORIZED:
                    title = _('Uncategorized')
                else:
                    title = Category.get(category_id, db_conn).label
            else:
                title = 'Komikku'

        self.title.set_title(title)
