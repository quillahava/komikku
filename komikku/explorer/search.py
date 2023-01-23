# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading
import time

from gi.repository import Adw
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango

from komikku.servers import LANGUAGES
from komikku.utils import log_error_traceback


class ExplorerSearchPage:
    global_search_mode = False
    page = None
    search_filters = None

    requests = {}
    lock_search_global = None
    stop_search_global = None

    def __init__(self, parent):
        self.parent = parent
        self.window = parent.window

        self.stack = self.parent.search_page_stack
        self.viewswitcherbar = self.parent.search_page_viewswitcherbar

        self.server_website_button = self.parent.window.explorer_search_page_server_website_button

        self.searchbar = self.parent.search_page_searchbar
        self.searchentry = self.parent.search_page_searchentry
        self.filter_menu_button = self.parent.search_page_filter_menu_button
        self.search_stack = self.parent.search_page_search_stack
        self.search_listbox = self.parent.search_page_search_listbox
        self.search_status_page = self.parent.search_page_search_status_page
        self.search_spinner = self.parent.search_page_search_spinner

        self.most_populars_stack = self.parent.search_page_most_populars_stack
        self.most_populars_listbox = self.parent.search_page_most_populars_listbox
        self.most_populars_status_page = self.parent.search_page_most_populars_status_page
        self.most_populars_spinner = self.parent.search_page_most_populars_spinner

        self.latest_updates_stack = self.parent.search_page_latest_updates_stack
        self.latest_updates_listbox = self.parent.search_page_latest_updates_listbox
        self.latest_updates_status_page = self.parent.search_page_latest_updates_status_page
        self.latest_updates_spinner = self.parent.search_page_latest_updates_spinner

        self.page_changed_handler_id = self.stack.connect('notify::visible-child-name', self.on_page_changed)

        self.server_website_button.connect('clicked', self.on_server_website_button_clicked)
        self.searchbar.connect_entry(self.searchentry)
        self.searchbar.set_key_capture_widget(self.window)
        self.searchentry.connect('activate', self.search)
        self.search_listbox.connect('row-activated', self.on_manga_clicked)

        self.most_populars_listbox.connect('row-activated', self.on_manga_clicked)
        self.most_populars_status_page.get_child().connect('clicked', self.populate_most_populars)
        self.latest_updates_listbox.connect('row-activated', self.on_manga_clicked)
        self.latest_updates_status_page.get_child().connect('clicked', self.populate_latest_updates)

        # Add Adw.ViewSwitcherTitle in Adw.HeaderBar => Gtk.Stack 'explorer' page => Gtk.Stack 'search' page
        self.viewswitchertitle = Adw.ViewSwitcherTitle(title=_('Search'))
        self.viewswitchertitle.set_stack(self.stack)
        self.viewswitchertitle.connect('notify::title-visible', self.on_viewswitchertitle_title_visible)
        self.parent.title_stack.get_child_by_name('search').set_child(self.viewswitchertitle)

    def can_page_be_updated_with_results(self, page, server_id):
        self.requests[page].remove(server_id)

        if self.parent.props.visible_child_name != 'search':
            # Not in Explorer search page
            return False
        elif server_id != self.parent.server.id:
            # server_id is not the current server
            return False
        elif page != self.page:
            # page is not the current page
            return False

        return True

    def clear_latest_updates(self):
        self.latest_updates_listbox.hide()

        child = self.latest_updates_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.latest_updates_listbox.remove(child)
            child = next_child

    def clear_most_populars(self):
        self.most_populars_listbox.hide()

        child = self.most_populars_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.most_populars_listbox.remove(child)
            child = next_child

    def clear_search_results(self):
        self.search_listbox.hide()

        child = self.search_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.search_listbox.remove(child)
            child = next_child

    def init_search_filters(self):
        self.search_filters = get_server_default_search_filters(self.parent.server)

        if not self.search_filters:
            self.filter_menu_button.set_popover(None)
            return

        def build_checkbox(filter_):
            def toggle(button, _param):
                self.search_filters[filter_['key']] = button.get_active()

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

            check_button = Gtk.CheckButton(label=filter_['name'], active=filter_['default'])
            check_button.connect('notify::active', toggle)
            vbox.append(check_button)

            return vbox

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

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

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

        for index, filter_ in enumerate(self.parent.server.filters):
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
                    raise NotImplementedError('Invalid select value_type')
            else:
                raise NotImplementedError('Invalid filter type')

            if index > 0:
                vbox.append(Gtk.Separator())

            label = Gtk.Label(label=filter_['name'], xalign=0, tooltip_text=filter_['description'])
            label.add_css_class('heading')
            vbox.append(label)
            vbox.append(filter_widget)

        popover.set_child(vbox)

        self.filter_menu_button.set_popover(popover)

    def on_manga_clicked(self, listbox, row):
        if self.global_search_mode:
            self.parent.server = getattr(row.server_data['module'], row.server_data['class_name'])()

        self.parent.card_page.populate(row.manga_data)

    def on_page_changed(self, _stack, _param):
        self.page = self.stack.props.visible_child_name

        if self.page == 'most_populars':
            self.toggle_search_page(False)
            self.populate_most_populars()
        elif self.page == 'latest_updates':
            self.toggle_search_page(False)
            self.populate_latest_updates()

    def on_server_website_button_clicked(self, _button):
        if self.parent.server.base_url:
            Gtk.show_uri(None, self.parent.server.base_url, time.time())
        else:
            self.window.show_notification(_('Oops, server website URL is unknown.'), 2)

    def on_viewswitchertitle_title_visible(self, _viewswitchertitle, _param):
        if self.viewswitchertitle.get_title_visible():
            self.viewswitcherbar.set_reveal(not self.global_search_mode and self.viewswitchertitle.props.view_switcher_enabled)
        else:
            self.viewswitcherbar.set_reveal(False)

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

            self.latest_updates_listbox.show()

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
                self.latest_updates_status_page.set_title(_('Oops, failed to retrieve latest updates.'))
                if message:
                    self.latest_updates_status_page.set_description(message)
            else:
                self.latest_updates_status_page.set_title(_('No Latest Updates Found'))

            self.latest_updates_stack.set_visible_child_name('no_results')

        self.clear_latest_updates()
        self.latest_updates_spinner.start()
        self.latest_updates_stack.set_visible_child_name('loading')

        if self.requests.get('latest_updates') and self.parent.server.id in self.requests['latest_updates']:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        thread = threading.Thread(target=run, args=(self.parent.server, ))
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

            self.most_populars_listbox.show()

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
                self.most_populars_status_page.set_title(_('Oops, failed to retrieve most popular.'))
                if message:
                    self.most_populars_status_page.set_description(message)
            else:
                self.most_populars_status_page.set_title(_('No Most Popular Found'))

            self.most_populars_stack.set_visible_child_name('no_results')

        self.clear_most_populars()
        self.most_populars_spinner.start()
        self.most_populars_stack.set_visible_child_name('loading')

        if self.requests.get('most_populars') and self.parent.server.id in self.requests['most_populars']:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        thread = threading.Thread(target=run, args=(self.parent.server, ))
        thread.daemon = True
        thread.start()

    def register_request(self, page):
        if page not in self.requests:
            self.requests[page] = []

        self.requests[page].append(self.parent.server.id)

    def search(self, _entry=None):
        term = self.searchentry.get_text().strip()

        if self.global_search_mode:
            self.search_global(term)
            return

        # Find manga by Id
        if term.startswith('id:'):
            slug = term[3:]

            if not slug:
                return

            self.parent.card_page.populate(dict(slug=slug))
            return

        # Disallow empty search except for 'Local' server
        if not term and self.parent.server.id != 'local':
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

            self.search_listbox.show()

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
                self.search_status_page.set_title(_('Oops, search failed. Please try again.'))
                if message:
                    self.search_status_page.set_description(message)
            else:
                self.search_status_page.set_title(_('No Results Found'))
                self.search_status_page.set_description(_('Try a different search'))

            self.search_stack.set_visible_child_name('no_results')

        self.toggle_search_page(True)
        self.search_spinner.start()
        self.search_stack.set_visible_child_name('loading')
        self.search_listbox.set_sort_func(None)

        if self.requests.get('search') and self.parent.server.id in self.requests['search']:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        thread = threading.Thread(target=run, args=(self.parent.server, ))
        thread.daemon = True
        thread.start()

    def search_global(self, term):
        if self.lock_search_global:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        def run(servers):
            for server_data in servers:
                server = getattr(server_data['module'], server_data['class_name'])()

                try:
                    filters = get_server_default_search_filters(server)
                    results = server.search(term, **filters)
                    if self.stop_search_global:
                        break

                    GLib.idle_add(complete_server, results, server_data)
                except Exception as e:
                    if self.stop_search_global:
                        break
                    user_error_message = log_error_traceback(e)
                    GLib.idle_add(complete_server, None, server_data, user_error_message)

            GLib.idle_add(complete)

        def complete():
            self.lock_search_global = False

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

        self.toggle_search_page(True)

        # Init results list
        for server_data in self.parent.servers_page.servers:
            # Server
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
        self.search_listbox.set_sort_func(sort_results)
        self.search_listbox.show()

        thread = threading.Thread(target=run, args=(self.parent.servers_page.servers, ))
        thread.daemon = True
        thread.start()

    def show(self):
        self.init_search_filters()

        if not self.global_search_mode:
            # Search, Most Populars, Latest Updates
            self.viewswitchertitle.set_title(self.parent.server.name)
            self.searchentry.props.placeholder_text = _('Search {}').format(self.parent.server.name)

            has_true_search = self.parent.server.true_search
            has_most_populars = getattr(self.parent.server, 'get_most_populars', None) is not None
            has_latest_updates = getattr(self.parent.server, 'get_latest_updates', None) is not None

            with self.stack.handler_block(self.page_changed_handler_id):
                self.stack.get_page(self.stack.get_child_by_name('most_populars')).set_visible(has_most_populars)
                self.stack.get_page(self.stack.get_child_by_name('latest_updates')).set_visible(has_latest_updates)
                self.stack.get_page(self.stack.get_child_by_name('search')).set_visible(not has_true_search)

            if has_true_search:
                self.searchbar.show()
            else:
                self.searchbar.hide()

            if has_most_populars:
                start_page = 'most_populars'
            elif has_latest_updates:
                start_page = 'latest_updates'
            else:
                start_page = 'search'
                self.clear_search_results()
                self.search_stack.set_visible_child_name('results')

            viewswitcher_enabled = has_true_search + has_most_populars + has_latest_updates > 1
            self.viewswitcherbar.set_reveal(self.viewswitchertitle.get_title_visible() and viewswitcher_enabled)
            self.viewswitchertitle.set_view_switcher_enabled(viewswitcher_enabled)
        else:
            # Global Search
            self.viewswitchertitle.set_title(_('Global Search'))
            self.searchentry.props.placeholder_text = ''

            self.searchbar.show()
            start_page = 'search'
            self.clear_search_results()
            self.search_stack.set_visible_child_name('results')

            self.viewswitcherbar.set_reveal(False)
            self.viewswitchertitle.set_view_switcher_enabled(False)

        self.searchentry.set_text('')
        self.stack.set_visible_child_name('search')  # To be sure to detect next page change
        GLib.idle_add(self.stack.set_visible_child_name, start_page)

    def toggle_search_page(self, visible):
        self.stack.get_page(self.stack.get_child_by_name('search')).set_visible(visible)
        self.clear_search_results()
        if not visible:
            self.searchentry.set_text('')
        else:
            self.stack.set_visible_child_name('search')


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
