# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import time

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from komikku.card.categories_list import CategoriesList
from komikku.card.chapters_list import ChaptersList
from komikku.utils import create_paintable_from_file
from komikku.utils import create_paintable_from_resource
from komikku.utils import folder_size
from komikku.utils import html_escape


class Card:
    manga = None
    selection_mode = False

    def __init__(self, window):
        self.window = window
        self.builder = window.builder
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/card.xml')
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/card_selection_mode.xml')

        self.viewswitchertitle = self.window.card_viewswitchertitle
        self.viewswitcherbar = self.window.card_viewswitcherbar

        self.stack = self.window.card_stack
        self.info_box = InfoBox(self)
        self.categories_list = CategoriesList(self)
        self.chapters_list = ChaptersList(self)

        self.viewswitchertitle.connect('notify::title-visible', self.on_viewswitchertitle_title_visible)
        self.window.card_resume_button.connect('clicked', self.on_resume_button_clicked)
        self.stack.connect('notify::visible-child', self.on_page_changed)
        self.window.updater.connect('manga-updated', self.on_manga_updated)
        self.window.connect('notify::page', self.on_shown)

    def add_actions(self):
        self.delete_action = Gio.SimpleAction.new('card.delete', None)
        self.delete_action.connect('activate', self.on_delete_menu_clicked)
        self.window.application.add_action(self.delete_action)

        self.update_action = Gio.SimpleAction.new('card.update', None)
        self.update_action.connect('activate', self.on_update_menu_clicked)
        self.window.application.add_action(self.update_action)

        variant = GLib.Variant.new_string('desc')
        self.sort_order_action = Gio.SimpleAction.new_stateful('card.sort-order', variant.get_type(), variant)
        self.sort_order_action.connect('activate', self.chapters_list.on_sort_order_changed)
        self.window.application.add_action(self.sort_order_action)

        self.open_in_browser_action = Gio.SimpleAction.new('card.open-in-browser', None)
        self.open_in_browser_action.connect('activate', self.on_open_in_browser_menu_clicked)
        self.window.application.add_action(self.open_in_browser_action)

        self.chapters_list.add_actions()

    def enter_selection_mode(self, *args):
        if self.selection_mode:
            return

        self.window.left_button.set_label(_('Cancel'))
        self.window.left_button.set_tooltip_text(_('Cancel'))
        self.window.right_button_stack.set_visible(False)
        self.window.menu_button.set_visible(False)

        self.selection_mode = True
        self.chapters_list.enter_selection_mode()

        self.viewswitchertitle.set_view_switcher_enabled(False)
        self.viewswitcherbar.set_reveal(False)

    def init(self, manga, transition=True, show=True):
        # Default page is `Info` page except when we come from Explorer
        self.stack.set_visible_child_name('chapters' if self.window.page == 'explorer' else 'info')

        self.manga = manga
        # Unref chapters to force a reload
        self.manga._chapters = None

        if manga.server.status == 'disabled':
            self.window.show_notification(
                _('NOTICE\n{0} server is not longer supported.\nPlease switch to another server.').format(manga.server.name)
            )

        if show:
            self.show()

    def leave_selection_mode(self, _param=None):
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.right_button_stack.set_visible(True)
        self.window.menu_button.set_visible(True)

        self.chapters_list.leave_selection_mode()
        self.selection_mode = False

        self.viewswitchertitle.set_view_switcher_enabled(True)
        self.viewswitcherbar.set_reveal(True)
        self.viewswitchertitle.set_subtitle('')

    def on_delete_menu_clicked(self, action, param):
        self.window.library.delete_mangas([self.manga, ])

    def on_manga_updated(self, updater, manga, nb_recent_chapters, nb_deleted_chapters, synced):
        if self.window.page == 'card' and self.manga.id == manga.id:
            self.manga = manga

            if manga.server.sync:
                self.window.show_notification(_('Read progress synchronization with server completed successfully'))

            if nb_recent_chapters > 0 or nb_deleted_chapters > 0 or synced:
                self.chapters_list.populate()

            self.info_box.populate()

    def on_open_in_browser_menu_clicked(self, action, param):
        if url := self.manga.server.get_manga_url(self.manga.slug, self.manga.url):
            Gtk.show_uri(None, url, time.time())
        else:
            self.window.show_notification(_('Failed to get manga URL'))

    def on_page_changed(self, _stack, _param):
        if self.selection_mode and self.stack.get_visible_child_name() != 'chapters':
            self.leave_selection_mode()

    def on_resize(self):
        self.info_box.on_resize()

    def on_resume_button_clicked(self, widget):
        chapters = []
        for i in range(self.chapters_list.list_model.get_n_items()):
            chapters.append(self.chapters_list.list_model.get_item(i).chapter)

        if self.chapters_list.sort_order.endswith('desc'):
            chapters.reverse()

        chapter = None
        for chapter_ in chapters:
            if not chapter_.read:
                chapter = chapter_
                break

        if not chapter:
            chapter = chapters[0]

        self.window.reader.init(self.manga, chapter)

    def on_shown(self, _window, _page):
        # Card can only be shown from library, explorer or history
        if self.window.page != 'card' or self.window.previous_page not in ('library', 'explorer', 'history'):
            return

        # Wait page is shown (transition is ended) to populate
        # Operation is resource intensive and could disrupt page transition
        self.populate()

    def on_update_menu_clicked(self, _action, _param):
        self.window.updater.add(self.manga)
        self.window.updater.start()

    def on_viewswitchertitle_title_visible(self, _viewswitchertitle, _param):
        if self.viewswitchertitle.get_title_visible() and not self.selection_mode:
            self.viewswitcherbar.set_reveal(True)
        else:
            self.viewswitcherbar.set_reveal(False)

    def populate(self):
        self.chapters_list.set_sort_order(invalidate=False)
        self.chapters_list.populate()
        self.categories_list.populate()

    def set_actions_enabled(self, enabled):
        self.delete_action.set_enabled(enabled)
        self.update_action.set_enabled(enabled)
        self.sort_order_action.set_enabled(enabled)

    def show(self, transition=True, reset=True):
        if reset:
            self.viewswitchertitle.set_title(self.manga.name)
            self.info_box.populate()

        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.left_extra_button_stack.set_visible(False)

        self.window.right_button_stack.set_visible_child_name('card')
        self.window.right_button_stack.set_visible(True)

        self.window.menu_button.set_icon_name('view-more-symbolic')
        self.window.menu_button.set_visible(True)

        self.open_in_browser_action.set_enabled(self.manga.server_id != 'local')

        self.window.show_page('card', transition=transition)

    def refresh(self, chapters):
        self.info_box.refresh()
        self.chapters_list.refresh(chapters)


class InfoBox:
    def __init__(self, card):
        self.card = card
        self.window = card.window

        self.cover_box = self.window.card_cover_box
        self.name_label = self.window.card_name_label
        self.cover_image = self.window.card_cover_image
        self.authors_label = self.window.card_authors_label
        self.status_server_label = self.window.card_status_server_label
        self.resume2_button = self.window.card_resume2_button
        self.genres_label = self.window.card_genres_label
        self.scanlators_label = self.window.card_scanlators_label
        self.chapters_label = self.window.card_chapters_label
        self.last_update_label = self.window.card_last_update_label
        self.synopsis_label = self.window.card_synopsis_label
        self.size_on_disk_label = self.window.card_size_on_disk_label

        self.resume2_button.connect('clicked', self.card.on_resume_button_clicked)

        self.adapt_to_width()

    def adapt_to_width(self):
        if self.window.mobile_width:
            self.cover_box.set_orientation(Gtk.Orientation.VERTICAL)
            self.cover_box.props.spacing = 12

            self.name_label.props.halign = Gtk.Align.CENTER
            self.name_label.props.justify = Gtk.Justification.CENTER

            self.status_server_label.props.halign = Gtk.Align.CENTER
            self.status_server_label.props.justify = Gtk.Justification.CENTER

            self.authors_label.props.halign = Gtk.Align.CENTER
            self.authors_label.props.justify = Gtk.Justification.CENTER

            self.resume2_button.props.halign = Gtk.Align.CENTER
        else:
            self.cover_box.set_orientation(Gtk.Orientation.HORIZONTAL)
            self.cover_box.props.spacing = 24

            self.name_label.props.halign = Gtk.Align.START
            self.name_label.props.justify = Gtk.Justification.LEFT

            self.status_server_label.props.halign = Gtk.Align.START
            self.status_server_label.props.justify = Gtk.Justification.LEFT

            self.authors_label.props.halign = Gtk.Align.START
            self.authors_label.props.justify = Gtk.Justification.LEFT

            self.resume2_button.props.halign = Gtk.Align.START

    def on_resize(self):
        self.adapt_to_width()

    def populate(self):
        cover_width = 170
        manga = self.card.manga

        self.name_label.set_text(manga.name)

        if manga.cover_fs_path is None:
            paintable = create_paintable_from_resource('/info/febvre/Komikku/images/missing_file.png', cover_width, -1)
        else:
            paintable = create_paintable_from_file(manga.cover_fs_path, cover_width, -1)
            if paintable is None:
                paintable = create_paintable_from_resource('/info/febvre/Komikku/images/missing_file.png', cover_width, -1)

        self.cover_image.set_paintable(paintable)

        authors = html_escape(', '.join(manga.authors)) if manga.authors else _('Unknown author')
        self.authors_label.set_markup(authors)

        if manga.server_id != 'local':
            self.status_server_label.set_markup(
                '{0} · <a href="{1}">{2}</a> ({3})'.format(
                    _(manga.STATUSES[manga.status]) if manga.status else _('Unknown status'),
                    manga.server.get_manga_url(manga.slug, manga.url),
                    html_escape(manga.server.name),
                    manga.server.lang.upper()
                )
            )
        else:
            self.status_server_label.set_markup(
                '{0} · {1}'.format(
                    _('Unknown status'),
                    html_escape(_('Local'))
                )
            )

        if manga.genres:
            self.genres_label.set_markup(html_escape(', '.join(manga.genres)))
            self.genres_label.get_parent().get_parent().set_visible(True)
        else:
            self.genres_label.get_parent().get_parent().set_visible(False)

        if manga.scanlators:
            self.scanlators_label.set_markup(html_escape(', '.join(manga.scanlators)))
            self.scanlators_label.get_parent().get_parent().set_visible(True)
        else:
            self.scanlators_label.get_parent().get_parent().set_visible(False)

        self.chapters_label.set_markup(str(len(manga.chapters)))

        if manga.last_update:
            self.last_update_label.set_markup(manga.last_update.strftime(_('%m/%d/%Y')))
            self.last_update_label.get_parent().get_parent().set_visible(True)
        else:
            self.last_update_label.get_parent().get_parent().set_visible(False)

        self.set_disk_usage()

        self.synopsis_label.set_markup(html_escape(manga.synopsis) if manga.synopsis else '-')

    def refresh(self):
        self.set_disk_usage()

    def set_disk_usage(self):
        self.size_on_disk_label.set_text(folder_size(self.card.manga.path) or '-')
