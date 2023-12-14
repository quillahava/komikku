# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw
from gi.repository import Gtk

from komikku.utils import create_paintable_from_data
from komikku.utils import create_paintable_from_resource
from komikku.utils import html_escape

DOWNLOAD_MAX_DELAY = 1  # in seconds
THUMB_WIDTH = 45
THUMB_HEIGHT = 62


class ExplorerSearchStackPage:
    def __init__(self, parent):
        self.parent = parent
        self.window = self.parent.window

    def clear(self):
        self.listbox.set_visible(False)

        child = self.listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.listbox.remove(child)
            child = next_child


class ExplorerSearchResultRow(Gtk.ListBoxRow):
    __gtype_name__ = 'ExplorerSearchResultRow'

    def __init__(self, data):
        Gtk.ListBoxRow.__init__(self)

        self.has_cover = 'cover' in data
        self.is_result = True
        self.manga_data = data

        action_row = Adw.ActionRow(activatable=True, selectable=False)
        self.set_child(action_row)

        action_row.set_title(html_escape(data['name']))
        action_row.set_title_lines(1)

        # Use subtitle to display additional info
        subtitle = []
        if nb_chapters := data.get('nb_chapters'):
            subtitle.append(ngettext('{0} chapter', '{0} chapters', nb_chapters).format(nb_chapters))
        if last_chapter := data.get('last_chapter'):
            subtitle.append(_('Last Chapter: {}').format(last_chapter))
        if last_volume := data.get('last_volume'):
            subtitle.append(_('Last Volume: {}').format(last_volume))

        if subtitle:
            action_row.set_subtitle(' · '.join(subtitle))
            action_row.set_subtitle_lines(1)

        if self.has_cover:
            self.cover = Gtk.Frame()
            self.cover.set_size_request(THUMB_WIDTH, THUMB_HEIGHT)
            self.cover.add_css_class('row-rounded-cover-frame')
            action_row.add_prefix(self.cover)

    def set_cover(self, data):
        if not self.has_cover:
            return

        if data is None:
            paintable = create_paintable_from_resource(
                '/info/febvre/Komikku/images/missing_file.png', THUMB_WIDTH, THUMB_HEIGHT, False)
        else:
            paintable = create_paintable_from_data(data, THUMB_WIDTH, THUMB_HEIGHT, True, False)
            if paintable is None:
                paintable = create_paintable_from_resource(
                    '/info/febvre/Komikku/images/missing_file.png', THUMB_WIDTH, THUMB_HEIGHT, False)

        self.cover.set_child(Gtk.Picture.new_for_paintable(paintable))


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
