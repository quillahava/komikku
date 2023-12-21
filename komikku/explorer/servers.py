# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import os

from gi.repository import Adw
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk

from komikku.explorer.common import ExplorerServerRow
from komikku.models import Settings
from komikku.servers import LANGUAGES
from komikku.servers.utils import get_allowed_servers_list
from komikku.utils import get_data_dir


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/explorer_servers.ui')
class ExplorerServersPage(Adw.NavigationPage):
    __gtype_name__ = 'ExplorerServersPage'

    global_search_button = Gtk.Template.Child('global_search_button')
    search_button = Gtk.Template.Child('search_button')

    searchbar = Gtk.Template.Child('searchbar')
    searchbar_separator = Gtk.Template.Child('searchbar_separator')
    searchentry = Gtk.Template.Child('searchentry')
    listbox = Gtk.Template.Child('listbox')
    pinned_listbox = Gtk.Template.Child('pinned_listbox')

    preselection = False

    def __init__(self, parent):
        Adw.NavigationPage.__init__(self)

        self.parent = parent
        self.window = parent.window

        self.servers = None

        self.connect('hidden', self.on_hidden)
        self.connect('shown', self.on_shown)

        self.global_search_button.connect('clicked', self.on_global_search_button_clicked)

        self.searchbar.bind_property(
            'search-mode-enabled', self.search_button, 'active',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.searchbar.bind_property(
            'search-mode-enabled', self.searchbar_separator, 'visible',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.searchbar.connect_entry(self.searchentry)
        self.searchbar.connect('notify::search-mode-enabled', self.on_search_mode_toggled)
        self.searchbar.set_key_capture_widget(self.window)

        self.searchentry.connect('activate', self.on_searchentry_activated)
        self.searchentry.connect('search-changed', self.search)

        self.pinned_listbox.connect('row-activated', self.on_server_clicked)

        self.listbox.connect('row-activated', self.on_server_clicked)
        self.listbox.set_filter_func(self.filter)

    def clear(self):
        # Clear servers list
        row = self.listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            if isinstance(row, ExplorerServerRow):
                row.dispose()
            row = next_row

        self.listbox.remove_all()

        # Clear pinned servers list
        row = self.pinned_listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            if isinstance(row, ExplorerServerRow):
                row.dispose()
            row = next_row

        self.pinned_listbox.remove_all()

    def filter(self, row):
        """
        This function gets one row and has to return:
        - True if the row should be displayed
        - False if the row should not be displayed
        """
        term = self.searchentry.get_text().strip().lower()

        if not hasattr(row, 'server_data'):
            # Languages headers should always be displayed
            return True

        server_name = row.server_data['name']
        server_lang = row.server_data['lang']

        # Search in name and language
        return (
            term in server_name.lower() or
            term in LANGUAGES.get(server_lang, _('Other')).lower() or
            term in server_lang.lower()
        )

    def on_hidden(self, _page):
        if self.window.previous_page == self.props.tag:
            return

        self.clear()

    def on_global_search_button_clicked(self, _button):
        self.parent.search_page.show()

    def on_server_clicked(self, _listbox, row):
        server = getattr(row.server_data['module'], row.server_data['class_name'])()
        if self.preselection and hasattr(row, 'manga_data'):
            self.parent.search_page.show_manga_card(row.manga_data, server)
        else:
            self.parent.search_page.show(server)

    def on_search_mode_toggled(self, _searchbar, _gparam):
        if self.searchbar.get_search_mode():
            self.pinned_listbox.set_visible(False)
        elif len(Settings.get_default().pinned_servers):
            self.pinned_listbox.set_visible(True)

    def on_searchentry_activated(self, _entry):
        if not self.searchbar.get_search_mode():
            return

        # Select first search result
        for child_row in self.listbox:
            if not hasattr(child_row, 'server_data') or not self.filter(child_row):
                continue
            self.on_server_clicked(self.listbox, child_row)
            break

    def on_shown(self, _page):
        if self.searchbar.get_search_mode():
            self.searchentry.grab_focus()

    def open_local_folder(self, _button):
        path = os.path.join(get_data_dir(), 'local')
        Gio.app_info_launch_default_for_uri(f'file://{path}')

    def populate_pinned(self):
        count = 0
        pinned_servers = Settings.get_default().pinned_servers
        for server_data in self.servers:
            if server_data['id'] not in pinned_servers:
                continue

            row = ExplorerServerRow(server_data, self)
            self.pinned_listbox.append(row)
            count += 1

        if count:
            # Add header
            row = Gtk.ListBoxRow(activatable=False)
            row.add_css_class('explorer-section-listboxrow')
            label = Gtk.Label(xalign=0)
            label.add_css_class('subtitle')
            label.set_text(_('Pinned').upper())
            row.set_child(label)
            self.pinned_listbox.prepend(row)

        self.pinned_listbox.set_visible(count > 0)

    def populate(self, servers=None):
        self.clear()

        if not servers:
            self.servers = get_allowed_servers_list(Settings.get_default())
            self.populate_pinned()
            self.preselection = False
        else:
            self.servers = servers
            self.pinned_listbox.set_visible(False)
            self.preselection = True

        last_lang = None
        for server_data in self.servers:
            if server_data['lang'] != last_lang:
                # Add language header
                last_lang = server_data['lang']

                row = Gtk.ListBoxRow(activatable=False)
                row.add_css_class('explorer-section-listboxrow')
                label = Gtk.Label(xalign=0)
                label.add_css_class('subtitle')
                label.set_text(LANGUAGES.get(server_data['lang'], _('Other')).upper())
                row.set_child(label)
                self.listbox.append(row)

            row = ExplorerServerRow(server_data, self)
            self.listbox.append(row)

        if self.preselection and len(self.servers) == 1:
            row = self.listbox.get_first_child().get_next_sibling()
            self.parent.server = getattr(row.server_data['module'], row.server_data['class_name'])()
            self.parent.search_page.show_manga_card(row.manga_data)
        elif self not in self.window.navigationview.get_navigation_stack():
            self.window.navigationview.push(self)

    def search(self, _entry):
        self.listbox.invalidate_filter()

    def show(self, servers):
        self.searchbar.set_search_mode(False)
        self.populate(servers)

    def toggle_search_mode(self):
        self.searchbar.set_search_mode(not self.searchbar.get_search_mode())

    def toggle_server_pinned_state(self, button, row):
        if button.get_active():
            Settings.get_default().add_pinned_server(row.server_data['id'])
        else:
            Settings.get_default().remove_pinned_server(row.server_data['id'])

        if row.get_parent().get_name() == 'pinned_servers':
            for child_row in self.listbox:
                if not hasattr(child_row, 'server_data'):
                    continue

                if child_row.server_data['id'] == row.server_data['id']:
                    child_row.get_first_child().get_last_child().set_active(button.get_active())
                    break

        self.populate_pinned()
