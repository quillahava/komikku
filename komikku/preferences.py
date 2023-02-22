# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Adw
from gi.repository import Gtk

from komikku.models import Settings
from komikku.models.keyring import KeyringHelper
from komikku.servers import LANGUAGES
from komikku.servers.utils import get_server_main_id_by_id
from komikku.servers.utils import get_servers_list
from komikku.utils import html_escape


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/preferences.ui')
class Preferences(Adw.Bin):
    __gtype_name__ = 'Preferences'

    window = NotImplemented
    settings = NotImplemented

    leaflet = Gtk.Template.Child('leaflet')
    pages_stack = Gtk.Template.Child('pages_stack')
    subpages_stack = Gtk.Template.Child('subpages_stack')
    viewswitcherbar = Gtk.Template.Child('viewswitcherbar')

    theme_switch = Gtk.Template.Child('theme_switch')
    night_light_switch = Gtk.Template.Child('night_light_switch')
    desktop_notifications_switch = Gtk.Template.Child('desktop_notifications_switch')

    library_display_mode_row = Gtk.Template.Child('library_display_mode_row')
    library_servers_logo_switch = Gtk.Template.Child('library_servers_logo_switch')
    library_badge_unread_chapters_switch = Gtk.Template.Child('library_badge_unread_chapters_switch')
    library_badge_downloaded_chapters_switch = Gtk.Template.Child('library_badge_downloaded_chapters_switch')
    library_badge_recent_chapters_switch = Gtk.Template.Child('library_badge_recent_chapters_switch')
    update_at_startup_switch = Gtk.Template.Child('update_at_startup_switch')
    new_chapters_auto_download_switch = Gtk.Template.Child('new_chapters_auto_download_switch')
    nsfw_content_switch = Gtk.Template.Child('nsfw_content_switch')
    servers_languages_actionrow = Gtk.Template.Child('servers_languages_actionrow')
    servers_languages_subpage_group = Gtk.Template.Child('servers_languages_subpage_group')
    servers_settings_actionrow = Gtk.Template.Child('servers_settings_actionrow')
    servers_settings_subpage_group = Gtk.Template.Child('servers_settings_subpage_group')
    long_strip_detection_switch = Gtk.Template.Child('long_strip_detection_switch')

    reading_mode_row = Gtk.Template.Child('reading_mode_row')
    clamp_size_adjustment = Gtk.Template.Child('clamp_size_adjustment')
    scaling_row = Gtk.Template.Child('scaling_row')
    landscape_zoom_switch = Gtk.Template.Child('landscape_zoom_switch')
    background_color_row = Gtk.Template.Child('background_color_row')
    borders_crop_switch = Gtk.Template.Child('borders_crop_switch')
    page_numbering_switch = Gtk.Template.Child('page_numbering_switch')
    fullscreen_switch = Gtk.Template.Child('fullscreen_switch')

    credentials_storage_plaintext_fallback_switch = Gtk.Template.Child('credentials_storage_plaintext_fallback_switch')
    disable_animations_switch = Gtk.Template.Child('disable_animations_switch')

    def __init__(self, window):
        super().__init__()

        self.window = window

        # Add Adw.ViewSwitcherTitle in Adw.HeaderBar => Gtk.Stack 'preferences' page
        self.viewswitchertitle = Adw.ViewSwitcherTitle(title=_('Preferences'))
        self.viewswitchertitle.set_stack(self.pages_stack)
        self.viewswitchertitle.connect('notify::title-visible', self.on_viewswitchertitle_title_visible)
        self.window.title_stack.get_child_by_name('preferences').set_child(self.viewswitchertitle)
        self.viewswitcherbar.set_reveal(self.viewswitchertitle.get_title_visible())

        self.settings = Settings.get_default()

        self.set_config_values()

        self.window.stack.add_named(self, 'preferences')
        self.leaflet.connect('notify::visible-child', self.on_page_changed)

    def navigate_back(self, _source):
        if self.leaflet.get_visible_child_name() == 'subpages':
            self.leaflet.navigate(Adw.NavigationDirection.BACK)
        else:
            getattr(self.window, self.window.previous_page).show(reset=False)

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

    def on_clamp_size_changed(self, adjustment):
        self.settings.clamp_size = int(adjustment.get_value())

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

        self.window.library.populate()

    def on_library_display_mode_changed(self, row, _gparam):
        index = row.get_selected()

        if index == 0:
            self.settings.library_display_mode = 'grid'
        elif index == 1:
            self.settings.library_display_mode = 'grid-compact'

        self.window.library.populate()

    def on_library_servers_logo_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.library_servers_logo = True
        else:
            self.settings.library_servers_logo = False

        self.window.library.populate()

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

    def on_page_changed(self, _deck, _child):
        if self.leaflet.get_visible_child_name() != 'subpages':
            self.viewswitchertitle.set_subtitle('')
            self.viewswitchertitle.set_view_switcher_enabled(True)
        else:
            self.viewswitchertitle.set_view_switcher_enabled(False)

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

    def on_theme_changed(self, switch_button, _gparam):
        self.settings.dark_theme = switch_button.get_active()

        self.window.init_theme()

    def on_update_at_startup_changed(self, switch_button, _gparam):
        if switch_button.get_active():
            self.settings.update_at_startup = True
        else:
            self.settings.update_at_startup = False

    def on_viewswitchertitle_title_visible(self, _viewswitchertitle, _param):
        self.viewswitcherbar.set_reveal(self.viewswitchertitle.get_title_visible())

    def set_config_values(self):
        #
        # General
        #

        # Dark theme
        self.theme_switch.set_active(self.settings.dark_theme)
        self.theme_switch.connect('notify::active', self.on_theme_changed)

        # Night light
        self.night_light_switch.set_active(self.settings.night_light)
        self.night_light_switch.connect('notify::active', self.on_night_light_changed)

        # Desktop notifications
        self.desktop_notifications_switch.set_active(self.settings.desktop_notifications)
        self.desktop_notifications_switch.connect('notify::active', self.on_desktop_notifications_changed)

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
        self.servers_languages_subpage = PreferencesServersLanguagesSubpage(self)
        self.servers_languages_actionrow.props.activatable = True
        self.servers_languages_actionrow.connect('activated', self.servers_languages_subpage.present)

        # Servers settings
        self.servers_settings_subpage = PreferencesServersSettingsSubpage(self)
        self.servers_settings_actionrow.props.activatable = True
        self.servers_settings_actionrow.connect('activated', self.servers_settings_subpage.present)

        # Long strip detection
        self.long_strip_detection_switch.set_active(self.settings.long_strip_detection)
        self.long_strip_detection_switch.connect('notify::active', self.on_long_strip_detection_changed)

        # NSFW content
        self.nsfw_content_switch.set_active(self.settings.nsfw_content)
        self.nsfw_content_switch.connect('notify::active', self.on_nsfw_content_changed)

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
        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.left_extra_button_stack.hide()

        self.window.right_button_stack.hide()

        self.window.menu_button.hide()

        # Update maximum value of clamp size adjustment
        self.clamp_size_adjustment.set_upper(self.window.monitor.props.geometry.width)

        self.pages_stack.set_visible_child_name('general')
        self.window.show_page('preferences', transition=transition)


class PreferencesServersLanguagesSubpage:
    parent = NotImplemented
    settings = NotImplemented

    def __init__(self, parent):
        self.parent = parent
        self.settings = Settings.get_default()

        servers_languages = self.settings.servers_languages

        for code, language in LANGUAGES.items():
            action_row = Adw.ActionRow()
            action_row.set_title(language)
            action_row.set_activatable(True)

            switch = Gtk.Switch.new()
            switch.set_valign(Gtk.Align.CENTER)
            switch.set_halign(Gtk.Align.CENTER)
            switch.set_active(code in servers_languages)
            switch.connect('notify::active', self.on_language_activated, code)
            action_row.add_suffix(switch)
            action_row.set_activatable_widget(switch)

            self.parent.servers_languages_subpage_group.add(action_row)

    def on_language_activated(self, switch_button, _gparam, code):
        if switch_button.get_active():
            self.settings.add_servers_language(code)
        else:
            self.settings.remove_servers_language(code)

        # Update Servers settings subpage
        self.parent.servers_settings_subpage.populate()

    def present(self, _widget):
        self.parent.viewswitchertitle.set_subtitle(_('Servers Languages'))
        self.parent.subpages_stack.set_visible_child_name('servers_languages')
        self.parent.leaflet.set_visible_child_name('subpages')


class PreferencesServersSettingsSubpage:
    parent = NotImplemented
    settings = NotImplemented

    def __init__(self, parent):
        self.parent = parent
        self.settings = Settings.get_default()
        self.keyring_helper = KeyringHelper()

        self.populate()

    def on_server_activated(self, widget, _gparam, server_main_id):
        if isinstance(widget, Adw.ExpanderRow):
            self.settings.toggle_server(server_main_id, widget.get_enable_expansion())
        else:
            self.settings.toggle_server(server_main_id, widget.get_active())

    def on_server_language_activated(self, switch_button, _gparam, server_main_id, lang):
        self.settings.toggle_server_lang(server_main_id, lang, switch_button.get_active())

    def populate(self):
        settings = self.settings.servers_settings
        languages = self.settings.servers_languages
        credentials_storage_plaintext_fallback = self.settings.credentials_storage_plaintext_fallback

        # Clear
        child = self.parent.servers_settings_subpage_group.get_first_child().get_last_child().get_first_child().get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.parent.servers_settings_subpage_group.remove(child)
            child = next_child

        servers_data = {}
        for server_data in get_servers_list(order_by=('name', 'lang')):
            main_id = get_server_main_id_by_id(server_data['id'])

            if main_id not in servers_data:
                servers_data[main_id] = dict(
                    main_id=main_id,
                    name=server_data['name'],
                    module=server_data['module'],
                    is_nsfw=server_data['is_nsfw'],
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
            server_enabled = server_settings is None or server_settings['enabled'] is True
            server_has_login = getattr(server_class, 'has_login')

            if len(server_data['langs']) > 1 or server_has_login:
                vbox = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL,
                    margin_start=12, margin_top=6, margin_end=12, margin_bottom=6,
                    spacing=12
                )

                expander_row = Adw.ExpanderRow()
                expander_row.set_title(html_escape(server_data['name']))
                if server_data['is_nsfw']:
                    expander_row.set_subtitle(_('18+'))
                expander_row.set_enable_expansion(server_enabled)
                expander_row.set_sensitive(server_allowed)
                expander_row.connect('notify::enable-expansion', self.on_server_activated, server_main_id)
                expander_row.add_row(vbox)

                self.parent.servers_settings_subpage_group.add(expander_row)

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

                if server_has_login:
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
                        label = Gtk.Label()
                        label.set_wrap(True)
                        if self.keyring_helper.is_disabled:
                            label.add_css_class('dim-label')
                            label.set_text(_('System keyring service is disabled. Credential cannot be saved.'))
                            box.append(label)
                        elif not self.keyring_helper.has_recommended_backend:
                            if not credentials_storage_plaintext_fallback:
                                plaintext_checkbutton = Gtk.CheckButton.new()
                                label.set_text(_('No keyring backends were found to store credential. Use plaintext storage as fallback.'))
                                plaintext_checkbutton.add(label)
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
                action_row = Adw.ActionRow()
                action_row.set_title(html_escape(server_data['name']))
                if server_data['is_nsfw']:
                    action_row.set_subtitle(_('18+'))
                action_row.set_sensitive(server_allowed)

                switch = Gtk.Switch.new()
                switch.set_active(server_enabled and server_allowed)
                switch.set_valign(Gtk.Align.CENTER)
                switch.set_halign(Gtk.Align.CENTER)
                switch.connect('notify::active', self.on_server_activated, server_main_id)
                action_row.set_activatable_widget(switch)
                action_row.add_suffix(switch)

                self.parent.servers_settings_subpage_group.add(action_row)

    def present(self, _widget):
        self.parent.viewswitchertitle.set_subtitle(_('Servers Settings'))
        self.parent.subpages_stack.set_visible_child_name('servers_settings')
        self.parent.leaflet.set_visible_child_name('subpages')

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

        button.icon.show()
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
