# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Adw
from gi.repository import GLib
from gi.repository import Gtk

from komikku.models import Settings
from komikku.models.database import clear_cached_data
from komikku.models.keyring import KeyringHelper
from komikku.servers import LANGUAGES
from komikku.servers.utils import get_server_main_id_by_id
from komikku.servers.utils import get_servers_list
from komikku.utils import folder_size
from komikku.utils import get_cached_data_dir
from komikku.utils import html_escape


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/preferences.ui')
class PreferencesPage(Adw.NavigationPage):
    __gtype_name__ = 'PreferencesPage'

    title_stack = Gtk.Template.Child('title_stack')
    title = Gtk.Template.Child('title')

    pages_stack = Gtk.Template.Child('pages_stack')
    viewswitcherbar = Gtk.Template.Child('viewswitcherbar')

    color_scheme_row = Gtk.Template.Child('color_scheme_row')
    night_light_switch = Gtk.Template.Child('night_light_switch')
    desktop_notifications_switch = Gtk.Template.Child('desktop_notifications_switch')
    card_backdrop_switch = Gtk.Template.Child('card_backdrop_switch')

    library_display_mode_row = Gtk.Template.Child('library_display_mode_row')
    library_servers_logo_switch = Gtk.Template.Child('library_servers_logo_switch')
    library_badge_unread_chapters_switch = Gtk.Template.Child('library_badge_unread_chapters_switch')
    library_badge_downloaded_chapters_switch = Gtk.Template.Child('library_badge_downloaded_chapters_switch')
    library_badge_recent_chapters_switch = Gtk.Template.Child('library_badge_recent_chapters_switch')
    update_at_startup_switch = Gtk.Template.Child('update_at_startup_switch')
    new_chapters_auto_download_switch = Gtk.Template.Child('new_chapters_auto_download_switch')
    nsfw_content_switch = Gtk.Template.Child('nsfw_content_switch')
    nsfw_only_content_switch = Gtk.Template.Child('nsfw_only_content_switch')
    servers_languages_actionrow = Gtk.Template.Child('servers_languages_actionrow')
    servers_settings_actionrow = Gtk.Template.Child('servers_settings_actionrow')
    long_strip_detection_switch = Gtk.Template.Child('long_strip_detection_switch')

    reading_mode_row = Gtk.Template.Child('reading_mode_row')
    clamp_size_adjustment = Gtk.Template.Child('clamp_size_adjustment')
    scaling_row = Gtk.Template.Child('scaling_row')
    landscape_zoom_switch = Gtk.Template.Child('landscape_zoom_switch')
    background_color_row = Gtk.Template.Child('background_color_row')
    borders_crop_switch = Gtk.Template.Child('borders_crop_switch')
    page_numbering_switch = Gtk.Template.Child('page_numbering_switch')
    fullscreen_switch = Gtk.Template.Child('fullscreen_switch')

    clear_cached_data_actionrow = Gtk.Template.Child('clear_cached_data_actionrow')
    clear_cached_data_on_app_close_switch = Gtk.Template.Child('clear_cached_data_on_app_close_switch')
    credentials_storage_plaintext_fallback_switch = Gtk.Template.Child('credentials_storage_plaintext_fallback_switch')
    disable_animations_switch = Gtk.Template.Child('disable_animations_switch')

    def __init__(self, window):
        Adw.NavigationPage.__init__(self)

        self.window = window

        self.window.breakpoint.add_setter(self.viewswitcherbar, 'reveal', True)
        self.window.breakpoint.add_setter(self.title_stack, 'visible-child', self.title)

        self.settings = Settings.get_default()

        self.set_config_values()

        self.window.navigationview.add(self)

    def on_background_color_changed(self, row, _gparam):
        index = row.get_selected()

        if index == 0:
            self.settings.background_color = 'white'
        elif index == 1:
            self.settings.background_color = 'black'
        elif index == 2:
            self.settings.background_color = 'gray'
        elif index == 3:
            self.settings.background_color = 'system-style'

    def on_borders_crop_changed(self, switch_button, _gparam):
        self.settings.borders_crop = switch_button.get_active()

    def on_card_backdrop_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.card_backdrop = True
            self.window.card.set_backdrop()
        else:
            self.settings.card_backdrop = False
            self.window.card.remove_backdrop()

    def on_color_scheme_changed(self, row, _gparam):
        index = row.get_selected()

        if index == 0:
            self.settings.color_scheme = 'light'
        elif index == 1:
            self.settings.color_scheme = 'dark'
        elif index == 2:
            self.settings.color_scheme = 'default'

        self.window.init_theme()

    def on_clamp_size_changed(self, adjustment):
        self.settings.clamp_size = int(adjustment.get_value())

    def on_clear_cached_data_activated(self, _actionrow):
        # Clear cached data of manga not in library
        # If a manga is being read, it must be excluded

        def confirm_callback():
            manga_in_use = None
            if self.window.previous_page in ('card', 'reader') and not self.window.card.manga.in_library:
                manga_in_use = self.window.card.manga

            clear_cached_data(manga_in_use)
            self.update_cached_data_size()

            if self.window.previous_page == 'history':
                self.window.history.populate()

        self.window.confirm(
            _('Clear?'),
            _('Are you sure you want to clear chapters cache and database?'),
            _('Clear'),
            confirm_callback,
            confirm_appearance=Adw.ResponseAppearance.DESTRUCTIVE
        )

    def on_clear_cached_data_on_app_close_changed(self, switch_button, _gparam):
        self.settings.clear_cached_data_on_app_close = switch_button.get_active()

    def on_credentials_storage_plaintext_fallback_changed(self, switch_button, _gparam):
        self.settings.credentials_storage_plaintext_fallback = switch_button.get_active()

    def on_desktop_notifications_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.desktop_notifications = True
        else:
            self.settings.desktop_notifications = False

    def on_disable_animations_changed(self, switch_button, _gparam):
        def on_cancel():
            switch_button.set_active(False)

        def on_confirm():
            self.settings.disable_animations = True
            Gtk.Settings.get_default().set_property('gtk-enable-animations', False)

        if switch_button.get_active():
            self.window.confirm(
                _('Disable animations?'),
                _('Are you sure you want to disable animations?\n\nThe gesture navigation in the reader will not work properly anymore.'),
                _('Disable'),
                on_confirm,
                cancel_callback=on_cancel
            )
        else:
            self.settings.disable_animations = False
            Gtk.Settings.get_default().set_property('gtk-enable-animations', True)

    def on_fullscreen_changed(self, switch_button, _gparam):
        self.settings.fullscreen = switch_button.get_active()

    def on_landscape_zoom_changed(self, switch_button, _gparam):
        self.settings.landscape_zoom = switch_button.get_active()

    def on_library_badge_changed(self, switch_button, _gparam):
        badges = self.settings.library_badges
        if switch_button.get_active():
            if switch_button._value not in badges:
                badges.append(switch_button._value)
        else:
            if switch_button._value in badges:
                badges.remove(switch_button._value)
        self.settings.library_badges = badges

        GLib.idle_add(self.window.library.populate)

    def on_library_display_mode_changed(self, row, _gparam):
        index = row.get_selected()

        if index == 0:
            self.settings.library_display_mode = 'grid'
        elif index == 1:
            self.settings.library_display_mode = 'grid-compact'

        GLib.idle_add(self.window.library.populate)

    def on_library_servers_logo_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.library_servers_logo = True
        else:
            self.settings.library_servers_logo = False

        GLib.idle_add(self.window.library.populate)

    def on_long_strip_detection_changed(self, switch_button, _gparam):
        self.settings.long_strip_detection = switch_button.get_active()

    def on_new_chapters_auto_download_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.new_chapters_auto_download = True
        else:
            self.settings.new_chapters_auto_download = False

    def on_night_light_changed(self, switch_button, _gparam):
        self.settings.night_light = switch_button.get_active()

        self.window.init_theme()

    def on_nsfw_content_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.nsfw_content = True
        else:
            self.settings.nsfw_content = False

        # Update Servers settings subpage
        self.servers_settings_subpage.populate()

    def on_nsfw_only_content_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.nsfw_only_content = True
        else:
            self.settings.nsfw_only_content = False

        # Update Servers settings subpage
        self.servers_settings_subpage.populate()

    def on_page_numbering_changed(self, switch_button, _gparam):
        self.settings.page_numbering = not switch_button.get_active()

    def on_reading_mode_changed(self, row, _gparam):
        index = row.get_selected()

        if index == 0:
            self.settings.reading_mode = 'right-to-left'
        elif index == 1:
            self.settings.reading_mode = 'left-to-right'
        elif index == 2:
            self.settings.reading_mode = 'vertical'
        elif index == 3:
            self.settings.reading_mode = 'webtoon'

    def on_scaling_changed(self, row, _gparam):
        index = row.get_selected()

        if index == 0:
            self.settings.scaling = 'screen'
        elif index == 1:
            self.settings.scaling = 'width'
        elif index == 2:
            self.settings.scaling = 'height'
        elif index == 3:
            self.settings.scaling = 'original'

    def on_update_at_startup_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.update_at_startup = True
        else:
            self.settings.update_at_startup = False

    def set_config_values(self):
        #
        # General
        #

        # Theme
        if not Adw.StyleManager.get_default().get_system_supports_color_schemes():
            # System doesn't support color schemes
            self.color_scheme_row.get_model().remove(2)
            if self.settings.color_scheme == 'default':
                self.settings.color_scheme = 'light'
        self.color_scheme_row.set_selected(self.settings.color_scheme_value)
        self.color_scheme_row.connect('notify::selected', self.on_color_scheme_changed)

        # Night light
        self.night_light_switch.set_active(self.settings.night_light)
        self.night_light_switch.connect('notify::active', self.on_night_light_changed)

        # Desktop notifications
        self.desktop_notifications_switch.set_active(self.settings.desktop_notifications)
        self.desktop_notifications_switch.connect('notify::active', self.on_desktop_notifications_changed)

        # Card backdrop
        self.card_backdrop_switch.set_active(self.settings.card_backdrop)
        self.card_backdrop_switch.connect('notify::active', self.on_card_backdrop_changed)

        #
        # Library
        #

        # Display mode
        self.library_display_mode_row.set_selected(self.settings.library_display_mode_value)
        self.library_display_mode_row.connect('notify::selected', self.on_library_display_mode_changed)

        # Servers logo
        self.library_servers_logo_switch.set_active(self.settings.library_servers_logo)
        self.library_servers_logo_switch.connect('notify::active', self.on_library_servers_logo_changed)

        # Badges
        self.library_badge_unread_chapters_switch.set_active('unread-chapters' in self.settings.library_badges)
        self.library_badge_unread_chapters_switch._value = 'unread-chapters'
        self.library_badge_unread_chapters_switch.connect('notify::active', self.on_library_badge_changed)
        self.library_badge_downloaded_chapters_switch.set_active('downloaded-chapters' in self.settings.library_badges)
        self.library_badge_downloaded_chapters_switch._value = 'downloaded-chapters'
        self.library_badge_downloaded_chapters_switch.connect('notify::active', self.on_library_badge_changed)
        self.library_badge_recent_chapters_switch.set_active('recent-chapters' in self.settings.library_badges)
        self.library_badge_recent_chapters_switch._value = 'recent-chapters'
        self.library_badge_recent_chapters_switch.connect('notify::active', self.on_library_badge_changed)

        # Update manga at startup
        self.update_at_startup_switch.set_active(self.settings.update_at_startup)
        self.update_at_startup_switch.connect('notify::active', self.on_update_at_startup_changed)

        # Auto download new chapters
        self.new_chapters_auto_download_switch.set_active(self.settings.new_chapters_auto_download)
        self.new_chapters_auto_download_switch.connect('notify::active', self.on_new_chapters_auto_download_changed)

        # Servers languages
        self.servers_languages_subpage = PreferencesServersLanguagesSubPage(self)
        self.window.navigationview.add(self.servers_languages_subpage)
        self.servers_languages_actionrow.props.activatable = True
        self.servers_languages_actionrow.connect('activated', self.servers_languages_subpage.present)

        # Servers settings
        self.servers_settings_subpage = PreferencesServersSettingsSubPage(self)
        self.window.navigationview.add(self.servers_settings_subpage)
        self.servers_settings_actionrow.props.activatable = True
        self.servers_settings_actionrow.connect('activated', self.servers_settings_subpage.present)

        # Long strip detection
        self.long_strip_detection_switch.set_active(self.settings.long_strip_detection)
        self.long_strip_detection_switch.connect('notify::active', self.on_long_strip_detection_changed)

        # NSFW content
        self.nsfw_content_switch.set_active(self.settings.nsfw_content)
        self.nsfw_content_switch.connect('notify::active', self.on_nsfw_content_changed)

        # NSFW only content
        self.nsfw_only_content_switch.set_active(self.settings.nsfw_only_content)
        self.nsfw_only_content_switch.connect('notify::active', self.on_nsfw_only_content_changed)

        #
        # Reader
        #

        # Reading mode
        self.reading_mode_row.set_selected(self.settings.reading_mode_value)
        self.reading_mode_row.connect('notify::selected', self.on_reading_mode_changed)

        # Pager clamp size ('Webtoon' reading mode only)
        self.clamp_size_adjustment.set_value(self.settings.clamp_size)
        self.clamp_size_adjustment.connect('value-changed', self.on_clamp_size_changed)

        # Image scaling
        self.scaling_row.set_selected(self.settings.scaling_value)
        self.scaling_row.connect('notify::selected', self.on_scaling_changed)

        # Landscape pages zoom ('LTR/RTL/Vertical' reading modes with 'Adapt to Screen' scaling only)
        self.landscape_zoom_switch.set_active(self.settings.landscape_zoom)
        self.landscape_zoom_switch.connect('notify::active', self.on_landscape_zoom_changed)

        # Background color
        self.background_color_row.set_selected(self.settings.background_color_value)
        self.background_color_row.connect('notify::selected', self.on_background_color_changed)

        # Borders crop
        self.borders_crop_switch.set_active(self.settings.borders_crop)
        self.borders_crop_switch.connect('notify::active', self.on_borders_crop_changed)

        # Page numbering
        self.page_numbering_switch.set_active(not self.settings.page_numbering)
        self.page_numbering_switch.connect('notify::active', self.on_page_numbering_changed)

        # Full screen
        self.fullscreen_switch.set_active(self.settings.fullscreen)
        self.fullscreen_switch.connect('notify::active', self.on_fullscreen_changed)

        #
        # Advanced
        #

        # Clear chapters cache and database
        self.clear_cached_data_actionrow.connect('activated', self.on_clear_cached_data_activated)

        # Clear chapters cache and database on app close
        self.clear_cached_data_on_app_close_switch.set_active(self.settings.clear_cached_data_on_app_close)
        self.clear_cached_data_on_app_close_switch.connect('notify::active', self.on_clear_cached_data_on_app_close_changed)

        # Credentials storage: allow plaintext as fallback
        self.credentials_storage_plaintext_fallback_switch.set_active(self.settings.credentials_storage_plaintext_fallback)
        self.credentials_storage_plaintext_fallback_switch.connect('notify::active', self.on_credentials_storage_plaintext_fallback_changed)

        # Disable animations
        if Gtk.Settings.get_default().get_property('gtk-enable-animations'):
            Gtk.Settings.get_default().set_property('gtk-enable-animations', not Settings.get_default().disable_animations)
            self.disable_animations_switch.set_active(self.settings.disable_animations)
        else:
            # GTK animations are already disabled (in GNOME Settings for ex.)
            self.disable_animations_switch.get_parent().get_parent().get_parent().set_sensitive(False)
            self.disable_animations_switch.set_active(False)

        self.disable_animations_switch.connect('notify::active', self.on_disable_animations_changed)

    def show(self, transition=True):
        # Update maximum value of clamp size adjustment
        self.clamp_size_adjustment.set_upper(self.window.monitor.props.geometry.width)

        self.update_cached_data_size()

        self.window.navigationview.push(self)

    def update_cached_data_size(self):
        self.clear_cached_data_actionrow.set_subtitle(folder_size(get_cached_data_dir()) or '-')


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/preferences_servers_languages.ui')
class PreferencesServersLanguagesSubPage(Adw.NavigationPage):
    __gtype_name__ = 'PreferencesServersLanguagesSubPage'

    group = Gtk.Template.Child('group')

    def __init__(self, parent):
        Adw.NavigationPage.__init__(self)

        self.parent = parent
        self.window = self.parent.window
        self.settings = Settings.get_default()

        servers_languages = self.settings.servers_languages

        for code, language in LANGUAGES.items():
            switchrow = Adw.SwitchRow()
            switchrow.set_title(language)
            switchrow.set_active(code in servers_languages)
            switchrow.connect('notify::active', self.on_language_activated, code)

            self.group.add(switchrow)

    def on_language_activated(self, switchrow, _gparam, code):
        if switchrow.get_active():
            self.settings.add_servers_language(code)
        else:
            self.settings.remove_servers_language(code)

        # Update Servers settings subpage
        self.parent.servers_settings_subpage.populate()
        # Update Explorer servers page
        if self.window.explorer.servers_page in self.window.navigationview.get_navigation_stack():
            self.window.explorer.servers_page.populate()

    def present(self, _widget):
        self.window.navigationview.push(self)


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/preferences_servers_settings.ui')
class PreferencesServersSettingsSubPage(Adw.NavigationPage):
    __gtype_name__ = 'PreferencesServersSettingsSubPage'

    group = Gtk.Template.Child('group')

    def __init__(self, parent):
        Adw.NavigationPage.__init__(self)

        self.parent = parent
        self.window = self.parent.window
        self.settings = Settings.get_default()
        self.keyring_helper = KeyringHelper()

        self.populate()

    def on_server_activated(self, row, _gparam, server_main_id):
        if isinstance(row, Adw.ExpanderRow):
            self.settings.toggle_server(server_main_id, row.get_enable_expansion())
        else:
            self.settings.toggle_server(server_main_id, row.get_active())

        # Update explorer servers page
        if self.window.explorer.servers_page in self.window.navigationview.get_navigation_stack():
            self.window.explorer.servers_page.populate()

    def on_server_language_activated(self, switch_button, _gparam, server_main_id, lang):
        self.settings.toggle_server_lang(server_main_id, lang, switch_button.get_active())

        # Update explorer servers page
        if self.window.explorer.servers_page in self.window.navigationview.get_navigation_stack():
            self.window.explorer.servers_page.populate()

    def populate(self):
        settings = self.settings.servers_settings
        languages = self.settings.servers_languages
        credentials_storage_plaintext_fallback = self.settings.credentials_storage_plaintext_fallback

        # Clear
        child = self.group.get_first_child().get_last_child().get_first_child().get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.group.remove(child)
            child = next_child

        servers = get_servers_list(order_by=('name', 'lang'))
        self.window.application.logger.info('{0} servers found'.format(len(servers)))

        servers_data = {}
        for server_data in servers:
            main_id = get_server_main_id_by_id(server_data['id'])

            if main_id not in servers_data:
                servers_data[main_id] = dict(
                    main_id=main_id,
                    name=server_data['name'],
                    module=server_data['module'],
                    is_nsfw=server_data['is_nsfw'],
                    is_nsfw_only=server_data['is_nsfw_only'],
                    langs=[],
                )

            if not languages or server_data['lang'] in languages:
                servers_data[main_id]['langs'].append(server_data['lang'])

        for server_main_id, server_data in servers_data.items():
            if not server_data['langs']:
                continue

            server_class = getattr(server_data['module'], server_data['main_id'].capitalize())
            server_settings = settings.get(server_main_id)

            server_allowed = not server_data['is_nsfw'] or (server_data['is_nsfw'] and self.settings.nsfw_content)
            server_allowed &= not server_data['is_nsfw_only'] or (server_data['is_nsfw_only'] and self.settings.nsfw_only_content)
            server_enabled = server_settings is None or server_settings['enabled'] is True

            if len(server_data['langs']) > 1 or server_class.has_login:
                vbox = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL,
                    margin_start=12, margin_top=6, margin_end=12, margin_bottom=6,
                    spacing=12
                )

                expander_row = Adw.ExpanderRow()
                expander_row.set_title(html_escape(server_data['name']))
                if server_data['is_nsfw'] or server_data['is_nsfw_only']:
                    expander_row.set_subtitle(_('18+'))
                expander_row.set_enable_expansion(server_enabled)
                expander_row.set_sensitive(server_allowed)
                expander_row.connect('notify::enable-expansion', self.on_server_activated, server_main_id)
                expander_row.add_row(vbox)

                self.group.add(expander_row)

                if len(server_data['langs']) > 1:
                    for lang in server_data['langs']:
                        lang_enabled = server_settings is None or server_settings['langs'].get(lang, True)

                        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, margin_top=6, margin_bottom=6, spacing=12)

                        label = Gtk.Label(label=LANGUAGES[lang], xalign=0, hexpand=True)
                        hbox.append(label)

                        switch = Gtk.Switch.new()
                        switch.set_active(lang_enabled)
                        switch.connect('notify::active', self.on_server_language_activated, server_main_id, lang)
                        hbox.append(switch)

                        vbox.append(hbox)

                if server_class.has_login:
                    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=12, margin_bottom=12, spacing=12)
                    vbox.append(box)

                    label = Gtk.Label(label=_('User Account'))
                    label.set_valign(Gtk.Align.CENTER)
                    box.append(label)

                    group = Adw.PreferencesGroup()

                    if server_class.base_url is None:
                        # Server has a customizable address/base_url (ex. Komga)
                        address_entry = Adw.EntryRow(title=_('Address'))
                        address_entry.add_prefix(Gtk.Image.new_from_icon_name('network-server-symbolic'))
                        group.add(address_entry)
                    else:
                        address_entry = None

                    username_entry = Adw.EntryRow(title=_('Username'))
                    username_entry.add_prefix(Gtk.Image.new_from_icon_name('avatar-default-symbolic'))
                    group.add(username_entry)

                    password_entry = Adw.PasswordEntryRow(title=_('Password'))
                    password_entry.add_prefix(Gtk.Image.new_from_icon_name('dialog-password-symbolic'))
                    group.add(password_entry)

                    box.append(group)

                    plaintext_checkbutton = None
                    if self.keyring_helper.is_disabled or not self.keyring_helper.has_recommended_backend:
                        label = Gtk.Label(hexpand=True)
                        label.set_wrap(True)
                        if self.keyring_helper.is_disabled:
                            label.add_css_class('dim-label')
                            label.set_text(_('System keyring service is disabled. Credential cannot be saved.'))
                            box.append(label)
                        elif not self.keyring_helper.has_recommended_backend:
                            if not credentials_storage_plaintext_fallback:
                                plaintext_checkbutton = Gtk.CheckButton.new()
                                label.set_text(_('No keyring backends were found to store credential. Use plaintext storage as fallback.'))
                                plaintext_checkbutton.set_child(label)
                                box.append(plaintext_checkbutton)
                            else:
                                label.add_css_class('dim-label')
                                label.set_text(_('No keyring backends were found to store credential. Plaintext storage will be used as fallback.'))
                                box.append(label)

                    btn = Gtk.Button()
                    btn_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                    btn_hbox.set_halign(Gtk.Align.CENTER)
                    btn.icon = Gtk.Image(visible=False)
                    btn_hbox.append(btn.icon)
                    btn_hbox.append(Gtk.Label(label=_('Test')))
                    btn.connect(
                        'clicked', self.save_credential,
                        server_main_id, server_class, username_entry, password_entry, address_entry, plaintext_checkbutton
                    )
                    btn.set_child(btn_hbox)
                    box.append(btn)

                    credential = self.keyring_helper.get(server_main_id)
                    if credential:
                        if address_entry is not None:
                            address_entry.set_text(credential.address)
                        username_entry.set_text(credential.username)
                        password_entry.set_text(credential.password)
            else:
                switchrow = Adw.SwitchRow()
                switchrow.set_title(html_escape(server_data['name']))
                if server_data['is_nsfw'] or server_data['is_nsfw_only']:
                    switchrow.set_subtitle(_('18+'))
                switchrow.set_sensitive(server_allowed)
                switchrow.set_active(server_enabled and server_allowed)
                switchrow.connect('notify::active', self.on_server_activated, server_main_id)

                self.group.add(switchrow)

    def present(self, _widget):
        self.window.navigationview.push(self)

    def save_credential(self, button, server_main_id, server_class, username_entry, password_entry, address_entry, plaintext_checkbutton):
        username = username_entry.get_text()
        password = password_entry.get_text()
        if address_entry is not None:
            address = address_entry.get_text().strip()
            if not address.startswith(('http://', 'https://')):
                return

            server = server_class(username=username, password=password, address=address)
        else:
            address = None
            server = server_class(username=username, password=password)

        button.icon.set_visible(True)
        if server.logged_in:
            button.icon.set_from_icon_name('object-select-symbolic')
            if self.keyring_helper.is_disabled or plaintext_checkbutton is not None and not plaintext_checkbutton.get_active():
                return

            if plaintext_checkbutton is not None and plaintext_checkbutton.get_active():
                # Save user agrees to save credentials in plaintext
                self.parent.credentials_storage_plaintext_fallback_switch.set_active(True)

            self.keyring_helper.store(server_main_id, username, password, address)
        else:
            button.icon.set_from_icon_name('computer-fail-symbolic')
