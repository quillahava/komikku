# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Gtk
from gi.repository import Pango

from komikku.explorer.search import ExplorerSearchPage
from komikku.explorer.servers import ExplorerServersPage
from komikku.models import Settings
from komikku.servers import LANGUAGES

LOGO_SIZE = 28


class Explorer:
    def __init__(self, window):
        self.window = window

        self.servers_page = ExplorerServersPage(self)
        self.window.navigationview.add(self.servers_page)
        self.search_page = ExplorerSearchPage(self)
        self.window.navigationview.add(self.search_page)

    def build_server_row(self, data):
        # Used in `servers` and `search` (global search) pages
        if self.search_page.search_global_mode:
            row = Gtk.ListBoxRow(activatable=False)
            row.add_css_class('explorer-section-listboxrow')
        else:
            row = Gtk.ListBoxRow(activatable=True)
            row.add_css_class('explorer-listboxrow')

        row.server_data = data
        if 'manga_initial_data' in data:
            row.manga_data = data.pop('manga_initial_data')

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_child(box)

        # Server logo
        logo = Gtk.Image()
        logo.set_size_request(LOGO_SIZE, LOGO_SIZE)
        if data['id'] != 'local':
            if data['logo_path']:
                logo.set_from_file(data['logo_path'])
        else:
            logo.set_from_icon_name('folder-symbolic')
        box.append(logo)

        # Server title & language
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        if data['id'] != 'local':
            title = data['name']
            subtitle = LANGUAGES[data['lang']]
        else:
            title = _('Local')
            subtitle = _('Comics stored locally as archives in CBZ/CBR formats')

        label = Gtk.Label(xalign=0, hexpand=True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_text(title)
        vbox.append(label)

        subtitle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        label = Gtk.Label(xalign=0)
        label.set_wrap(True)
        label.set_text(subtitle)
        label.add_css_class('subtitle')
        subtitle_box.append(label)

        if data['is_nsfw']:
            label = Gtk.Label(xalign=0)
            label.set_markup('<b>' + _('18+') + '</b>')
            label.add_css_class('subtitle')
            label.add_css_class('accent')
            subtitle_box.append(label)

        vbox.append(subtitle_box)
        box.append(vbox)

        if self.search_page.search_global_mode:
            return row

        # Server requires a user account
        if data['has_login']:
            label = Gtk.Image.new_from_icon_name('dialog-password-symbolic')
            box.append(label)

        if data['id'] == 'local':
            # Info button
            button = Gtk.MenuButton(valign=Gtk.Align.CENTER)
            button.set_icon_name('help-about-symbolic')
            button.set_tooltip_text(_('Help'))
            popover = Gtk.Popover()
            label = Gtk.Label()
            label.set_wrap(True)
            label.set_max_width_chars(32)
            label.set_text(_("""A specific folder structure is required for local comics to be properly processed.

Each comic must have its own folder which must contain the chapters/volumes as archive files in CBZ or CBR formats.

The folder's name will be used as name for the comic.

NOTE: The 'unrar' or 'unar' command-line tool is required for CBR archives."""))
            popover.set_child(label)
            button.set_popover(popover)
            box.append(button)

            # Button to open local folder
            button = Gtk.Button(valign=Gtk.Align.CENTER)
            button.set_icon_name('folder-visiting-symbolic')
            button.set_tooltip_text(_('Open local folder'))
            button.connect('clicked', self.servers_page.open_local_folder)
            box.append(button)

        # Button to pin/unpin
        button = Gtk.ToggleButton(valign=Gtk.Align.CENTER)
        button.set_icon_name('view-pin-symbolic')
        button.set_tooltip_text(_('Toggle pinned status'))
        button.set_active(data['id'] in Settings.get_default().pinned_servers)
        button.connect('toggled', self.servers_page.toggle_server_pinned_state, row)
        box.append(button)

        return row

    def show(self, servers=None):
        self.servers_page.show(servers)
