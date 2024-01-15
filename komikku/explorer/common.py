# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import Pango

from komikku.models import Settings
from komikku.servers import LANGUAGES
from komikku.utils import COVER_WIDTH
from komikku.utils import html_escape
from komikku.utils import PaintableCover

DOWNLOAD_MAX_DELAY = 1  # in seconds
LOGO_SIZE = 28
THUMB_WIDTH = 45
THUMB_HEIGHT = 62


class ExplorerSearchStackPage:
    def __init__(self, parent):
        self.parent = parent
        self.window = self.parent.window

    def clear(self):
        self.listbox.set_visible(False)

        row = self.listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            if isinstance(row, (ExplorerServerRow, ExplorerSearchResultRow)):
                row.dispose()
            row = next_row

        self.listbox.remove_all()


class ExplorerSearchResultRow(Adw.ActionRow):
    __gtype_name__ = 'ExplorerSearchResultRow'

    def __init__(self, data):
        Adw.ActionRow.__init__(self, activatable=True, selectable=False)

        self.has_cover = 'cover' in data
        self.is_result = True
        self.manga_data = data
        self.cover_data = None

        self.set_title(html_escape(data['name']))
        self.set_title_lines(1)

        # Use subtitle to display additional info
        subtitle = []
        if nb_chapters := data.get('nb_chapters'):
            subtitle.append(ngettext('{0} chapter', '{0} chapters', nb_chapters).format(nb_chapters))
        if last_chapter := data.get('last_chapter'):
            subtitle.append(_('Last Chapter: {}').format(last_chapter))
        if last_volume := data.get('last_volume'):
            subtitle.append(_('Last Volume: {}').format(last_volume))

        if subtitle:
            self.set_subtitle(html_escape(' · '.join(subtitle)))
            self.set_subtitle_lines(1)

        if self.has_cover:
            self.cover = Gtk.Frame()
            self.cover.set_size_request(THUMB_WIDTH, THUMB_HEIGHT)
            self.cover.add_css_class('row-rounded-cover-frame')
            self.add_prefix(self.cover)

            self.popover = Gtk.Popover()
            self.popover.set_position(Gtk.PositionType.RIGHT)
            self.popover.set_parent(self.cover)

            self.gesture_click = Gtk.GestureClick.new()
            self.gesture_click.set_button(0)
            self.gesture_click.connect('released', self.on_cover_clicked)
            self.cover.add_controller(self.gesture_click)

    def dispose(self):
        self.cover_data = None
        self.manga_data = None

        if self.has_cover:
            if self.cover.get_child():
                self.cover.get_child().set_paintable(None)
            self.cover.remove_controller(self.gesture_click)

            if self.popover.get_child():
                self.popover.get_child().set_paintable(None)
            self.popover.unparent()

    def on_cover_clicked(self, _gesture, _n_press, _x, _y):
        self.gesture_click.set_state(Gtk.EventSequenceState.CLAIMED)

        if self.cover_data is None:
            return

        if not self.popover.get_child():
            picture = Gtk.Picture.new_for_paintable(PaintableCover.new_from_data(self.cover_data, COVER_WIDTH))
            picture.add_css_class('cover-dropshadow')

            self.popover.set_child(picture)
            # Avoid vertical padding in popover content
            self.popover.get_first_child().props.valign = Gtk.Align.CENTER

        self.popover.popup()

    def set_cover(self, data):
        if not self.has_cover:
            return

        paintable = PaintableCover.new_from_data(data, THUMB_WIDTH, THUMB_HEIGHT, True) if data else None
        if paintable is None:
            paintable = PaintableCover.new_from_resource(
                '/info/febvre/Komikku/images/missing_file.png', THUMB_WIDTH, THUMB_HEIGHT)
        else:
            self.cover_data = data

        self.cover.set_child(Gtk.Picture.new_for_paintable(paintable))


class ExplorerServerRow(Gtk.ListBoxRow):
    __gtype_name__ = 'ExplorerServerRow'

    def __init__(self, data, page):
        Gtk.ListBoxRow.__init__(self)

        self.page = page

        self.pin_button_toggled_handler_id = None
        self.local_folder_button_clicked_handler_id = None

        # Used in `explorer.servers` and `explorer.search` (global search) pages
        if page.props.tag == 'explorer.search':
            self.props.activatable = False
            self.add_css_class('explorer-section-listboxrow')
        else:
            self.props.activatable = True
            self.add_css_class('explorer-listboxrow')

        self.server_data = data
        if 'manga_initial_data' in data:
            self.manga_data = data.pop('manga_initial_data')

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_child(box)

        # Server logo
        logo_image = Gtk.Image()
        if page.props.tag == 'explorer.search':
            # Align logos horizontally with covers
            logo_image.set_margin_start(3)
            logo_image.set_margin_end(3)
        logo_image.set_size_request(LOGO_SIZE, LOGO_SIZE)
        if data['id'] != 'local':
            if data['logo_path']:
                logo_image.set_from_file(data['logo_path'])
        else:
            logo_image.set_from_icon_name('folder-symbolic')
        box.append(logo_image)

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

        if page.props.tag == 'explorer.search':
            return

        # Server requires a user account
        if data['has_login']:
            login_image = Gtk.Image.new_from_icon_name('dialog-password-symbolic')
            box.append(login_image)

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
            self.local_folder_button = Gtk.Button(valign=Gtk.Align.CENTER)
            self.local_folder_button.set_icon_name('folder-visiting-symbolic')
            self.local_folder_button.set_tooltip_text(_('Open local folder'))
            self.local_folder_button_clicked_handler_id = self.local_folder_button.connect(
                'clicked', self.page.open_local_folder)
            box.append(self.local_folder_button)

        # Button to pin/unpin
        self.pin_button = Gtk.ToggleButton(valign=Gtk.Align.CENTER)
        self.pin_button.set_icon_name('view-pin-symbolic')
        self.pin_button.set_tooltip_text(_('Toggle pinned status'))
        self.pin_button.set_active(data['id'] in Settings.get_default().pinned_servers)
        self.pin_button_toggled_handler_id = self.pin_button.connect(
            'toggled', self.page.toggle_server_pinned_state, self)
        box.append(self.pin_button)

    def dispose(self):
        if self.local_folder_button_clicked_handler_id:
            self.local_folder_button.disconnect(self.local_folder_button_clicked_handler_id)
        if self.pin_button_toggled_handler_id:
            self.pin_button.disconnect(self.pin_button_toggled_handler_id)


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
