# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from komikku.card.categories_list import CategoriesList
from komikku.card.chapters_list import ChaptersList
from komikku.models import Settings
from komikku.utils import COVER_WIDTH
from komikku.utils import folder_size
from komikku.utils import html_escape
from komikku.utils import PaintableCover


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/card.ui')
class CardPage(Adw.NavigationPage):
    __gtype_name__ = 'CardPage'

    left_button = Gtk.Template.Child('left_button')
    title_stack = Gtk.Template.Child('title_stack')
    title = Gtk.Template.Child('title')
    viewswitcher = Gtk.Template.Child('viewswitcher')
    resume_button = Gtk.Template.Child('resume_button')
    menu_button = Gtk.Template.Child('menu_button')

    progressbar = Gtk.Template.Child('progressbar')
    progressbar_timeout_id = None
    stack = Gtk.Template.Child('stack')
    categories_stack = Gtk.Template.Child('categories_stack')
    categories_scrolledwindow = Gtk.Template.Child('categories_scrolledwindow')
    categories_listbox = Gtk.Template.Child('categories_listbox')
    chapters_scrolledwindow = Gtk.Template.Child('chapters_scrolledwindow')
    chapters_listview = Gtk.Template.Child('chapters_listview')
    chapters_selection_mode_actionbar = Gtk.Template.Child('chapters_selection_mode_actionbar')
    chapters_selection_mode_menubutton = Gtk.Template.Child('chapters_selection_mode_menubutton')
    info_scrolledwindow = Gtk.Template.Child('info_scrolledwindow')
    cover_box = Gtk.Template.Child('cover_box')
    cover_image = Gtk.Template.Child('cover_image')
    name_label = Gtk.Template.Child('name_label')
    authors_label = Gtk.Template.Child('authors_label')
    status_server_label = Gtk.Template.Child('status_server_label')
    buttons_box = Gtk.Template.Child('buttons_box')
    add_button = Gtk.Template.Child('add_button')
    resume2_button = Gtk.Template.Child('resume2_button')
    genres_label = Gtk.Template.Child('genres_label')
    scanlators_label = Gtk.Template.Child('scanlators_label')
    chapters_label = Gtk.Template.Child('chapters_label')
    last_update_label = Gtk.Template.Child('last_update_label')
    synopsis_label = Gtk.Template.Child('synopsis_label')
    size_on_disk_label = Gtk.Template.Child('size_on_disk_label')
    viewswitcherbar = Gtk.Template.Child('viewswitcherbar')

    manga = None
    pool_to_update = False
    pool_to_update_offset = 0
    selection_mode = False

    def __init__(self, window):
        Adw.NavigationPage.__init__(self)

        self.window = window
        self.builder = window.builder
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/card.xml')
        self.builder.add_from_resource('/info/febvre/Komikku/ui/menu/card_selection_mode.xml')

        self.connect('hidden', self.on_hidden)
        self.connect('shown', self.on_shown)
        self.window.controller_key.connect('key-pressed', self.on_key_pressed)

        # Header bar
        self.left_button.connect('clicked', self.leave_selection_mode)
        self.resume_button.connect('clicked', self.on_resume_button_clicked)
        self.menu_button.set_menu_model(self.builder.get_object('menu-card'))
        # Focus is lost after showing popover submenu (bug?)
        self.menu_button.get_popover().connect('closed', lambda _popover: self.menu_button.grab_focus())

        # Pool-to-Update
        self.pool_to_update_revealer = self.window.pool_to_update_revealer
        self.pool_to_update_spinner = self.window.pool_to_update_spinner
        self.pool_to_update_revealer.bind_property('child-revealed', self.pool_to_update_spinner, 'spinning', 0)
        # Drag gesture
        self.gesture_drag = Gtk.GestureDrag.new()
        self.gesture_drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.gesture_drag.connect('drag-end', self.on_gesture_drag_end)
        self.gesture_drag.connect('drag-update', self.on_gesture_drag_update)
        self.add_controller(self.gesture_drag)

        self.info_box = InfoBox(self)
        self.categories_list = CategoriesList(self)
        self.chapters_list = ChaptersList(self)

        self.window.updater.connect('manga-updated', self.on_manga_updated)

        self.window.breakpoint.add_setter(self.viewswitcherbar, 'reveal', True)
        self.window.breakpoint.add_setter(self.title_stack, 'visible-child', self.title)

        self.window.navigationview.add(self)

    def add_actions(self):
        self.delete_action = Gio.SimpleAction.new('card.delete', None)
        self.delete_action.connect('activate', self.on_delete_menu_clicked)
        self.window.application.add_action(self.delete_action)

        self.update_action = Gio.SimpleAction.new('card.update', None)
        self.update_action.connect('activate', self.on_update_request)
        self.window.application.add_action(self.update_action)

        variant = GLib.Variant.new_string('desc')
        self.sort_order_action = Gio.SimpleAction.new_stateful('card.sort-order', variant.get_type(), variant)
        self.sort_order_action.connect('activate', self.chapters_list.on_sort_order_changed)
        self.window.application.add_action(self.sort_order_action)

        self.open_in_browser_action = Gio.SimpleAction.new('card.open-in-browser', None)
        self.open_in_browser_action.connect('activate', self.on_open_in_browser_menu_clicked)
        self.window.application.add_action(self.open_in_browser_action)

        self.chapters_list.add_actions()

    def enter_selection_mode(self, init=False):
        if self.selection_mode:
            return

        self.selection_mode = True
        self.chapters_list.enter_selection_mode(init)

        self.props.can_pop = False

        self.left_button.set_label(_('Cancel'))
        self.left_button.set_tooltip_text(_('Cancel'))
        self.left_button.set_visible(True)

        self.viewswitcher.set_visible(False)
        self.viewswitcherbar.set_visible(False)
        self.title_stack.set_visible_child(self.title)

        self.resume_button.set_visible(False)
        self.menu_button.set_visible(False)

    def init(self, manga):
        # Default page is `Info`
        self.stack.set_visible_child_name('info')

        # Hide Categories if manga is not in Library
        self.stack.get_page(self.stack.get_child_by_name('categories')).set_visible(manga.in_library)

        self.manga = manga
        # Unref chapters to force a reload
        self.manga._chapters = None

        self.show()

    def leave_selection_mode(self, *args):
        self.selection_mode = False
        self.chapters_list.leave_selection_mode()

        self.props.can_pop = True

        self.left_button.set_visible(False)

        self.viewswitcher.set_visible(True)
        self.viewswitcherbar.set_visible(True)
        self.title.set_subtitle('')
        if not self.viewswitcherbar.get_reveal():
            self.title_stack.set_visible_child(self.viewswitcher)

        self.resume_button.set_visible(True)
        self.menu_button.set_visible(True)

    def on_add_button_clicked(self, _button):
        # Show categories
        self.stack.get_page(self.stack.get_child_by_name('categories')).set_visible(True)
        # Hide Add to Library button
        self.info_box.add_button.set_visible(False)
        self.info_box.resume2_button.add_css_class('suggested-action')
        # Update manga
        self.manga.add_in_library()
        self.window.library.on_manga_added(self.manga)

    def on_delete_menu_clicked(self, _action, _gparam):
        self.window.library.delete_mangas([self.manga, ])

    def on_gesture_drag_end(self, _controller, _offset_x, _offset_y):
        if not self.pool_to_update:
            return

        self.pool_to_update = False
        self.pool_to_update_revealer.set_reveal_child(False)

        if self.pool_to_update_offset > 2 * 150:
            self.on_update_request()

        self.gesture_drag.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_gesture_drag_update(self, _controller, _offset_x, offset_y):
        _active, start_x, start_y = self.gesture_drag.get_start_point()

        page = self.stack.get_visible_child_name()
        if page == 'info':
            scroll_value = self.info_scrolledwindow.get_vadjustment().props.value
        elif page == 'chapters':
            scroll_value = self.chapters_scrolledwindow.get_vadjustment().props.value
        else:
            scroll_value = self.categories_scrolledwindow.get_vadjustment().props.value

        if scroll_value != 0 or offset_y < 0 or self.selection_mode or start_x < 32 or start_y > self.get_height() / 3:
            return

        self.pool_to_update_offset = offset_y

        if not self.pool_to_update:
            self.pool_to_update = True
            # Adjust revealer position
            self.pool_to_update_revealer.set_margin_top(self.get_child().get_top_bar_height())
            self.pool_to_update_revealer.set_reveal_child(True)
        else:
            self.pool_to_update_spinner.props.margin_top = max(0, min(150, offset_y / 2))

    def on_hidden(self, _page):
        # Force stop of update indicator (in case an update is in progress)
        self.toggle_update_indicator(False)

    def on_key_pressed(self, _controller, keyval, _keycode, state):
        if self.window.page != self.props.tag:
            return Gdk.EVENT_PROPAGATE

        modifiers = state & Gtk.accelerator_get_default_mod_mask()
        if self.selection_mode:
            if keyval == Gdk.KEY_Escape or (modifiers == Gdk.ModifierType.ALT_MASK and keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left)):
                self.leave_selection_mode()
                # Stop event to prevent back navigation
                return Gdk.EVENT_STOP
        else:
            # Allow to enter in selection mode with <SHIFT>+Arrow key
            if modifiers != Gdk.ModifierType.SHIFT_MASK or keyval not in (Gdk.KEY_Up, Gdk.KEY_KP_Up, Gdk.KEY_Down, Gdk.KEY_KP_Down):
                return Gdk.EVENT_PROPAGATE

            self.enter_selection_mode()

        return Gdk.EVENT_PROPAGATE

    def on_manga_updated(self, _updater, manga, result):
        if (self.window.page == self.props.tag or self.window.previous_page == self.props.tag) and self.manga.id == manga.id:
            self.manga = manga

            if manga.server.sync:
                self.window.show_notification(_('Read progress synchronization with server completed successfully'))

            if result['nb_recent_chapters'] > 0 or result['nb_deleted_chapters'] > 0 or result['synced']:
                self.chapters_list.populate()

            self.info_box.populate()

    def on_open_in_browser_menu_clicked(self, _action, _gparam):
        if uri := self.manga.server.get_manga_url(self.manga.slug, self.manga.url):
            Gtk.UriLauncher.new(uri=uri).launch()
        else:
            self.window.show_notification(_('Failed to get manga URL'))

    def on_resume_button_clicked(self, _button):
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

    def on_shown(self, _page):
        def do_populate():
            if self.manga.server.status == 'disabled':
                self.window.show_notification(
                    _('NOTICE\n{0} is no longer supported.\nPlease switch to another server.').format(self.manga.server.name)
                )

            # Show update indicator (in case an update is in progress)
            self.toggle_update_indicator()

            if self.window.last_navigation_action != 'push':
                return

            # Wait page is shown (transition is ended) to populate
            # Operation is resource intensive and could disrupt page transition
            self.populate()

        if Settings.get_default().disable_animations:
            # When animations are disabled, popped/pushed events are sent after `shown` event (bug?)
            # Use idle_add to be sure that last `popped` or `pushed` event has been received
            GLib.idle_add(do_populate)
        else:
            do_populate()

    def on_update_request(self, _action=None, _param=None):
        self.window.updater.add(self.manga)
        self.window.updater.start()

        # Start update indicator
        self.toggle_update_indicator()

    def populate(self):
        self.chapters_list.set_sort_order(invalidate=False)
        self.chapters_list.populate()
        self.categories_list.populate()

    def refresh(self, chapters):
        self.info_box.refresh()
        self.chapters_list.refresh(chapters)

    def remove_backdrop(self):
        self.remove_css_class('backdrop')

    def set_actions_enabled(self, enabled):
        self.delete_action.set_enabled(enabled)
        self.update_action.set_enabled(enabled)
        self.sort_order_action.set_enabled(enabled)

    def set_backdrop(self):
        if Adw.StyleManager.get_default().get_high_contrast() or not Settings.get_default().card_backdrop:
            return

        if backdrop_colors_css := self.manga.backdrop_colors_css:
            self.window.css_provider.load_from_string(backdrop_colors_css)
            self.add_css_class('backdrop')

    def show(self):
        self.props.title = self.manga.name  # Adw.NavigationPage title
        self.title.set_title(self.manga.name)
        self.info_box.populate()

        self.open_in_browser_action.set_enabled(self.manga.server_id != 'local')

        # Reset scrolling in all pages
        for page in self.stack.get_pages():
            scrolledwindow = page.get_child() if page.props.name != 'chapters' else page.get_child().get_first_child()
            scrolledwindow.get_vadjustment().props.value = 0

        self.window.navigationview.push(self)

    def toggle_update_indicator(self, state=True):
        if state is False:
            # Force indicator to stop (when page is left for example)
            if self.progressbar_timeout_id is not None:
                try:
                    GLib.source_remove(self.progressbar_timeout_id)
                except Exception:
                    pass
                else:
                    self.progressbar_timeout_id = None
                    self.progressbar.props.fraction = 0

            return

        def pulse(manga_id):
            if self.window.updater.current_id == manga_id:
                self.progressbar.pulse()
                return GLib.SOURCE_CONTINUE

            # Update is ended, stop indicator
            self.progressbar_timeout_id = None
            self.progressbar.props.fraction = 0
            return GLib.SOURCE_REMOVE

        self.progressbar_timeout_id = GLib.timeout_add(250, pulse, self.manga.id)


class InfoBox:
    def __init__(self, card):
        self.card = card
        self.window = card.window

        self.cover_box = self.card.cover_box
        self.cover_image = self.card.cover_image
        self.name_label = self.card.name_label
        self.authors_label = self.card.authors_label
        self.status_server_label = self.card.status_server_label
        self.buttons_box = self.card.buttons_box
        self.add_button = self.card.add_button
        self.resume2_button = self.card.resume2_button
        self.genres_label = self.card.genres_label
        self.scanlators_label = self.card.scanlators_label
        self.chapters_label = self.card.chapters_label
        self.last_update_label = self.card.last_update_label
        self.synopsis_label = self.card.synopsis_label
        self.size_on_disk_label = self.card.size_on_disk_label

        self.add_button.connect('clicked', self.card.on_add_button_clicked)
        self.resume2_button.connect('clicked', self.card.on_resume_button_clicked)

        self.window.breakpoint.add_setter(self.cover_box, 'orientation', Gtk.Orientation.VERTICAL)
        self.window.breakpoint.add_setter(self.cover_box, 'spacing', 12)
        self.window.breakpoint.add_setter(self.name_label, 'halign', Gtk.Align.CENTER)
        self.window.breakpoint.add_setter(self.name_label, 'justify', Gtk.Justification.CENTER)
        self.window.breakpoint.add_setter(self.status_server_label, 'halign', Gtk.Align.CENTER)
        self.window.breakpoint.add_setter(self.status_server_label, 'justify', Gtk.Justification.CENTER)
        self.window.breakpoint.add_setter(self.authors_label, 'halign', Gtk.Align.CENTER)
        self.window.breakpoint.add_setter(self.authors_label, 'justify', Gtk.Justification.CENTER)
        self.window.breakpoint.add_setter(self.buttons_box, 'orientation', Gtk.Orientation.VERTICAL)
        self.window.breakpoint.add_setter(self.buttons_box, 'spacing', 18)
        self.window.breakpoint.add_setter(self.buttons_box, 'halign', Gtk.Align.CENTER)

    def populate(self):
        manga = self.card.manga

        self.name_label.set_text(manga.name)

        if manga.cover_fs_path is None:
            paintable = PaintableCover.new_from_resource('/info/febvre/Komikku/images/missing_file.png', COVER_WIDTH)
            self.card.remove_backdrop()
        else:
            paintable = PaintableCover.new_from_file(manga.cover_fs_path, COVER_WIDTH)
            if paintable:
                self.card.set_backdrop()
            else:
                paintable = PaintableCover.new_from_resource('/info/febvre/Komikku/images/missing_file.png', COVER_WIDTH)
                self.card.remove_backdrop()

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

        if manga.in_library:
            self.add_button.set_visible(False)
            self.resume2_button.add_css_class('suggested-action')
        else:
            self.add_button.set_visible(True)
            self.resume2_button.remove_css_class('suggested-action')

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
