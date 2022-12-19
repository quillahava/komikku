# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading

from gi.repository import GLib
from gi.repository import Gtk

from komikku.models import create_db_connection
from komikku.models import Manga
from komikku.models import Settings
from komikku.utils import html_escape
from komikku.utils import log_error_traceback
from komikku.utils import create_paintable_from_data
from komikku.utils import create_paintable_from_resource


class ExplorerCardPage:
    manga = None
    manga_data = None
    manga_slug = None

    def __init__(self, parent):
        self.parent = parent
        self.window = parent.window

        self.cover_box = self.parent.card_page_cover_box
        self.cover_image = self.parent.card_page_cover_image
        self.name_label = self.parent.card_page_name_label
        self.authors_label = self.parent.card_page_authors_label
        self.status_server_label = self.parent.card_page_status_server_label
        self.add_read_button = self.parent.card_page_add_read_button
        self.genres_label = self.parent.card_page_genres_label
        self.scanlators_label = self.parent.card_page_scanlators_label
        self.chapters_label = self.parent.card_page_chapters_label
        self.last_chapter_label = self.parent.card_page_last_chapter_label
        self.synopsis_label = self.parent.card_page_synopsis_label

        self.add_read_button.connect('clicked', self.on_add_read_button_clicked)

    def adapt_to_width(self):
        # Adapt card page to window width
        if self.window.mobile_width:
            self.cover_box.set_orientation(Gtk.Orientation.VERTICAL)
            self.cover_box.props.spacing = 12

            self.name_label.props.halign = Gtk.Align.CENTER
            self.name_label.props.justify = Gtk.Justification.CENTER

            self.status_server_label.props.halign = Gtk.Align.CENTER
            self.status_server_label.props.justify = Gtk.Justification.CENTER

            self.authors_label.props.halign = Gtk.Align.CENTER
            self.authors_label.props.justify = Gtk.Justification.CENTER

            self.add_read_button.props.halign = Gtk.Align.CENTER
        else:
            self.cover_box.set_orientation(Gtk.Orientation.HORIZONTAL)
            self.cover_box.props.spacing = 24

            self.name_label.props.halign = Gtk.Align.START
            self.name_label.props.justify = Gtk.Justification.LEFT

            self.status_server_label.props.halign = Gtk.Align.START
            self.status_server_label.props.justify = Gtk.Justification.LEFT

            self.authors_label.props.halign = Gtk.Align.START
            self.authors_label.props.justify = Gtk.Justification.LEFT

            self.add_read_button.props.halign = Gtk.Align.START

    def on_add_button_clicked(self):
        def run():
            manga = Manga.new(self.manga_data, self.parent.server, Settings.get_default().long_strip_detection)
            GLib.idle_add(complete, manga)

        def complete(manga):
            self.manga = manga

            self.window.show_notification(_('{0} manga added').format(self.manga.name))

            self.window.library.on_manga_added(self.manga)

            self.add_read_button.set_sensitive(True)
            self.add_read_button.get_child().get_first_child().set_from_icon_name('media-playback-start-symbolic')
            self.add_read_button.get_child().get_last_child().set_text(_('Read'))
            self.window.activity_indicator.stop()

            return False

        self.window.activity_indicator.start()
        self.add_read_button.set_sensitive(False)

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def on_add_read_button_clicked(self, _button):
        if self.manga:
            self.on_read_button_clicked()
        else:
            self.on_add_button_clicked()

    def on_read_button_clicked(self):
        # Stop search, most populars and latest_updates if not ended
        self.parent.search_page.stop_search = True
        self.parent.search_page.stop_most_populars = True
        self.parent.search_page.stop_latest_updates = True

        self.window.card.init(self.manga, transition=False)

    def populate(self, manga_data):
        def run(server, manga_slug):
            try:
                current_manga_data = self.parent.server.get_manga_data(manga_data)

                if current_manga_data is not None:
                    GLib.idle_add(complete, current_manga_data, server)
                else:
                    GLib.idle_add(error, server, manga_slug)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, server, manga_slug, user_error_message)

        def complete(manga_data, server):
            if server != self.parent.server or manga_data['slug'] != self.manga_slug:
                return False

            self.manga_data = manga_data

            # Populate card
            try:
                cover_data = self.parent.server.get_manga_cover_image(self.manga_data.get('cover'))
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

            self.cover_image.set_paintable(paintable)

            self.name_label.set_label(manga_data['name'])

            authors = html_escape(', '.join(self.manga_data['authors'])) if self.manga_data['authors'] else _('Unknown author')
            self.authors_label.set_markup(authors)

            if self.manga_data['server_id'] != 'local':
                self.status_server_label.set_markup(
                    '{0} · <a href="{1}">{2}</a> ({3})'.format(
                        _(Manga.STATUSES[self.manga_data['status']]) if self.manga_data['status'] else _('Unknown status'),
                        self.parent.server.get_manga_url(self.manga_data['slug'], self.manga_data.get('url')),
                        html_escape(self.parent.server.name),
                        self.parent.server.lang.upper()
                    )
                )
            else:
                self.status_server_label.set_markup(
                    '{0} · {1}'.format(
                        _('Unknown status'),
                        html_escape(_('Local'))
                    )
                )

            if self.manga_data['genres']:
                self.genres_label.set_markup(html_escape(', '.join(self.manga_data['genres'])))
                self.genres_label.get_parent().get_parent().show()
            else:
                self.genres_label.get_parent().get_parent().hide()

            if self.manga_data['scanlators']:
                self.scanlators_label.set_markup(html_escape(', '.join(self.manga_data['scanlators'])))
                self.scanlators_label.get_parent().get_parent().show()
            else:
                self.scanlators_label.get_parent().get_parent().hide()

            self.chapters_label.set_markup(str(len(self.manga_data['chapters'])))

            if self.manga_data['chapters']:
                self.last_chapter_label.set_markup(html_escape(self.manga_data['chapters'][-1]['title']))
                self.last_chapter_label.get_parent().get_parent().show()
            else:
                self.last_chapter_label.get_parent().get_parent().hide()

            self.synopsis_label.set_markup(
                html_escape(self.manga_data['synopsis']) if self.manga_data['synopsis'] else '-'
            )

            self.window.activity_indicator.stop()
            self.parent.show_page('card')

            return False

        def error(server, manga_slug, message=None):
            if server != self.parent.server or manga_slug != self.manga_slug:
                return False

            self.window.activity_indicator.stop()

            self.window.show_notification(message or _("Oops, failed to retrieve manga's information."), 2)

            return False

        self.manga = None
        self.manga_slug = manga_data['slug']
        self.window.activity_indicator.start()

        thread = threading.Thread(target=run, args=(self.parent.server, self.manga_slug, ))
        thread.daemon = True
        thread.start()

    def show(self):
        self.parent.title_stack.get_child_by_name('card').set_text(self.manga_data['name'])

        # Check if selected manga is already in library
        db_conn = create_db_connection()
        row = db_conn.execute(
            'SELECT * FROM mangas WHERE slug = ? AND server_id = ?',
            (self.manga_data['slug'], self.manga_data['server_id'])
        ).fetchone()
        db_conn.close()

        if row:
            self.manga = Manga.get(row['id'], self.parent.server)

            self.add_read_button.get_child().get_first_child().set_from_icon_name('media-playback-start-symbolic')
            self.add_read_button.get_child().get_last_child().set_text(_('Read'))
        else:
            self.add_read_button.get_child().get_first_child().set_from_icon_name('list-add-symbolic')
            self.add_read_button.get_child().get_last_child().set_text(_('Add to Library'))
