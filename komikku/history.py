# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import datetime
from gettext import gettext as _
import pytz

from gi.repository import Adw
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from komikku.models import Chapter
from komikku.models import create_db_connection
from komikku.utils import html_escape
from komikku.utils import PaintableCover

THUMB_WIDTH = 45
THUMB_HEIGHT = 62
DAYS_LIMIT = 30


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/history.ui')
class HistoryPage(Adw.NavigationPage):
    __gtype_name__ = 'HistoryPage'

    search_button = Gtk.Template.Child('search_button')

    stack = Gtk.Template.Child('stack')
    dates_box = Gtk.Template.Child('dates_box')
    searchbar = Gtk.Template.Child('searchbar')
    searchbar_separator = Gtk.Template.Child('searchbar_separator')
    searchentry = Gtk.Template.Child('searchentry')

    def __init__(self, window):
        Adw.NavigationPage.__init__(self)

        self.window = window

        self.connect('hidden', self.on_hidden)

        self.searchbar.bind_property(
            'search-mode-enabled', self.search_button, 'active',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.searchbar.bind_property(
            'search-mode-enabled', self.searchbar_separator, 'visible',
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
        )
        self.searchbar.connect_entry(self.searchentry)
        self.searchbar.set_key_capture_widget(self.window)

        self.searchentry.connect('activate', self.on_searchentry_activated)
        self.searchentry.connect('search-changed', self.search)

        self.window.navigationview.add(self)

    def filter(self, row):
        """
        This function gets one row and has to return:
        - True if the row should be displayed
        - False if the row should not be displayed
        """
        term = self.searchentry.get_text().strip().lower()

        ret = (
            term in row.chapter.title.lower() or
            term in row.chapter.manga.name.lower()
        )

        if ret:
            # As soon as a row is visible, made grand parent date_box visible
            GLib.idle_add(row.get_parent().get_parent().set_visible, True)

        return ret

    def on_hidden(self, _page):
        # Leave search mode
        if self.searchbar.get_search_mode():
            self.searchbar.set_search_mode(False)

    def on_searchentry_activated(self, _entry):
        if not self.searchbar.get_search_mode():
            return

        row = self.dates_box.get_first_child().get_last_child().get_row_at_y(0)
        if row:
            self.window.reader.init(row.chapter.manga, row.chapter)

    def populate(self):
        box = self.dates_box.get_first_child()
        while box:
            next_box = box.get_next_sibling()
            self.dates_box.remove(box)
            box = next_box

        db_conn = create_db_connection()
        start = (datetime.date.today() - datetime.timedelta(days=DAYS_LIMIT)).strftime('%Y-%m-%d')
        records = db_conn.execute('SELECT * FROM chapters WHERE last_read >= ? ORDER BY last_read DESC', (start,)).fetchall()
        db_conn.close()

        if records:
            local_timezone = datetime.datetime.utcnow().astimezone().tzinfo
            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)

            current_date = None
            current_manga_id = None
            for record in records:
                chapter = Chapter.get(record['id'])
                # Convert chapter's last read date in local timezone
                last_read = chapter.last_read.replace(tzinfo=pytz.UTC).astimezone(local_timezone)
                date_changed = current_date is None or current_date != last_read.date()

                if not date_changed and current_manga_id and chapter.manga.id == current_manga_id:
                    continue

                current_manga_id = chapter.manga.id

                # Create new Box (Label + ListBox) when date change
                if date_changed:
                    current_date = last_read.date()
                    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

                    if current_date == today:
                        label = _('Today')
                    elif current_date == yesterday:
                        label = _('Yesterday')
                    else:
                        g_datetime = GLib.DateTime.new_from_iso8601(last_read.isoformat())
                        label = g_datetime.format(_('%A, %B %e'))
                    date_label = Gtk.Label(label=label, xalign=0)
                    date_label.add_css_class('heading')
                    box.append(date_label)

                    listbox = Gtk.ListBox()
                    listbox.add_css_class('boxed-list')
                    listbox.set_filter_func(self.filter)
                    box.append(listbox)

                    self.dates_box.append(box)

                action_row = Adw.ActionRow(activatable=True, selectable=False)
                action_row.connect('activated', self.on_row_activated)
                action_row.chapter = chapter

                action_row.set_title(html_escape(chapter.manga.name))
                action_row.set_title_lines(1)
                action_row.set_subtitle(chapter.title)
                action_row.set_subtitle_lines(1)

                # Cover
                if chapter.manga.cover_fs_path is None:
                    paintable = PaintableCover.new_from_resource(
                        '/info/febvre/Komikku/images/missing_file.png', THUMB_WIDTH, THUMB_HEIGHT)
                else:
                    paintable = PaintableCover.new_from_file(chapter.manga.cover_fs_path, THUMB_WIDTH, THUMB_HEIGHT, True)
                    if paintable is None:
                        paintable = PaintableCover.new_from_resource(
                            '/info/febvre/Komikku/images/missing_file.png', THUMB_WIDTH, THUMB_HEIGHT)

                cover_frame = Gtk.Frame()
                cover_frame.add_css_class('row-rounded-cover-frame')
                cover_frame.set_child(Gtk.Picture.new_for_paintable(paintable))
                action_row.add_prefix(cover_frame)

                # Time
                label = Gtk.Label(label=last_read.strftime('%H:%M'))
                label.add_css_class('subtitle')
                action_row.add_suffix(label)

                # Resume button
                button = Gtk.Button.new_from_icon_name('media-playback-start-symbolic')
                button.set_tooltip_text(_('Resume'))
                button.connect('clicked', self.on_row_play_button_clicked, action_row)
                button.set_valign(Gtk.Align.CENTER)
                action_row.add_suffix(button)

                listbox.append(action_row)

            self.stack.set_visible_child_name('list')
        else:
            self.stack.set_visible_child_name('empty')

    def on_row_activated(self, row):
        self.window.card.init(row.chapter.manga)

    def on_row_play_button_clicked(self, _button, row):
        self.window.reader.init(row.chapter.manga, row.chapter)

    def search(self, _entry):
        for date_box in self.dates_box:
            listbox = date_box.get_last_child()
            listbox.invalidate_filter()
            # Hide date_box, will be shown if a least one row of listbox is not filtered
            date_box.set_visible(False)

    def show(self):
        self.populate()

        self.window.navigationview.push(self)

    def toggle_search_mode(self):
        self.searchbar.set_search_mode(not self.searchbar.get_search_mode())
