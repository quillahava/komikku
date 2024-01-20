# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk

from komikku.explorer.common import get_server_default_search_filters
from komikku.explorer.search.latest_updates import ExplorerSearchStackPageLatestUpdates
from komikku.explorer.search.most_popular import ExplorerSearchStackPageMostPopular
from komikku.explorer.search.search import ExplorerSearchStackPageSearch
from komikku.explorer.search.search_global import ExplorerSearchStackPageSearchGlobal
from komikku.models import create_db_connection
from komikku.models import Manga
from komikku.models import Settings
from komikku.utils import log_error_traceback


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/explorer_search.ui')
class ExplorerSearchPage(Adw.NavigationPage):
    __gtype_name__ = 'ExplorerSearchPage'

    title_stack = Gtk.Template.Child('title_stack')
    title = Gtk.Template.Child('title')
    viewswitcher = Gtk.Template.Child('viewswitcher')
    server_website_button = Gtk.Template.Child('server_website_button')

    progressbar = Gtk.Template.Child('progressbar')
    stack = Gtk.Template.Child('stack')
    searchbar = Gtk.Template.Child('searchbar')
    searchentry = Gtk.Template.Child('searchentry')
    filter_menu_button = Gtk.Template.Child('filter_menu_button')
    search_stack = Gtk.Template.Child('search_stack')
    search_listbox = Gtk.Template.Child('search_listbox')
    search_no_results_status_page = Gtk.Template.Child('search_no_results_status_page')
    search_intro_status_page = Gtk.Template.Child('search_intro_status_page')
    search_spinner = Gtk.Template.Child('search_spinner')
    most_popular_stack = Gtk.Template.Child('most_popular_stack')
    most_popular_listbox = Gtk.Template.Child('most_popular_listbox')
    most_popular_no_results_status_page = Gtk.Template.Child('most_popular_no_results_status_page')
    most_popular_spinner = Gtk.Template.Child('most_popular_spinner')
    latest_updates_stack = Gtk.Template.Child('latest_updates_stack')
    latest_updates_listbox = Gtk.Template.Child('latest_updates_listbox')
    latest_updates_no_results_status_page = Gtk.Template.Child('latest_updates_no_results_status_page')
    latest_updates_spinner = Gtk.Template.Child('latest_updates_spinner')
    viewswitcherbar = Gtk.Template.Child('viewswitcherbar')

    page = None
    requests = {}
    search_global_mode = False
    search_filters = None
    server = None

    def __init__(self, parent):
        Adw.NavigationPage.__init__(self)

        self.parent = parent
        self.window = parent.window

        self.window.builder.add_from_resource('/info/febvre/Komikku/ui/menu/explorer_search_global_search.xml')

        self.connect('hidden', self.on_hidden)
        self.connect('shown', self.on_shown)

        self.window.controller_key.connect('key-pressed', self.on_key_pressed)

        self.page_changed_handler_id = self.stack.connect('notify::visible-child-name', self.on_page_changed)

        self.server_website_button.connect('clicked', self.on_server_website_button_clicked)
        self.searchbar.connect_entry(self.searchentry)
        self.searchbar.set_key_capture_widget(self.window)
        self.searchentry.connect('activate', self.search)
        self.searchentry.connect('search-changed', self.on_search_changed)

        self.window.breakpoint.add_setter(self.viewswitcherbar, 'reveal', True)
        self.window.breakpoint.add_setter(self.title_stack, 'visible-child', self.title)

        self.latest_updates_page = ExplorerSearchStackPageLatestUpdates(self)
        self.most_popular_page = ExplorerSearchStackPageMostPopular(self)
        self.search_page = ExplorerSearchStackPageSearch(self)
        self.search_global_page = ExplorerSearchStackPageSearchGlobal(self)

    def add_actions(self):
        self.search_global_page.add_actions()

    def can_page_be_updated_with_results(self, page, server_id):
        self.requests[page].remove(server_id)

        if self.window.page != self.props.tag:
            # Not in Explorer search page
            return False
        if server_id != self.server.id:
            # server_id is not the current server
            return False
        if page != self.page:
            # page is not the current page
            return False

        return True

    def clear(self):
        self.search_page.clear()
        self.most_popular_page.clear()
        self.latest_updates_page.clear()

        self.search_global_mode = False

    def init_search_filters(self):
        self.search_filters = get_server_default_search_filters(self.server)
        self.filter_menu_button.remove_css_class('accent')

        if self.search_global_mode:
            if self.search_global_page.selected_filters:
                self.filter_menu_button.add_css_class('accent')
            self.filter_menu_button.set_menu_model(self.window.builder.get_object('menu-explorer-search-global-search'))
            return

        if not self.search_filters:
            self.filter_menu_button.set_popover(None)
            return

        def build_checkbox(filter_):
            def toggle(button, _param):
                self.search_filters[filter_['key']] = button.get_active()

            check_button = Gtk.CheckButton(label=filter_['name'], active=filter_['default'])
            check_button.connect('notify::active', toggle)

            return check_button

        def build_entry(filter_):
            def on_text_changed(buf, _param):
                self.search_filters[filter_['key']] = buf.get_text()

            entry = Gtk.Entry(text=filter_['default'])
            entry.get_buffer().connect('notify::text', on_text_changed)

            return entry

        def build_select_single(filter_):
            def toggle_option(button, _param, key):
                if button.get_active():
                    self.search_filters[filter_['key']] = key

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

            last = None
            for option in filter_['options']:
                is_active = option['key'] == filter_['default']
                radio_button = Gtk.CheckButton(label=option['name'])
                radio_button.set_group(last)
                radio_button.set_active(is_active)
                radio_button.connect('notify::active', toggle_option, option['key'])
                vbox.append(radio_button)
                last = radio_button

            return vbox

        def build_select_multiple(filter_):
            def toggle_option(button, _param, key):
                if button.get_active():
                    self.search_filters[filter_['key']].append(key)
                else:
                    self.search_filters[filter_['key']].remove(key)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

            for option in filter_['options']:
                check_button = Gtk.CheckButton(label=option['name'], active=option['default'])
                check_button.connect('notify::active', toggle_option, option['key'])
                vbox.append(check_button)

            return vbox

        popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        for index, filter_ in enumerate(self.server.filters):
            if filter_['type'] == 'checkbox':
                filter_widget = build_checkbox(filter_)
            elif filter_['type'] == 'entry':
                filter_widget = build_entry(filter_)
            elif filter_['type'] == 'select':
                if filter_['value_type'] == 'single':
                    filter_widget = build_select_single(filter_)
                elif filter_['value_type'] == 'multiple':
                    filter_widget = build_select_multiple(filter_)
                else:
                    raise ValueError('Invalid select value_type')  # noqa: TC003
            else:
                raise ValueError('Invalid filter type')  # noqa: TC003

            if index > 0:
                vbox.append(Gtk.Separator())

            label = Gtk.Label(label=filter_['name'], xalign=0, tooltip_text=filter_['description'])
            label.add_css_class('heading')
            vbox.append(label)
            vbox.append(filter_widget)

        popover.set_child(vbox)

        self.filter_menu_button.set_popover(popover)

    def on_hidden(self, _page):
        if self.window.previous_page == self.props.tag:
            return

        self.clear()

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != self.props.tag:
            return Gdk.EVENT_PROPAGATE

        modifiers = state & Gtk.accelerator_get_default_mod_mask()

        if keyval == Gdk.KEY_Escape or (modifiers == Gdk.ModifierType.ALT_MASK and keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left)):
            # If in search mode, stop event to prevent Search mode exit and do pop
            if self.searchbar.get_search_mode():
                self.window.navigationview.pop()
                return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_manga_clicked(self, _listbox, row):
        if self.search_global_mode:
            self.server = getattr(row.server_data['module'], row.server_data['class_name'])()

        self.show_manga_card(row.manga_data)

    def on_page_changed(self, _stack, _param):
        self.page = self.stack.props.visible_child_name

        if self.page == 'most_popular':
            self.most_popular_page.populate()
        elif self.page == 'latest_updates':
            self.latest_updates_page.populate()

    def on_search_changed(self, _entry):
        if not self.searchentry.get_text().strip():
            self.search_stack.set_visible_child_name('intro')

    def on_server_website_button_clicked(self, _button):
        if self.server.base_url:
            Gtk.UriLauncher.new(uri=self.server.base_url).launch()
        else:
            self.window.show_notification(_('Oops, server website URL is unknown.'), 2)

    def on_shown(self, _page):
        self.searchentry.grab_focus()

    def register_request(self, page):
        if page not in self.requests:
            self.requests[page] = []

        self.requests[page].append(self.server.id)

    def search(self, _entry=None):
        term = self.searchentry.get_text().strip()

        if self.search_global_mode:
            self.search_global_page.search(term)
            return

        self.search_page.search(term)

    def show(self, server=None):
        self.server = server
        self.search_global_mode = server is None

        self.init_search_filters()

        if not self.search_global_mode:
            # Search, Most Popular, Latest Updates
            self.title.set_title(self.server.name)

            has_search = self.server.true_search
            has_most_popular = getattr(self.server, 'get_most_populars', None) is not None
            has_latest_updates = getattr(self.server, 'get_latest_updates', None) is not None

            with self.stack.handler_block(self.page_changed_handler_id):
                self.stack.get_page(self.stack.get_child_by_name('most_popular')).set_visible(has_most_popular)
                self.stack.get_page(self.stack.get_child_by_name('latest_updates')).set_visible(has_latest_updates)
                self.stack.get_page(self.stack.get_child_by_name('search')).set_visible(has_search)

            if has_search:
                self.searchentry.props.placeholder_text = _('Search {}').format(self.server.name)
                self.searchentry.set_text('')
                self.search_intro_status_page.set_title(_('Search for Reading'))
                if self.server.id == 'local':
                    description = _('Empty search is allowed.')
                else:
                    description = _("""Alternatively, you can look up specific comics using the syntax:

<b>id:ID from comic URL</b>""")
                self.search_intro_status_page.set_description(description)
                self.search_stack.set_visible_child_name('intro')

            if has_search:
                start_page = 'search'
            elif has_most_popular:
                start_page = 'most_popular'
            elif has_latest_updates:
                start_page = 'latest_updates'

            viewswitcher_enabled = has_search + has_most_popular + has_latest_updates > 1
            if viewswitcher_enabled:
                self.viewswitcher.set_visible(True)
                self.viewswitcherbar.set_visible(True)
                if self.viewswitcherbar.get_reveal():
                    self.title_stack.set_visible_child(self.title)
                else:
                    self.title_stack.set_visible_child(self.viewswitcher)
            else:
                self.title_stack.set_visible_child(self.title)
                self.viewswitcher.set_visible(False)
                self.viewswitcherbar.set_visible(False)
            self.server_website_button.set_visible(self.server.id != 'local')
        else:
            # Global Search (use `search` page)
            self.title.set_title(_('Global Search'))

            self.searchentry.props.placeholder_text = _('Search globally by name')
            self.searchentry.set_text('')
            self.search_intro_status_page.set_title(_('Search for Comics'))
            self.search_intro_status_page.set_description('')
            self.search_stack.set_visible_child_name('intro')
            start_page = 'search'

            self.viewswitcher.set_visible(False)
            self.viewswitcherbar.set_visible(False)
            self.server_website_button.set_visible(False)

        self.page = start_page
        self.progressbar.set_fraction(0)
        # To be sure to be notify on next page change
        self.stack.set_visible_child_name('search')
        GLib.idle_add(self.stack.set_visible_child_name, start_page)

        self.window.navigationview.push(self)

    def show_manga_card(self, manga_data, server=None):
        def run_get(server, initial_data):
            try:
                manga_data = self.server.get_manga_data(initial_data)

                if manga_data is not None:
                    GLib.idle_add(complete_get, manga_data, server)
                else:
                    GLib.idle_add(error, server)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, server, user_error_message)

        def run_update(server, manga_id):
            manga = Manga.get(manga_id, server)
            try:
                status, recent_chapters_ids, nb_deleted_chapters, synced = manga.update_full()
                if status is True:
                    GLib.idle_add(complete_update, manga, server, recent_chapters_ids, nb_deleted_chapters, synced)
                else:
                    GLib.idle_add(error, server)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, server, user_error_message)

        def complete_get(manga_data, server):
            if server != self.server:
                return False

            self.window.activity_indicator.stop()

            manga = Manga.new(manga_data, self.server, Settings.get_default().long_strip_detection)

            self.window.card.init(manga)

        def complete_update(manga, server, recent_chapters_ids, _nb_deleted_chapters, _synced):
            nb_recent_chapters = len(recent_chapters_ids)

            if nb_recent_chapters > 0:
                # Auto download new chapters
                if Settings.get_default().new_chapters_auto_download:
                    self.window.downloader.add(recent_chapters_ids, emit_signal=True)
                    self.window.downloader.start()

                self.window.library.refresh_on_manga_state_changed(manga)

            if server != self.server:
                return False

            self.window.activity_indicator.stop()

            self.window.card.init(manga)

        def error(server, message=None):
            if server != self.server:
                return False

            self.window.activity_indicator.stop()

            self.window.show_notification(message or _("Oops, failed to retrieve manga's information."), 2)

            return False

        self.window.activity_indicator.start()

        if server is not None:
            self.server = server

        # Check if selected manga is already in database
        db_conn = create_db_connection()
        record = db_conn.execute(
            'SELECT * FROM mangas WHERE slug = ? AND server_id = ?',
            (manga_data['slug'], self.server.id)
        ).fetchone()
        db_conn.close()

        if record:
            thread = threading.Thread(target=run_update, args=(self.server, record['id'], ))
        else:
            thread = threading.Thread(target=run_get, args=(self.server, manga_data, ))

        thread.daemon = True
        thread.start()
