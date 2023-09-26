# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import os
import shutil

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from komikku.models import Settings
from komikku.reader.controls import Controls
from komikku.reader.pager import Pager
from komikku.reader.pager.webtoon import WebtoonPager
from komikku.servers.utils import get_file_mime_type
from komikku.utils import is_flatpak


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/reader.ui')
class ReaderPage(Adw.NavigationPage):
    __gtype_name__ = 'ReaderPage'

    headerbar_revealer = Gtk.Template.Child('headerbar_revealer')
    back_button = Gtk.Template.Child('back_button')
    title = Gtk.Template.Child('title')
    fullscreen_button = Gtk.Template.Child('fullscreen_button')
    menu_button = Gtk.Template.Child('menu_button')

    overlay = Gtk.Template.Child('reader_overlay')

    manga = None
    init_chapter = None
    chapters_consulted = None
    pager = None

    def __init__(self, window):
        Adw.NavigationPage.__init__(self)

        self.window = window
        self.builder = window.builder
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/reader.xml')

        self.connect('hidden', self.on_hidden)
        self.connect('shown', self.on_shown)
        self.window.connect('notify::fullscreened', self.on_fullscreen_state_changed)
        self.window.controller_key.connect('key-pressed', self.on_key_pressed)

        # Double maximum distance allowed between two clicks (default 5)
        # Allows to zoom more easily (double tap) on touch screen
        Gtk.Settings.get_default().set_property('gtk-double-click-distance', 10)

        # Header bar
        self.back_button.connect('clicked', self.on_back_button_clicked)
        self.fullscreen_button.connect('clicked', self.window.toggle_fullscreen, None)
        self.menu_button.set_menu_model(self.builder.get_object('menu-reader'))
        # Focus is lost after showing popover submenu (bug?)
        self.menu_button.get_popover().connect('closed', lambda _popover: self.menu_button.grab_focus())

        # Page numbering
        self.page_numbering_defined = False
        self.page_numbering_label = Gtk.Label(halign=Gtk.Align.CENTER, can_focus=False, can_target=False)
        self.page_numbering_label.add_css_class('reader-page-number-indicator-label')
        self.page_numbering_label.set_valign(Gtk.Align.END)
        self.overlay.add_overlay(self.page_numbering_label)

        # Controls
        self.controls = Controls(self)

        self.window.navigationview.add(self)

    @property
    def background_color(self):
        return self.manga.background_color or Settings.get_default().background_color

    @property
    def borders_crop(self):
        if self.reading_mode == 'webtoon':
            # Borders crop is not an option in Webtoon reading mode
            # Ignore settings and return False
            return False

        if self.manga.borders_crop in (0, 1):
            return bool(self.manga.borders_crop)

        return Settings.get_default().borders_crop

    @property
    def landscape_zoom(self):
        if self.reading_mode == 'webtoon':
            # Landscape zoom is not an option in Webtoon reading mode
            # Ignore settings and return False
            return False

        if self.manga.landscape_zoom in (0, 1):
            return bool(self.manga.landscape_zoom)

        return Settings.get_default().landscape_zoom

    @property
    def page_numbering(self):
        if self.manga.page_numbering in (0, 1):
            return bool(self.manga.page_numbering)

        return Settings.get_default().page_numbering

    @property
    def reading_mode(self):
        return self.manga.reading_mode or Settings.get_default().reading_mode

    @property
    def scaling(self):
        if self.reading_mode == 'webtoon':
            # Scaling is not an option in Webtoon reading mode
            # Ignore settings and return 'width'
            return 'width'

        return self.manga.scaling or Settings.get_default().scaling

    @property
    def size(self):
        size = self.window.get_allocation()

        if self.headerbar_revealer.get_child_revealed():
            size.height -= self.get_child().get_top_bar_height()

        return size

    def add_accelerators(self):
        self.window.application.set_accels_for_action('app.reader.save-page', ['<Primary>s'])

    def add_actions(self):
        # Reading mode
        variant = GLib.Variant.new_string('right-to-left')
        self.reading_mode_action = Gio.SimpleAction.new_stateful('reader.reading-mode', variant.get_type(), variant)
        self.reading_mode_action.connect('activate', self.on_reading_mode_changed)
        self.window.application.add_action(self.reading_mode_action)

        # Scaling
        variant = GLib.Variant.new_string('screen')
        self.scaling_action = Gio.SimpleAction.new_stateful('reader.scaling', variant.get_type(), variant)
        self.scaling_action.connect('activate', self.on_scaling_changed)
        self.window.application.add_action(self.scaling_action)

        # Landscape Pages Zoom
        self.landscape_zoom_action = Gio.SimpleAction.new_stateful('reader.landscape-zoom', None, GLib.Variant('b', False))
        self.landscape_zoom_action.connect('change-state', self.on_landscape_zoom_changed)
        self.window.application.add_action(self.landscape_zoom_action)

        # Background color
        variant = GLib.Variant.new_string('white')
        self.background_color_action = Gio.SimpleAction.new_stateful('reader.background-color', variant.get_type(), variant)
        self.background_color_action.connect('activate', self.on_background_color_changed)
        self.window.application.add_action(self.background_color_action)

        # Borders crop
        self.borders_crop_action = Gio.SimpleAction.new_stateful('reader.borders-crop', None, GLib.Variant('b', False))
        self.borders_crop_action.connect('change-state', self.on_borders_crop_changed)
        self.window.application.add_action(self.borders_crop_action)

        # Page numbering
        self.page_numbering_action = Gio.SimpleAction.new_stateful('reader.page-numbering', None, GLib.Variant('b', False))
        self.page_numbering_action.connect('change-state', self.on_page_numbering_changed)
        self.window.application.add_action(self.page_numbering_action)

        # Save page
        self.save_page_action = Gio.SimpleAction.new('reader.save-page', None)
        self.save_page_action.connect('activate', self.save_page)
        self.window.application.add_action(self.save_page_action)

    def init(self, manga, chapter):
        self.manga = manga
        self.init_chapter = chapter

        # Reset list of chapters consulted
        self.chapters_consulted = set()

        # Init settings
        self.set_action_reading_mode()
        self.set_action_scaling()
        self.set_action_landscape_zoom()
        self.set_action_borders_crop()
        self.set_action_page_numbering()

        if Settings.get_default().fullscreen:
            self.window.fullscreen()

        self.back_button.set_tooltip_text(self.manga.name)

        self.show()

    def init_pager(self, chapter):
        if self.pager:
            self.pager.dispose()

        if self.reading_mode == 'webtoon':
            self.pager = WebtoonPager(self)
        else:
            self.pager = Pager(self)
            self.set_orientation()

        self.set_action_background_color()

        self.overlay.set_child(self.pager)

        self.pager.init(chapter)

    def on_back_button_clicked(self, _btn):
        self.window.navigationview.pop()

    def on_background_color_changed(self, _action, variant):
        value = variant.get_string()
        if value == self.background_color:
            return

        self.manga.update(dict(background_color=value))
        self.set_action_background_color()

    def on_borders_crop_changed(self, _action, variant):
        self.manga.update(dict(borders_crop=variant.get_boolean()))
        self.set_action_borders_crop()
        self.pager.crop_pages_borders()

    def on_fullscreen_state_changed(self, _window, gparam):
        if self.window.is_fullscreen():
            self.headerbar_revealer.set_reveal_child(False)
            self.fullscreen_button.set_icon_name('view-restore-symbolic')
        else:
            self.headerbar_revealer.set_reveal_child(True)
            self.fullscreen_button.set_icon_name('view-fullscreen-symbolic')

    def on_hidden(self, _page):
        if self.pager:
            self.pager.dispose()
            self.pager = None

        self.controls.hide()
        self.page_numbering_label.set_visible(False)
        self.window.unfullscreen()

        # Sync Card page
        if self.window.card in self.window.navigationview.get_navigation_stack():
            if self.chapters_consulted:
                # Refresh to update all previously chapters consulted (last page read may have changed also)
                # and update info like disk usage
                self.window.card.refresh(self.chapters_consulted)

        # Sync History page
        if self.window.history in self.window.navigationview.get_navigation_stack():
            self.window.history.populate()

        # Sync Library page (root)
        if self.manga.in_library:
            self.window.library.update_thumbnail(self.manga)
            self.window.library.flowbox.invalidate_sort()

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != self.props.tag:
            return Gdk.EVENT_PROPAGATE

        # Allow to navigate back with <Esc> key and <Alt+Left>
        modifiers = state & Gtk.accelerator_get_default_mod_mask()
        if keyval == Gdk.KEY_Escape or (modifiers == Gdk.ModifierType.ALT_MASK and keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left)):
            self.window.navigationview.pop()
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_landscape_zoom_changed(self, _action, variant):
        value = variant.get_boolean()
        self.manga.update(dict(landscape_zoom=value))
        self.set_action_landscape_zoom()

        self.pager.rescale_pages()

    def on_page_numbering_changed(self, _action, variant):
        value = not variant.get_boolean()
        self.manga.update(dict(page_numbering=value))
        self.set_action_page_numbering()
        if value and self.page_numbering_defined and not self.controls.is_visible:
            self.page_numbering_label.set_visible(True)
        else:
            self.page_numbering_label.set_visible(False)

    def on_reading_mode_changed(self, _action, variant):
        value = variant.get_string()
        if value == self.reading_mode:
            return

        prior_reading_mode = self.reading_mode

        self.manga.update(dict(reading_mode=value))
        self.set_action_reading_mode()

        if value == 'webtoon' or prior_reading_mode == 'webtoon':
            self.init_pager(self.pager.current_page.chapter)
        else:
            if value == 'right-to-left' or prior_reading_mode == 'right-to-left':
                self.pager.reverse_pages()
            self.set_orientation()

    def on_scaling_changed(self, _action, variant):
        value = variant.get_string()
        if value == self.scaling:
            return

        self.manga.update(dict(scaling=value))
        self.set_action_scaling()

        self.pager.rescale_pages()

    def on_shown(self, _page):
        # Wait page is shown (transition is ended) to init pager
        # Operation is resource intensive and could disrupt page transition
        self.init_pager(self.init_chapter)

    def save_page(self, _action, _gparam):
        if self.window.page != self.props.tag:
            return

        page = self.pager.current_page
        if not page.picture or page.error:
            return

        def do_save(dest_path):
            shutil.copy(page.path, dest_path)
            self.window.show_notification(_('Page successfully saved to {0}').format(dest_path.replace(os.path.expanduser('~'), '~')))

        def on_ready(dialog, result):
            try:
                gfile = dialog.save_finish(result)
            except GLib.GError:
                # Cancel
                gfile = None

            if gfile:
                do_save(gfile.get_path())

        extension = get_file_mime_type(page.path).split('/')[-1]
        filename = f'{self.manga.name}_{page.chapter.title}_{str(page.index + 1)}.{extension}'
        xdg_pictures_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)

        if not is_flatpak():
            dialog = Gtk.FileDialog(modal=True)
            dialog.set_initial_name(filename)
            if xdg_pictures_dir is not None:
                dialog.set_initial_folder(Gio.File.new_for_path(xdg_pictures_dir))

            dialog.save(self.window, None, on_ready)
        else:
            if xdg_pictures_dir is not None:
                do_save(os.path.join(xdg_pictures_dir, filename))
            else:
                self.window.show_notification(_('Failed to save page: missing permission to access the XDG pictures directory'))

    def set_action_background_color(self):
        self.background_color_action.set_state(GLib.Variant('s', self.background_color))

        if self.background_color == 'white':
            self.pager.set_css_classes(['background-white'])
        elif self.background_color == 'gray':
            self.pager.set_css_classes(['background-gray'])
        elif self.background_color == 'black':
            self.pager.set_css_classes(['background-black'])
        else:
            # System style
            self.pager.set_css_classes([])

    def set_action_borders_crop(self):
        self.borders_crop_action.set_state(GLib.Variant('b', self.borders_crop))

    def set_action_landscape_zoom(self):
        self.landscape_zoom_action.set_state(GLib.Variant('b', self.landscape_zoom))

    def set_action_page_numbering(self):
        self.page_numbering_action.set_state(GLib.Variant('b', not self.page_numbering))

    def set_action_reading_mode(self):
        self.reading_mode_action.set_state(GLib.Variant('s', self.reading_mode))

        # Scaling action is enabled in RTL/LTR/Vertical reading modes only
        self.scaling_action.set_enabled(self.reading_mode != 'webtoon')
        # Landscape pages zoom is enabled in RTL/LTR/Vertical reading modes only and when scaling is 'screen'
        self.landscape_zoom_action.set_enabled(self.reading_mode != 'webtoon' and self.scaling == 'screen')
        # Borders crop is enabled in RTL/LTR/Vertical reading mode only
        self.borders_crop_action.set_enabled(self.reading_mode != 'webtoon')

        # Additionally, direction of page slider in controls must be updated
        self.controls.set_scale_direction(inverted=self.reading_mode == 'right-to-left')

    def set_action_scaling(self, scaling=None):
        self.scaling_action.set_state(GLib.Variant('s', scaling or self.scaling))

        # Landscape pages zoom is enabled in RTL/LTR/Vertical reading modes only and when scaling is 'screen'
        self.landscape_zoom_action.set_enabled(self.reading_mode != 'webtoon' and self.scaling == 'screen')

    def set_orientation(self):
        if self.reading_mode in ('right-to-left', 'left-to-right'):
            orientation = Gtk.Orientation.HORIZONTAL
        else:
            orientation = Gtk.Orientation.VERTICAL

        self.pager.set_orientation(orientation)

    def show(self):
        self.window.navigationview.push(self)

    def toggle_controls(self, visible=None):
        if visible is None:
            visible = not self.controls.is_visible

        if visible:
            self.controls.show()
            self.page_numbering_label.set_visible(False)
        else:
            self.controls.hide()
            if self.page_numbering and self.page_numbering_defined:
                self.page_numbering_label.set_visible(True)

    def update_page_numbering(self, number=None, total=None):
        if number and total:
            self.page_numbering_label.set_text('{0}/{1}'.format(number, total))
            self.page_numbering_defined = True

            if self.page_numbering and not self.controls.is_visible:
                self.page_numbering_label.set_visible(True)
            else:
                self.page_numbering_label.set_visible(False)
        else:
            self.page_numbering_defined = False
            self.page_numbering_label.set_visible(False)

    def update_title(self, chapter):
        # Set title & subtitle (headerbar)
        self.title.set_title(chapter.manga.name)
        subtitle = chapter.title
        if chapter.manga.name in subtitle:
            subtitle = subtitle.replace(chapter.manga.name, '').strip()
        self.title.set_subtitle(subtitle)
