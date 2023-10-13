# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from concurrent.futures import as_completed
from concurrent.futures import ThreadPoolExecutor
from gettext import gettext as _
import threading

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango

from komikku.models import create_db_connection
from komikku.models import Manga
from komikku.models import Settings
from komikku.servers import LANGUAGES
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
    most_populars_stack = Gtk.Template.Child('most_populars_stack')
    most_populars_listbox = Gtk.Template.Child('most_populars_listbox')
    most_populars_no_results_status_page = Gtk.Template.Child('most_populars_no_results_status_page')
    most_populars_spinner = Gtk.Template.Child('most_populars_spinner')
    latest_updates_stack = Gtk.Template.Child('latest_updates_stack')
    latest_updates_listbox = Gtk.Template.Child('latest_updates_listbox')
    latest_updates_no_results_status_page = Gtk.Template.Child('latest_updates_no_results_status_page')
    latest_updates_spinner = Gtk.Template.Child('latest_updates_spinner')
    viewswitcherbar = Gtk.Template.Child('viewswitcherbar')

    search_global_mode = False
    search_global_selected_filters = []
    page = None
    search_filters = None
    server = None

    requests = {}
    lock_search_global = None
    stop_search_global = None

    def __init__(self, parent):
        Adw.NavigationPage.__init__(self)

        self.parent = parent
        self.window = parent.window

        self.window.builder.add_from_resource('/info/febvre/Komikku/ui/menu/explorer_search_global_search.xml')

        self.search_global_selected_filters = Settings.get_default().explorer_search_global_selected_filters

        self.connect('hidden', self.on_hidden)
        self.connect('shown', self.on_shown)

        self.window.controller_key.connect('key-pressed', self.on_key_pressed)

        self.page_changed_handler_id = self.stack.connect('notify::visible-child-name', self.on_page_changed)

        self.server_website_button.connect('clicked', self.on_server_website_button_clicked)
        self.searchbar.connect_entry(self.searchentry)
        self.searchbar.set_key_capture_widget(self.window)
        self.searchentry.connect('activate', self.search)
        self.searchentry.connect('search-changed', self.on_search_changed)

        self.search_listbox.connect('row-activated', self.on_manga_clicked)
        self.most_populars_listbox.connect('row-activated', self.on_manga_clicked)
        self.most_populars_no_results_status_page.get_child().connect('clicked', self.populate_most_populars)
        self.latest_updates_listbox.connect('row-activated', self.on_manga_clicked)
        self.latest_updates_no_results_status_page.get_child().connect('clicked', self.populate_latest_updates)

        self.window.breakpoint.add_setter(self.viewswitcherbar, 'reveal', True)
        self.window.breakpoint.add_setter(self.title_stack, 'visible-child', self.title)

    def add_actions(self):
        # Global Search menu actions
        action = Gio.SimpleAction.new_stateful(
            'explorer.search.global.search.pinned', None, GLib.Variant('b', 'pinned' in self.search_global_selected_filters)
        )
        action.connect('change-state', self.on_search_global_search_menu_action_changed)
        self.window.application.add_action(action)

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

    def clear_latest_updates(self):
        self.latest_updates_listbox.set_visible(False)

        child = self.latest_updates_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.latest_updates_listbox.remove(child)
            child = next_child

    def clear_most_populars(self):
        self.most_populars_listbox.set_visible(False)

        child = self.most_populars_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.most_populars_listbox.remove(child)
            child = next_child

    def clear_search_results(self):
        self.search_listbox.set_visible(False)

        child = self.search_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.search_listbox.remove(child)
            child = next_child

    def init_search_filters(self):
        self.search_filters = get_server_default_search_filters(self.server)
        self.filter_menu_button.remove_css_class('accent')

        if self.search_global_mode:
            if self.search_global_selected_filters:
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

        self.search_global_mode = False
        # Stop global search if not ended
        self.stop_search_global = True

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

        if self.page == 'most_populars':
            self.populate_most_populars()
        elif self.page == 'latest_updates':
            self.populate_latest_updates()

    def on_search_changed(self, _entry):
        if not self.searchentry.get_text().strip():
            self.search_stack.set_visible_child_name('intro')

    def on_search_global_search_menu_action_changed(self, action, variant):
        value = variant.get_boolean()
        action.set_state(GLib.Variant('b', value))
        name = action.props.name.split('.')[-1]

        if value:
            self.search_global_selected_filters.add(name)
        else:
            self.search_global_selected_filters.remove(name)
        Settings.get_default().explorer_search_global_selected_filters = self.search_global_selected_filters

        if self.search_global_selected_filters:
            self.filter_menu_button.add_css_class('accent')
        else:
            self.filter_menu_button.remove_css_class('accent')

    def on_server_website_button_clicked(self, _button):
        if self.server.base_url:
            Gtk.UriLauncher.new(uri=self.server.base_url).launch()
        else:
            self.window.show_notification(_('Oops, server website URL is unknown.'), 2)

    def on_shown(self, _page):
        self.searchentry.grab_focus()

    def populate_latest_updates(self, *args):
        def run(server):
            self.register_request('latest_updates')

            try:
                results = server.get_latest_updates(**self.search_filters)

                if results:
                    GLib.idle_add(complete, results, server.id)
                else:
                    GLib.idle_add(error, results, server.id)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, None, server.id, user_error_message)

        def complete(results, server_id):
            self.latest_updates_spinner.stop()

            if not self.can_page_be_updated_with_results('latest_updates', server_id):
                return

            self.latest_updates_listbox.set_visible(True)

            for item in results:
                row = Gtk.ListBoxRow()
                row.add_css_class('explorer-listboxrow')
                row.manga_data = item
                label = Gtk.Label(label=item['name'], xalign=0)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                row.set_child(label)

                self.latest_updates_listbox.append(row)

            self.latest_updates_stack.set_visible_child_name('results')

        def error(results, server_id, message=None):
            self.latest_updates_spinner.stop()

            if not self.can_page_be_updated_with_results('latest_updates', server_id):
                return

            if results is None:
                self.latest_updates_no_results_status_page.set_title(_('Oops, failed to retrieve latest updates.'))
                if message:
                    self.latest_updates_no_results_status_page.set_description(message)
            else:
                self.latest_updates_no_results_status_page.set_title(_('No Latest Updates Found'))

            self.latest_updates_stack.set_visible_child_name('no_results')

        self.clear_latest_updates()
        self.latest_updates_spinner.start()
        self.latest_updates_stack.set_visible_child_name('loading')

        if self.requests.get('latest_updates') and self.server.id in self.requests['latest_updates']:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        thread = threading.Thread(target=run, args=(self.server, ))
        thread.daemon = True
        thread.start()

    def populate_most_populars(self, *args):
        def run(server):
            self.register_request('most_populars')

            try:
                results = server.get_most_populars(**self.search_filters)

                if results:
                    GLib.idle_add(complete, results, server.id)
                else:
                    GLib.idle_add(error, results, server.id)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, None, server.id, user_error_message)

        def complete(results, server_id):
            self.most_populars_spinner.stop()

            if not self.can_page_be_updated_with_results('most_populars', server_id):
                return

            self.most_populars_listbox.set_visible(True)

            for item in results:
                row = Gtk.ListBoxRow()
                row.add_css_class('explorer-listboxrow')
                row.manga_data = item
                label = Gtk.Label(label=item['name'], xalign=0)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                row.set_child(label)

                self.most_populars_listbox.append(row)

            self.most_populars_stack.set_visible_child_name('results')

        def error(results, server_id, message=None):
            self.most_populars_spinner.stop()

            if not self.can_page_be_updated_with_results('most_populars', server_id):
                return

            if results is None:
                self.most_populars_no_results_status_page.set_title(_('Oops, failed to retrieve most popular.'))
                if message:
                    self.most_populars_no_results_status_page.set_description(message)
            else:
                self.most_populars_no_results_status_page.set_title(_('No Most Popular Found'))

            self.most_populars_stack.set_visible_child_name('no_results')

        self.clear_most_populars()
        self.most_populars_spinner.start()
        self.most_populars_stack.set_visible_child_name('loading')

        if self.requests.get('most_populars') and self.server.id in self.requests['most_populars']:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        thread = threading.Thread(target=run, args=(self.server, ))
        thread.daemon = True
        thread.start()

    def register_request(self, page):
        if page not in self.requests:
            self.requests[page] = []

        self.requests[page].append(self.server.id)

    def search(self, _entry=None):
        term = self.searchentry.get_text().strip()

        if self.search_global_mode:
            self.search_global(term)
            return

        # Find manga by Id
        if term.startswith('id:'):
            slug = term[3:]

            if not slug:
                return

            self.show_manga_card(dict(slug=slug))
            return

        # Disallow empty search except for 'Local' server
        if not term and self.server.id != 'local':
            return

        def run(server):
            self.register_request('search')

            try:
                results = server.search(term, **self.search_filters)

                if results:
                    GLib.idle_add(complete, results, server.id)
                else:
                    GLib.idle_add(error, results, server.id)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, None, server.id, user_error_message)

        def complete(results, server_id):
            self.search_spinner.stop()

            if not self.can_page_be_updated_with_results('search', server_id):
                return

            self.search_listbox.set_visible(True)

            for item in results:
                row = Gtk.ListBoxRow()
                row.add_css_class('explorer-listboxrow')
                row.manga_data = item
                label = Gtk.Label(label=item['name'], xalign=0)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                row.set_child(label)

                self.search_listbox.append(row)

            self.search_stack.set_visible_child_name('results')

        def error(results, server_id, message=None):
            self.search_spinner.stop()

            if not self.can_page_be_updated_with_results('search', server_id):
                return

            if results is None:
                self.search_no_results_status_page.set_title(_('Oops, search failed. Please try again.'))
                if message:
                    self.search_no_results_status_page.set_description(message)
            else:
                self.search_no_results_status_page.set_title(_('No Results Found'))
                self.search_no_results_status_page.set_description(_('Try a different search'))

            self.search_stack.set_visible_child_name('no_results')

        self.clear_search_results()
        self.search_stack.set_visible_child_name('loading')
        self.search_spinner.start()
        self.search_listbox.set_sort_func(None)

        if self.requests.get('search') and self.server.id in self.requests['search']:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        thread = threading.Thread(target=run, args=(self.server, ))
        thread.daemon = True
        thread.start()

    def search_global(self, term):
        if self.lock_search_global:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        def run(servers):
            with ThreadPoolExecutor(max_workers=len(servers)) as executor:
                tasks = {}
                for server_data in servers:
                    future = executor.submit(search_server, server_data)
                    tasks[future] = server_data

                for index, future in enumerate(as_completed(tasks)):
                    if self.stop_search_global:
                        executor.shutdown(False, cancel_futures=True)
                        break

                    server_data = tasks[future]
                    try:
                        results = future.result()
                    except Exception as exc:
                        GLib.idle_add(complete_server, None, server_data, log_error_traceback(exc))
                    else:
                        GLib.idle_add(complete_server, results, server_data)

                    self.progressbar.set_fraction((index + 1) / len(servers))

            GLib.idle_add(complete)

        def complete():
            self.lock_search_global = False
            self.progressbar.set_fraction(0)

        def complete_server(results, server_data, message=None):
            lang = server_data['lang']
            name = server_data['name']

            # Remove spinner
            for row in self.search_listbox:
                if row.server_data['lang'] == lang and row.server_data['name'] == name:
                    if row.position == 0:
                        row.results = results is not None and len(results) > 0
                    elif row.position == 1:
                        self.search_listbox.remove(row)
                        break

            if results:
                # Add results
                for index, item in enumerate(results):
                    row = Gtk.ListBoxRow()
                    row.add_css_class('explorer-listboxrow')
                    row.manga_data = item
                    row.server_data = server_data
                    row.position = index + 1
                    row.results = True
                    label = Gtk.Label(label=item['name'], xalign=0)
                    label.set_ellipsize(Pango.EllipsizeMode.END)
                    row.set_child(label)

                    self.search_listbox.append(row)
            else:
                # Error or no results
                row = Gtk.ListBoxRow(activatable=False)
                row.server_data = server_data
                row.position = 1
                row.results = False
                row.add_css_class('explorer-listboxrow')
                label = Gtk.Label(halign=Gtk.Align.CENTER, justify=Gtk.Justification.CENTER)
                if results is None:
                    # Error
                    text = _('Oops, search failed. Please try again.')
                    if message:
                        text = f'{text}\n{message}'
                else:
                    # No results
                    text = _('No results')
                label.set_markup(f'<i>{text}</i>')
                label.set_ellipsize(Pango.EllipsizeMode.END)
                row.set_child(label)

                self.search_listbox.append(row)

            self.search_listbox.invalidate_sort()

        def search_server(server_data):
            server = getattr(server_data['module'], server_data['class_name'])()
            filters = get_server_default_search_filters(server)
            return server.search(term, **filters)

        def sort_results(row1, row2):
            """
            This function gets two children and has to return:
            - a negative integer if the first one should come before the second one
            - zero if they are equal
            - a positive integer if the second one should come before the firstone
            """
            row1_results = row1.results
            row1_server_lang = LANGUAGES.get(row1.server_data['lang'], '')
            row1_server_name = row1.server_data['name']
            row1_position = row1.position

            row2_results = row2.results
            row2_server_lang = LANGUAGES.get(row2.server_data['lang'], '')
            row2_server_name = row2.server_data['name']
            row2_position = row2.position

            # Servers with results first
            if row1_results and not row2_results:
                return -1
            if not row1_results and row2_results:
                return 1

            # Sort by language
            if row1_server_lang < row2_server_lang:
                return -1

            if row1_server_lang == row2_server_lang:
                # Sort by server name
                if row1_server_name < row2_server_name:
                    return -1

                # Sort by position
                if row1_server_name == row2_server_name and row1_position < row2_position:
                    return -1

            return 1

        self.clear_search_results()

        if 'pinned' in self.search_global_selected_filters:
            servers = []
            pinned_servers = Settings.get_default().pinned_servers
            for server_data in self.parent.servers_page.servers:
                if server_data['id'] not in pinned_servers:
                    continue

                servers.append(server_data)
        else:
            servers = self.parent.servers_page.servers

        # Init results list
        for server_data in servers:
            # Server row
            row = self.parent.build_server_row(server_data)
            row.server_data = server_data
            row.position = 0
            row.results = False
            self.search_listbox.append(row)

            # Spinner
            row = Gtk.ListBoxRow(activatable=False)
            row.server_data = server_data
            row.position = 1
            row.results = False
            row.add_css_class('explorer-listboxrow')
            spinner = Gtk.Spinner()
            spinner.start()
            row.set_child(spinner)
            self.search_listbox.append(row)

        self.lock_search_global = True
        self.stop_search_global = False
        self.search_stack.set_visible_child_name('results')
        self.search_listbox.set_sort_func(sort_results)
        self.search_listbox.set_visible(True)

        thread = threading.Thread(target=run, args=(servers,))
        thread.daemon = True
        thread.start()

    def show(self, server=None):
        self.server = server
        self.search_global_mode = server is None

        self.init_search_filters()

        if not self.search_global_mode:
            # Search, Most Populars, Latest Updates
            self.title.set_title(self.server.name)

            has_search = self.server.true_search
            has_most_populars = getattr(self.server, 'get_most_populars', None) is not None
            has_latest_updates = getattr(self.server, 'get_latest_updates', None) is not None

            with self.stack.handler_block(self.page_changed_handler_id):
                self.stack.get_page(self.stack.get_child_by_name('most_populars')).set_visible(has_most_populars)
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
            elif has_most_populars:
                start_page = 'most_populars'
            elif has_latest_updates:
                start_page = 'latest_updates'

            viewswitcher_enabled = has_search + has_most_populars + has_latest_updates > 1
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
            self.search_intro_status_page.set_title(_('Search for comics across all the servers you have enabled'))
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

        def complete_update(manga, server, recent_chapters_ids, nb_deleted_chapters, synced):
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


def get_server_default_search_filters(server):
    filters = {}

    if getattr(server, 'filters', None) is None:
        return filters

    for filter_ in server.filters:
        if filter_['type'] == 'select' and filter_['value_type'] == 'multiple':
            filters[filter_['key']] = [option['key'] for option in filter_['options'] if option['default']]
        else:
            filters[filter_['key']] = filter_['default']

    return filters
