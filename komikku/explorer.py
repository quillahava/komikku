# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import os
import threading
import time

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

from komikku.models import create_db_connection
from komikku.models import Manga
from komikku.models import Settings
from komikku.servers import LANGUAGES
from komikku.servers.utils import get_allowed_servers_list
from komikku.utils import get_data_dir
from komikku.utils import html_escape
from komikku.utils import log_error_traceback
from komikku.utils import create_paintable_from_data
from komikku.utils import create_paintable_from_resource


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/explorer.ui')
class Explorer(Gtk.Stack):
    __gtype_name__ = 'Explorer'

    page = 'servers'
    preselection = False
    search_filters = None
    search_lock = False
    servers_search_mode = False

    server = None
    manga = None
    manga_data = None
    manga_slug = None

    servers_page_searchbar = Gtk.Template.Child('servers_page_searchbar')
    servers_page_searchentry = Gtk.Template.Child('servers_page_searchentry')
    servers_page_listbox = Gtk.Template.Child('servers_page_listbox')
    servers_page_pinned_listbox = Gtk.Template.Child('servers_page_pinned_listbox')

    search_page_searchbar = Gtk.Template.Child('search_page_searchbar')
    search_page_searchentry = Gtk.Template.Child('search_page_searchentry')
    search_page_filter_menu_button = Gtk.Template.Child('search_page_filter_menu_button')
    search_page_listbox = Gtk.Template.Child('search_page_listbox')

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

        # Servers page
        self.servers_page_search_button = self.window.explorer_servers_page_search_button

        self.servers_page_searchbar.bind_property(
            'search-mode-enabled', self.servers_page_search_button, 'active', GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.servers_page_searchbar.connect_entry(self.servers_page_searchentry)
        self.servers_page_searchbar.connect('notify::search-mode-enabled', self.on_servers_page_search_mode_toggled)
        self.servers_page_searchbar.set_key_capture_widget(self.window)
        self.servers_page_searchentry.connect('activate', self.on_servers_page_searchentry_activated)
        self.servers_page_searchentry.connect('search-changed', self.search_servers)

        self.servers_page_pinned_listbox.connect('row-activated', self.on_server_clicked)

        self.servers_page_listbox.connect('row-activated', self.on_server_clicked)
        self.servers_page_listbox.set_filter_func(self.filter_servers)

        # Search page
        self.search_page_server_website_button = self.window.explorer_search_page_server_website_button
        self.search_page_server_website_button.connect('clicked', self.on_search_page_server_website_button_clicked)
        self.search_page_searchbar.connect_entry(self.search_page_searchentry)
        self.search_page_searchbar.set_key_capture_widget(self.window)
        self.search_page_searchentry.connect('activate', self.search)

        self.search_page_listbox.connect('row-activated', self.on_manga_clicked)

        # Card page
        self.card_page_add_read_button.connect('clicked', self.on_card_page_add_read_button_clicked)

        self.window.stack.add_named(self, 'explorer')

        self.adapt_to_width()

    def adapt_to_width(self):
        # Adapt card page to window width
        if self.window.mobile_width:
            self.card_page_cover_box.set_orientation(Gtk.Orientation.VERTICAL)
            self.card_page_cover_box.props.spacing = 12

            self.card_page_name_label.props.halign = Gtk.Align.CENTER
            self.card_page_name_label.props.justify = Gtk.Justification.CENTER

            self.card_page_status_server_label.props.halign = Gtk.Align.CENTER
            self.card_page_status_server_label.props.justify = Gtk.Justification.CENTER

            self.card_page_authors_label.props.halign = Gtk.Align.CENTER
            self.card_page_authors_label.props.justify = Gtk.Justification.CENTER

            self.card_page_add_read_button.props.halign = Gtk.Align.CENTER
        else:
            self.card_page_cover_box.set_orientation(Gtk.Orientation.HORIZONTAL)
            self.card_page_cover_box.props.spacing = 24

            self.card_page_name_label.props.halign = Gtk.Align.START
            self.card_page_name_label.props.justify = Gtk.Justification.LEFT

            self.card_page_status_server_label.props.halign = Gtk.Align.START
            self.card_page_status_server_label.props.justify = Gtk.Justification.LEFT

            self.card_page_authors_label.props.halign = Gtk.Align.START
            self.card_page_authors_label.props.justify = Gtk.Justification.LEFT

            self.card_page_add_read_button.props.halign = Gtk.Align.START

    def build_server_row(self, data):
        row = Gtk.ListBoxRow()
        row.add_css_class('explorer-listboxrow')

        row.server_data = data
        if 'manga_initial_data' in data:
            row.manga_data = data.pop('manga_initial_data')

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_child(box)

        # Server logo
        logo = Gtk.Image()
        logo.set_size_request(28, 28)
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
            label.set_markup("""A specific folder structure is required
for local comics to be properly processed.

Each comic must have its own folder which
must contain the chapters as archive files
in CBZ or CBR formats.

The folder's name will be used as name
for the comic.

The 'unrar' utility is required for
CBR format archives.
""")
            popover.set_child(label)
            button.set_popover(popover)
            box.append(button)

            # Button to open local folder
            button = Gtk.Button(valign=Gtk.Align.CENTER)
            button.set_icon_name('folder-symbolic')
            button.set_tooltip_text(_('Open local folder'))
            button.connect('clicked', self.open_local_folder)
            box.append(button)

        # Button to pin/unpin
        button = Gtk.ToggleButton(valign=Gtk.Align.CENTER)
        button.set_icon_name('view-pin-symbolic')
        button.set_active(data['id'] in Settings.get_default().pinned_servers)
        button.connect('toggled', self.toggle_server_pinned_state, row)
        box.append(button)

        return row

    def clear_search_page_results(self):
        self.search_page_listbox.hide()

        child = self.search_page_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.search_page_listbox.remove(child)
            child = next_child

    def clear_search_page_search(self):
        self.search_page_searchentry.set_text('')
        self.clear_search_page_results()
        self.init_search_page_filters()

    def filter_servers(self, row):
        """
        This function gets one row and has to return:
        - True if the row should be displayed
        - False if the row should not be displayed
        """
        term = self.servers_page_searchentry.get_text().strip().lower()

        if not hasattr(row, 'server_data'):
            # Languages headers should always be displayed
            return True

        server_name = row.server_data['name']
        server_lang = row.server_data['lang']

        # Search in name and language
        return (
            term in server_name.lower() or
            term in LANGUAGES[server_lang].lower() or
            term in server_lang.lower()
        )

    def init_search_page_filters(self):
        self.search_filters = {}

        if getattr(self.server, 'filters', None) is None:
            self.search_page_filter_menu_button.set_popover(None)
            return

        def build_checkbox(filter):
            self.search_filters[filter['key']] = filter['default']

            def toggle(button, _param):
                self.search_filters[filter['key']] = button.get_active()

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

            check_button = Gtk.CheckButton(label=filter['name'], active=filter['default'], tooltip_text=filter['description'])
            check_button.connect('notify::active', toggle)
            vbox.append(check_button)

            return vbox

        def build_entry(filter):
            self.search_filters[filter['key']] = filter['default']

            def on_text_changed(buf, _param):
                self.search_filters[filter['key']] = buf.get_text()

            entry = Gtk.Entry(text=filter['default'], placeholder_text=filter['name'], tooltip_text=filter['description'])
            entry.get_buffer().connect('notify::text', on_text_changed)

            return entry

        def build_select_single(filter):
            self.search_filters[filter['key']] = filter['default']

            def toggle_option(button, _param, key):
                if button.get_active():
                    self.search_filters[filter['key']] = key

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

            last = None
            for option in filter['options']:
                is_active = option['key'] == filter['default']
                radio_button = Gtk.CheckButton(label=option['name'])
                radio_button.set_group(last)
                radio_button.set_active(is_active)
                radio_button.connect('notify::active', toggle_option, option['key'])
                vbox.append(radio_button)
                last = radio_button

            return vbox

        def build_select_multiple(filter):
            self.search_filters[filter['key']] = [option['key'] for option in filter['options'] if option['default']]

            def toggle_option(button, _param, key):
                if button.get_active():
                    self.search_filters[filter['key']].append(key)
                else:
                    self.search_filters[filter['key']].remove(key)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

            for option in filter['options']:
                check_button = Gtk.CheckButton(label=option['name'], active=option['default'])
                check_button.connect('notify::active', toggle_option, option['key'])
                vbox.append(check_button)

            return vbox

        popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        last = None
        for filter in self.server.filters:
            if filter['type'] == 'checkbox':
                filter_widget = build_checkbox(filter)
            elif filter['type'] == 'entry':
                filter_widget = build_entry(filter)
            elif filter['type'] == 'select':
                if filter['value_type'] == 'single':
                    filter_widget = build_select_single(filter)
                elif filter['value_type'] == 'multiple':
                    filter_widget = build_select_multiple(filter)
                else:
                    raise NotImplementedError('Invalid select value_type')

                label = Gtk.Label(label=filter['name'], tooltip_text=filter['description'], sensitive=False)
                if last:
                    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    vbox.append(sep)
                vbox.append(label)
            else:
                raise NotImplementedError('Invalid filter type')

            vbox.append(filter_widget)
            last = filter_widget

        popover.set_child(vbox)

        self.search_page_filter_menu_button.set_popover(popover)

    def navigate_back(self, source):
        if self.page == 'servers':
            # Back to Library if:
            # - user click on 'Back' button
            # - or use 'Esc' key and 'severs' page in not in search mode
            if source == 'click' or not self.servers_page_searchbar.get_search_mode():
                self.window.library.show()

            # Leave search mode
            if self.servers_page_searchbar.get_search_mode():
                self.servers_page_searchbar.set_search_mode(False)
        elif self.page == 'search':
            self.search_lock = False
            self.server = None

            # Stop activity indicator in case of search page is left before the end of a search
            self.window.activity_indicator.stop()

            # Restore focus to search entry if in search mode
            if self.servers_page_searchbar.get_search_mode():
                self.servers_page_searchentry.grab_focus()

            self.show_page('servers')
        elif self.page == 'card':
            self.manga_slug = None

            # Restore focus to search entry
            self.search_page_searchentry.grab_focus()

            if self.preselection:
                self.show_page('servers')
            else:
                self.show_page('search')

    def on_card_page_add_button_clicked(self):
        def run():
            manga = Manga.new(self.manga_data, self.server, Settings.get_default().long_strip_detection)
            GLib.idle_add(complete, manga)

        def complete(manga):
            self.manga = manga

            self.window.show_notification(_('{0} manga added').format(self.manga.name))

            self.window.library.on_manga_added(self.manga)

            self.card_page_add_read_button.set_sensitive(True)
            self.card_page_add_read_button.get_child().get_first_child().set_from_icon_name('media-playback-start-symbolic')
            self.card_page_add_read_button.get_child().get_last_child().set_text(_('Read'))
            self.window.activity_indicator.stop()

            return False

        self.window.activity_indicator.start()
        self.card_page_add_read_button.set_sensitive(False)

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def on_card_page_add_read_button_clicked(self, _button):
        if self.manga:
            self.on_card_page_read_button_clicked()
        else:
            self.on_card_page_add_button_clicked()

    def on_card_page_read_button_clicked(self):
        self.window.card.init(self.manga, transition=False)

    def on_manga_clicked(self, listbox, row):
        if row.manga_data is None:
            return

        self.populate_card(row.manga_data)

    def on_resize(self):
        self.adapt_to_width()

    def on_search_page_server_website_button_clicked(self, _button):
        if self.server.base_url:
            Gtk.show_uri(None, self.server.base_url, time.time())
        else:
            self.window.show_notification(_('Oops, server website URL is unknown.'), 2)

    def on_server_clicked(self, listbox, row):
        self.server = getattr(row.server_data['module'], row.server_data['class_name'])()
        if hasattr(row, 'manga_data'):
            self.populate_card(row.manga_data)
        else:
            self.show_page('search')

    def on_servers_page_search_mode_toggled(self, _searchbar, _gparam):
        if self.servers_page_searchbar.get_search_mode():
            self.servers_page_pinned_listbox.hide()
        elif len(Settings.get_default().pinned_servers):
            self.servers_page_pinned_listbox.show()

    def on_servers_page_searchentry_activated(self, _entry):
        if not self.servers_page_searchbar.get_search_mode():
            return

        # Select first search result
        for child_row in self.servers_page_listbox:
            if not hasattr(child_row, 'server_data') or not self.filter_servers(child_row):
                continue
            self.on_server_clicked(self.servers_page_listbox, child_row)
            break

    def open_local_folder(self, _button):
        path = os.path.join(get_data_dir(), 'local')
        Gio.app_info_launch_default_for_uri(f'file://{path}')

    def populate_card(self, manga_data):
        def run(server, manga_slug):
            try:
                current_manga_data = server.get_manga_data(manga_data)

                if current_manga_data is not None:
                    GLib.idle_add(complete, current_manga_data, server)
                else:
                    GLib.idle_add(error, server, manga_slug)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, server, manga_slug, user_error_message)

        def complete(manga_data, server):
            if server != self.server or manga_data['slug'] != self.manga_slug:
                return False

            self.manga_data = manga_data

            # Populate manga card
            try:
                cover_data = self.server.get_manga_cover_image(self.manga_data.get('cover'))
            except Exception as e:
                cover_data = None
                user_error_message = log_error_traceback(e)
                if user_error_message:
                    self.window.show_notification(user_error_message)

            if cover_data is None:
                paintable = create_paintable_from_resource('/info/febvre/Komikku/images/missing_file.png', 174, -1)
            else:
                paintable = create_paintable_from_data(cover_data, 174, -1)
                if paintable is None:
                    paintable = create_paintable_from_resource('/info/febvre/Komikku/images/missing_file.png', 174, -1)

            self.card_page_cover_image.set_paintable(paintable)

            self.card_page_name_label.set_label(manga_data['name'])

            authors = html_escape(', '.join(self.manga_data['authors'])) if self.manga_data['authors'] else _('Unknown author')
            self.card_page_authors_label.set_markup(authors)

            if self.manga_data['server_id'] != 'local':
                self.card_page_status_server_label.set_markup(
                    '{0} · <a href="{1}">{2}</a> ({3})'.format(
                        _(Manga.STATUSES[self.manga_data['status']]) if self.manga_data['status'] else _('Unknown status'),
                        self.server.get_manga_url(self.manga_data['slug'], self.manga_data.get('url')),
                        html_escape(self.server.name),
                        self.server.lang.upper()
                    )
                )
            else:
                self.card_page_status_server_label.set_markup(
                    '{0} · {1}'.format(
                        _('Unknown status'),
                        html_escape(_('Local'))
                    )
                )

            if self.manga_data['genres']:
                self.card_page_genres_label.set_markup(html_escape(', '.join(self.manga_data['genres'])))
                self.card_page_genres_label.get_parent().get_parent().show()
            else:
                self.card_page_genres_label.get_parent().get_parent().hide()

            if self.manga_data['scanlators']:
                self.card_page_scanlators_label.set_markup(html_escape(', '.join(self.manga_data['scanlators'])))
                self.card_page_scanlators_label.get_parent().get_parent().show()
            else:
                self.card_page_scanlators_label.get_parent().get_parent().hide()

            self.card_page_chapters_label.set_markup(str(len(self.manga_data['chapters'])))

            if self.manga_data['chapters']:
                self.card_page_last_chapter_label.set_markup(html_escape(self.manga_data['chapters'][-1]['title']))
                self.card_page_last_chapter_label.get_parent().get_parent().show()
            else:
                self.card_page_last_chapter_label.get_parent().get_parent().hide()

            self.card_page_synopsis_label.set_markup(
                html_escape(self.manga_data['synopsis']) if self.manga_data['synopsis'] else '-'
            )

            self.window.activity_indicator.stop()
            self.show_page('card')

            return False

        def error(server, manga_slug, message=None):
            if server != self.server or manga_slug != self.manga_slug:
                return False

            self.window.activity_indicator.stop()

            self.window.show_notification(message or _("Oops, failed to retrieve manga's information."), 2)

            return False

        self.manga = None
        self.manga_slug = manga_data['slug']
        self.window.activity_indicator.start()

        thread = threading.Thread(target=run, args=(self.server, self.manga_slug, ))
        thread.daemon = True
        thread.start()

    def populate_pinned_servers(self):
        row = self.servers_page_pinned_listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            self.servers_page_pinned_listbox.remove(row)
            row = next_row

        pinned_servers = Settings.get_default().pinned_servers

        servers_ids = [server_data['id'] for server_data in self.servers]
        for pinned_server in pinned_servers[:]:
            if pinned_server not in servers_ids:
                # Pinned server no longer belongs to the allowed servers
                pinned_servers.remove(pinned_server)
                Settings.get_default().remove_pinned_server(pinned_server)

        if len(pinned_servers) == 0:
            self.servers_page_pinned_listbox.hide()
            return

        # Add header
        row = Gtk.ListBoxRow(activatable=False)
        row.add_css_class('explorer-section-listboxrow')
        label = Gtk.Label(xalign=0)
        label.add_css_class('subtitle')
        label.set_text(_('Pinned').upper())
        row.set_child(label)
        self.servers_page_pinned_listbox.append(row)

        for server_data in self.servers:
            if server_data['id'] not in pinned_servers:
                continue

            row = self.build_server_row(server_data)
            self.servers_page_pinned_listbox.append(row)

        self.servers_page_pinned_listbox.show()

    def populate_servers(self, servers=None):
        if not servers:
            self.servers = get_allowed_servers_list(Settings.get_default())
            self.populate_pinned_servers()
        else:
            self.servers = servers
            self.preselection = True

        row = self.servers_page_listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            self.servers_page_listbox.remove(row)
            row = next_row

        last_lang = None
        for server_data in self.servers:
            if server_data['lang'] != last_lang:
                # Add language header
                last_lang = server_data['lang']

                row = Gtk.ListBoxRow(activatable=False)
                row.add_css_class('explorer-section-listboxrow')
                label = Gtk.Label(xalign=0)
                label.add_css_class('subtitle')
                label.set_text(LANGUAGES[server_data['lang']].upper() if server_data['lang'] else _('Other'))
                row.set_child(label)
                self.servers_page_listbox.append(row)

            row = self.build_server_row(server_data)
            self.servers_page_listbox.append(row)

        if self.preselection and len(self.servers) == 1:
            row = self.servers_page_listbox.get_children()[1]
            self.server = getattr(row.server_data['module'], row.server_data['class_name'])()
            self.populate_card(row.manga_data)
        else:
            self.show_page(self.page)

    def search(self, entry=None):
        if self.search_lock:
            return

        term = self.search_page_searchentry.get_text().strip()

        # Find manga by Id
        if term.startswith('id:'):
            slug = term[3:]

            if not slug:
                return

            self.populate_card(dict(slug=slug))
            return

        if not term and getattr(self.server, 'get_most_populars', None) is None:
            # An empty term is allowed only if server has 'get_most_populars' method
            return

        def run(server):
            most_populars = not term

            try:
                if most_populars:
                    # We offer most popular mangas as starting search results
                    result = server.get_most_populars(**self.search_filters)
                else:
                    result = server.search(term, **self.search_filters)

                if result:
                    GLib.idle_add(complete, result, server, most_populars)
                else:
                    GLib.idle_add(error, result, server)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, None, server, user_error_message)

        def complete(result, server, most_populars):
            if server != self.server:
                return False

            self.window.activity_indicator.stop()
            self.search_page_listbox.show()

            if most_populars:
                row = Gtk.ListBoxRow()
                row.add_css_class('explorer-section-listboxrow')
                row.manga_data = None
                if server.id != 'local':
                    label = Gtk.Label(label=_('Most populars').upper(), xalign=0)
                else:
                    label = Gtk.Label(label=_('Collection').upper(), xalign=0)
                label.add_css_class('subtitle')
                row.set_child(label)

                self.search_page_listbox.append(row)

            for item in result:
                row = Gtk.ListBoxRow()
                row.add_css_class('explorer-listboxrow')
                row.manga_data = item
                label = Gtk.Label(label=item['name'], xalign=0)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                row.set_child(label)

                self.search_page_listbox.append(row)

            self.search_lock = False

            return False

        def error(result, server, message=None):
            if server != self.server:
                return

            self.window.activity_indicator.stop()
            self.search_lock = False

            if message:
                self.window.show_notification(message)
            elif result is None:
                self.window.show_notification(_('Oops, search failed. Please try again.'), 2)
            elif len(result) == 0:
                self.window.show_notification(_('No results'))

        self.search_lock = True
        self.clear_search_page_results()
        self.window.activity_indicator.start()

        thread = threading.Thread(target=run, args=(self.server, ))
        thread.daemon = True
        thread.start()

    def search_servers(self, _entry):
        self.servers_page_listbox.invalidate_filter()

    def show(self, transition=True, servers=None, reset=True):
        if reset:
            self.servers_page_searchbar.set_search_mode(False)
            self.populate_servers(servers)
            self.show_page('servers')

        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.library_flap_reveal_button.hide()
        self.window.right_button_stack.set_visible_child_name('explorer.servers')
        self.window.right_button_stack.show()

        self.window.menu_button.hide()

        self.window.show_page('explorer', transition=transition)

    def show_page(self, name):
        if name == 'servers':
            self.title_label.set_text(_('Servers'))

            if self.page is None and self.servers_page_searchbar.get_search_mode():
                self.servers_page_searchbar.set_search_mode(False)

        elif name == 'search':
            self.title_label.set_text(self.server.name)

            if self.page == 'servers':
                self.clear_search_page_search()
                self.search()

        elif name == 'card':
            self.title_label.set_text(self.manga_data['name'])

            # Check if selected manga is already in library
            db_conn = create_db_connection()
            row = db_conn.execute(
                'SELECT * FROM mangas WHERE slug = ? AND server_id = ?',
                (self.manga_data['slug'], self.manga_data['server_id'])
            ).fetchone()
            db_conn.close()

            if row:
                self.manga = Manga.get(row['id'], self.server)

                self.card_page_add_read_button.get_child().get_first_child().set_from_icon_name('media-playback-start-symbolic')
                self.card_page_add_read_button.get_child().get_last_child().set_text(_('Read'))
            else:
                self.card_page_add_read_button.get_child().get_first_child().set_from_icon_name('list-add-symbolic')
                self.card_page_add_read_button.get_child().get_last_child().set_text(_('Add to Library'))

        if name in ('servers', 'search'):
            self.window.right_button_stack.set_visible_child_name('explorer.' + name)
            self.window.right_button_stack.show()
        else:
            # `Card` stack doesn't have a right button in headerbar
            self.window.right_button_stack.hide()
        self.set_visible_child_name(name)

        self.page = name

    def toggle_server_pinned_state(self, button, row):
        if button.get_active():
            Settings.get_default().add_pinned_server(row.server_data['id'])
        else:
            Settings.get_default().remove_pinned_server(row.server_data['id'])

        if row.get_parent().get_name() == 'pinned_servers':
            for child_row in self.servers_page_listbox:
                if not hasattr(child_row, 'server_data'):
                    continue

                if child_row.server_data['id'] == row.server_data['id']:
                    child_row.get_first_child().get_last_child().set_active(button.get_active())
                    break

        self.populate_pinned_servers()
