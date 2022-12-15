# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Gtk
from gi.repository import Pango

from komikku.explorer.card import ExplorerCardPage
from komikku.explorer.search import ExplorerSearchPage
from komikku.explorer.servers import ExplorerServersPage
from komikku.models import create_db_connection
from komikku.models import Manga
from komikku.models import Settings
from komikku.servers import LANGUAGES

LOGO_SIZE = 28


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/explorer.ui')
class Explorer(Gtk.Stack):
    __gtype_name__ = 'Explorer_'

    page = 'servers'
    server = None

    servers_page_searchbar = Gtk.Template.Child('servers_page_searchbar')
    servers_page_searchentry = Gtk.Template.Child('servers_page_searchentry')
    servers_page_listbox = Gtk.Template.Child('servers_page_listbox')
    servers_page_pinned_listbox = Gtk.Template.Child('servers_page_pinned_listbox')

    search_page_searchbar = Gtk.Template.Child('search_page_searchbar')
    search_page_searchentry = Gtk.Template.Child('search_page_searchentry')
    search_page_filter_menu_button = Gtk.Template.Child('search_page_filter_menu_button')
    search_page_stack = Gtk.Template.Child('search_page_stack')
    search_page_listbox = Gtk.Template.Child('search_page_listbox')
    search_page_status_page = Gtk.Template.Child('search_page_status_page')

    card_page_cover_box = Gtk.Template.Child('card_page_cover_box')
    card_page_cover_image = Gtk.Template.Child('card_page_cover_image')
    card_page_name_label = Gtk.Template.Child('card_page_name_label')
    card_page_authors_label = Gtk.Template.Child('card_page_authors_label')
    card_page_status_server_label = Gtk.Template.Child('card_page_status_server_label')
    card_page_add_read_button = Gtk.Template.Child('card_page_add_read_button')
    card_page_genres_label = Gtk.Template.Child('card_page_genres_label')
    card_page_scanlators_label = Gtk.Template.Child('card_page_scanlators_label')
    card_page_chapters_label = Gtk.Template.Child('card_page_chapters_label')
    card_page_last_chapter_label = Gtk.Template.Child('card_page_last_chapter_label')
    card_page_synopsis_label = Gtk.Template.Child('card_page_synopsis_label')

    def __init__(self, window):
        Gtk.Stack.__init__(self)

        self.window = window

        self.title_label = self.window.explorer_title_label

        self.servers_page = ExplorerServersPage(self)
        self.search_page = ExplorerSearchPage(self)
        self.card_page = ExplorerCardPage(self)

        self.window.stack.add_named(self, 'explorer')

        self.adapt_to_width()

    def adapt_to_width(self):
        self.card_page.adapt_to_width()

    def build_server_row(self, data):
        # Used in `servers` and `search` (global search) pages
        if self.search_page.global_mode:
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
            if data['is_nsfw']:
                title += ' (NSFW)'
            subtitle = LANGUAGES[data['lang']]
        else:
            title = _('Local')
            subtitle = _('Comics stored locally as archives in CBZ/CBR formats')

        label = Gtk.Label(xalign=0, hexpand=True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_text(title)
        vbox.append(label)

        label = Gtk.Label(xalign=0)
        label.set_wrap(True)
        label.set_text(subtitle)
        label.add_css_class('subtitle')
        vbox.append(label)

        box.append(vbox)

        if self.search_page.global_mode:
            return row

        # Server requires a user account
        if data['has_login']:
            label = Gtk.Image.new_from_icon_name('dialog-password-symbolic')
            box.append(label)

        if data['id'] == 'local':
            # Info button
            button = Gtk.MenuButton(valign=Gtk.Align.CENTER)
            button.set_icon_name('help-about-symbolic')
            popover = Gtk.Popover()
            label = Gtk.Label()
            label.set_wrap(True)
            label.set_max_width_chars(32)
            label.set_markup(_("""A specific folder structure is required for local comics to be properly processed.

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
        button.set_active(data['id'] in Settings.get_default().pinned_servers)
        button.connect('toggled', self.servers_page.toggle_server_pinned_state, row)
        box.append(button)

        return row

    def navigate_back(self, source):
        if self.page == 'servers':
            # Back to Library if:
            # - user click on 'Back' button
            # - or use 'Esc' key and 'severs' page in not in search mode
            if source == 'click' or not self.servers_page_searchbar.get_search_mode():
                self.window.library.show()

            # Leave search mode
            if self.servers_page.searchbar.get_search_mode():
                self.servers_page.searchbar.set_search_mode(False)
                self.servers_page.search_button.grab_focus()

        elif self.page == 'search':
            self.server = None
            self.search_page.global_mode = False
            # Stop search if not ended
            self.search_page.stop = True

            # Stop activity indicator in case of search page is left before the end of a search
            self.window.activity_indicator.stop()

            # Restore focus to search entry if in search mode
            if self.servers_page.searchbar.get_search_mode():
                self.servers_page.searchentry.grab_focus()

            self.show_page('servers')

        elif self.page == 'card':
            self.card_page.manga_slug = None

            if self.servers_page.preselection:
                self.show_page('servers')
            else:
                self.show_page('search')

    def on_resize(self):
        self.adapt_to_width()

    def show(self, transition=True, servers=None, reset=True):
        if reset:
            self.server = None
            self.search_page.global_mode = False

            self.servers_page.searchbar.set_search_mode(False)
            self.servers_page.populate(servers)
            self.show_page('servers')

        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.left_extra_button_stack.hide()

        self.window.right_button_stack.set_visible_child_name('explorer.servers')
        self.window.right_button_stack.show()

        self.window.menu_button.hide()

        self.window.show_page('explorer', transition=transition)

    def show_page(self, name):
        if name == 'servers':
            self.title_label.set_text(_('Servers'))

            if self.page is None and self.servers_page.searchbar.get_search_mode():
                self.servers_page.searchbar.set_search_mode(False)

        elif name == 'search':
            self.title_label.set_text(_('Global Search') if self.search_page.global_mode else self.server.name)

            self.search_page.searchentry.grab_focus()

            if self.page == 'servers':
                self.search_page.clear_search()

                if not self.search_page.global_mode:
                    # Load search with populars
                    self.search_page.search()

        elif name == 'card':
            self.title_label.set_text(self.card_page.manga_data['name'])

            # Check if selected manga is already in library
            db_conn = create_db_connection()
            row = db_conn.execute(
                'SELECT * FROM mangas WHERE slug = ? AND server_id = ?',
                (self.card_page.manga_data['slug'], self.card_page.manga_data['server_id'])
            ).fetchone()
            db_conn.close()

            if row:
                self.card_page.manga = Manga.get(row['id'], self.server)

                self.card_page.add_read_button.get_child().get_first_child().set_from_icon_name('media-playback-start-symbolic')
                self.card_page.add_read_button.get_child().get_last_child().set_text(_('Read'))
            else:
                self.card_page.add_read_button.get_child().get_first_child().set_from_icon_name('list-add-symbolic')
                self.card_page.add_read_button.get_child().get_last_child().set_text(_('Add to Library'))

        if name == 'servers' or (name == 'search' and not self.search_page.global_mode):
            self.window.right_button_stack.set_visible_child_name('explorer.' + name)
            self.window.right_button_stack.show()
        else:
            # `Search` (in global mode) and `Card` pages doesn't have a right button in headerbar
            self.window.right_button_stack.hide()
        self.set_visible_child_name(name)

        self.page = name