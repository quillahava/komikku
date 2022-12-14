# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading
import time

from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango

from komikku.servers import LANGUAGES
from komikku.utils import log_error_traceback


class ExplorerSearchPage:
    filters = None
    global_mode = False
    lock = False
    stop = False

    def __init__(self, parent):
        self.parent = parent
        self.window = parent.window

        self.server_website_button = self.parent.window.explorer_search_page_server_website_button
        self.searchbar = self.parent.search_page_searchbar
        self.searchentry = self.parent.search_page_searchentry
        self.filter_menu_button = self.parent.search_page_filter_menu_button
        self.stack = self.parent.search_page_stack
        self.listbox = self.parent.search_page_listbox
        self.status_page = self.parent.search_page_status_page

        self.server_website_button.connect('clicked', self.on_server_website_button_clicked)
        self.searchbar.connect_entry(self.searchentry)
        self.searchbar.set_key_capture_widget(self.window)
        self.searchentry.connect('activate', self.search)
        self.listbox.connect('row-activated', self.on_manga_clicked)

    def clear_results(self):
        self.listbox.hide()
        self.stack.set_visible_child_name('search.results')

        child = self.listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.listbox.remove(child)
            child = next_child

    def clear_search(self):
        self.lock = False
        self.searchentry.set_text('')
        self.clear_results()
        self.init_filters()

    def init_filters(self):
        self.filters = get_server_default_search_filters(self.parent.server)

        if not self.filters:
            self.filter_menu_button.set_popover(None)
            return

        def build_checkbox(filter_):
            def toggle(button, _param):
                self.filters[filter_['key']] = button.get_active()

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

            check_button = Gtk.CheckButton(label=filter_['name'], active=filter_['default'])
            check_button.connect('notify::active', toggle)
            vbox.append(check_button)

            return vbox

        def build_entry(filter_):
            def on_text_changed(buf, _param):
                self.filters[filter_['key']] = buf.get_text()

            entry = Gtk.Entry(text=filter_['default'])
            entry.get_buffer().connect('notify::text', on_text_changed)

            return entry

        def build_select_single(filter_):
            def toggle_option(button, _param, key):
                if button.get_active():
                    self.filters[filter_['key']] = key

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
                    self.filters[filter_['key']].append(key)
                else:
                    self.filters[filter_['key']].remove(key)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

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

            vbox.append(Gtk.Label(label=filter_['name'], tooltip_text=filter_['description']))
            vbox.append(filter_widget)

        popover.set_child(vbox)

        self.filter_menu_button.set_popover(popover)

    def on_manga_clicked(self, listbox, row):
        if self.global_mode:
            self.parent.server = getattr(row.server_data['module'], row.server_data['class_name'])()

        self.parent.card_page.populate(row.manga_data)

    def on_server_website_button_clicked(self, _button):
        if self.parent.server.base_url:
            Gtk.show_uri(None, self.parent.server.base_url, time.time())
        else:
            self.window.show_notification(_('Oops, server website URL is unknown.'), 2)

    def search(self, _entry=None):
        if self.lock:
            return

        term = self.searchentry.get_text().strip()

        if self.global_mode:
            self.search_global(term)
            return

        # Find manga by Id
        if term.startswith('id:'):
            slug = term[3:]

            if not slug:
                return

            self.parent.card_page.populate(dict(slug=slug))
            return

        if not term and getattr(self.parent.server, 'get_most_populars', None) is None:
            # An empty term is allowed only if server has 'get_most_populars' method
            return

        def run(server):
            try:
                most_populars = not term
                if most_populars:
                    # We offer most popular mangas as starting search results
                    results = server.get_most_populars(**self.filters)
                else:
                    results = server.search(term, **self.filters)
                if self.stop:
                    return

                if results:
                    GLib.idle_add(complete, results, server, most_populars)
                else:
                    GLib.idle_add(error, results, server)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, None, server, user_error_message)

        def complete(results, server, most_populars):
            self.window.activity_indicator.stop()
            self.listbox.show()

            if most_populars:
                row = Gtk.ListBoxRow(activatable=False)
                row.add_css_class('explorer-section-listboxrow')
                if server.id != 'local':
                    label = Gtk.Label(label=_('Most populars').upper(), xalign=0)
                else:
                    label = Gtk.Label(label=_('Collection').upper(), xalign=0)
                label.add_css_class('subtitle')
                row.set_child(label)

                self.listbox.append(row)

            for item in results:
                row = Gtk.ListBoxRow()
                row.add_css_class('explorer-listboxrow')
                row.manga_data = item
                label = Gtk.Label(label=item['name'], xalign=0)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                row.set_child(label)

                self.listbox.append(row)

            self.lock = False

        def error(results, server, message=None):
            self.window.activity_indicator.stop()

            if results is None:
                self.status_page.set_title(_('Oops, search failed. Please try again.'))
                if message:
                    self.status_page.set_description(message)
            else:
                self.status_page.set_title(_('No Results Found'))
                self.status_page.set_description(_('Try a different search'))

            self.stack.set_visible_child_name('search.no_results')
            self.lock = False

        self.lock = True
        self.stop = False
        self.clear_results()
        self.listbox.set_sort_func(None)
        self.window.activity_indicator.start()

        thread = threading.Thread(target=run, args=(self.parent.server, ))
        thread.daemon = True
        thread.start()

    def search_global(self, term):
        def run(servers):
            for server_data in servers:
                server = getattr(server_data['module'], server_data['class_name'])()

                try:
                    filters = get_server_default_search_filters(server)
                    results = server.search(term, **filters)
                    if self.stop:
                        break

                    GLib.idle_add(complete_server, results, server_data)
                except Exception as e:
                    user_error_message = log_error_traceback(e)
                    GLib.idle_add(complete_server, None, server_data, user_error_message)

            GLib.idle_add(complete)

        def complete():
            self.lock = False

        def complete_server(results, server_data, message=None):
            lang = server_data['lang']
            name = server_data['name']

            # Remove spinner
            for row in self.listbox:
                if row.server_data['lang'] == lang and row.server_data['name'] == name:
                    if row.position == 0:
                        row.results = results is not None and len(results) > 0
                    elif row.position == 1:
                        self.listbox.remove(row)
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

                    self.listbox.append(row)
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

                self.listbox.append(row)

            self.listbox.invalidate_sort()

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

        self.clear_results()

        # Init results list
        for server_data in self.parent.servers_page.servers:
            # Server
            row = self.parent.build_server_row(server_data)
            row.server_data = server_data
            row.position = 0
            row.results = False
            self.listbox.append(row)

            # Spinner
            row = Gtk.ListBoxRow(activatable=False)
            row.server_data = server_data
            row.position = 1
            row.results = False
            row.add_css_class('explorer-listboxrow')
            spinner = Gtk.Spinner()
            spinner.start()
            row.set_child(spinner)
            self.listbox.append(row)

        self.lock = True
        self.stop = False
        self.listbox.set_sort_func(sort_results)
        self.listbox.show()

        thread = threading.Thread(target=run, args=(self.parent.servers_page.servers, ))
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
