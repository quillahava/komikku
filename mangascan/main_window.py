import os
from pathlib import Path

from gi.repository import Gio
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository.GdkPixbuf import Pixbuf

from mangascan.add_dialog import AddDialog
import mangascan.config_manager
from mangascan.settings_dialog import SettingsDialog
from mangascan.manga import Manga
from mangascan.reader import Reader


class MainWindow(Gtk.ApplicationWindow):
    mobile_width = False
    page = 'library'
    manga = None
    reader = None
    first_start_grid = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logging_manager = kwargs['application'].get_logger()

        self.builder = Gtk.Builder()
        self.builder.add_from_resource("/com/gitlab/valos/MangaScan/main_window.ui")
        self.stack = self.builder.get_object('stack')
        self.reader = Reader(self.builder)

        self.assemble_window()

        if Gio.Application.get_default().development_mode is True:
            mangascan.config_manager.set_development_backup_mode(True)

    def add_actions(self):
        add_action = Gio.SimpleAction.new("add", None)
        add_action.connect("activate", self.on_left_button_clicked)

        delete_action = Gio.SimpleAction.new("delete", None)
        delete_action.connect("activate", self.on_delete_button_clicked)

        settings_action = Gio.SimpleAction.new("settings", None)
        settings_action.connect("activate", self.on_settings_menu_clicked)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about_menu_clicked)

        shortcuts_action = Gio.SimpleAction.new("shortcuts", None)
        shortcuts_action.connect("activate", self.on_shortcuts_menu_clicked)

        self.application.add_action(add_action)
        self.application.add_action(delete_action)
        self.application.add_action(settings_action)
        self.application.add_action(about_action)
        self.application.add_action(shortcuts_action)

    def add_global_accelerators(self):
        self.application.set_accels_for_action("app.settings", ["<Control>p"])
        self.application.set_accels_for_action("app.add", ["<Control>plus"])

    def apply_theme(self):
        gtk_settings = Gtk.Settings.get_default()

        gtk_settings.set_property("gtk-application-prefer-dark-theme", mangascan.config_manager.get_dark_theme())

    def assemble_window(self):
        window_size = mangascan.config_manager.get_window_size()
        self.set_default_size(window_size[0], window_size[1])

        self.create_titlebar()
        self.create_library()

        self.connect("delete-event", self.on_application_quit)
        self.connect("check-resize", self.responsive_listener)

        self.custom_css()
        self.apply_theme()
        self.show_all()

    def change_layout(self):
        pass

    def create_first_start_screen(self):
        self.first_start_grid = self.builder.get_object("first_start_grid")

        pix = Pixbuf.new_from_resource_at_scale("/com/gitlab/valos/MangaScan/images/logo.png", 256, 256, True)
        app_logo = self.builder.get_object("app_logo")
        app_logo.set_from_pixbuf(pix)

        self.add(self.first_start_grid)

    def create_library(self):
        root_path = os.path.join(str(Path.home()), 'MangaScan')
        mangas = os.listdir(root_path)

        if not mangas:
            self.create_first_start_screen()
            return
        elif self.first_start_grid:
            self.first_start_grid.destroy()

        flowbox = self.builder.get_object('library_page_flowbox')
        flowbox.connect("child-activated", self.on_manga_clicked)

        self.populate_library()

        self.add(self.stack)

    def create_titlebar(self):
        self.titlebar = self.builder.get_object("titlebar")
        self.headerbar = self.builder.get_object('headerbar')

        self.left_button = self.builder.get_object("left_button")
        self.left_button.connect("clicked", self.on_left_button_clicked, None)
        self.left_button_stack = self.builder.get_object("left_button_stack")

        self.set_titlebar(self.titlebar)

        if Gio.Application.get_default().development_mode is True:
            context = self.get_style_context()
            context.add_class("devel")

    def custom_css(self):
        screen = Gdk.Screen.get_default()

        css_provider = Gtk.CssProvider()
        css_provider_resource = Gio.File.new_for_uri("resource:///com/gitlab/valos/MangaScan/css/style.css")
        css_provider.load_from_file(css_provider_resource)

        context = Gtk.StyleContext()
        context.add_provider_for_screen(screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def on_about_menu_clicked(self, action, param):
        builder = Gtk.Builder()
        builder.add_from_resource("/com/gitlab/valos/MangaScan/about_dialog.ui")

        about_dialog = builder.get_object("about_dialog")
        about_dialog.set_modal(True)
        about_dialog.set_transient_for(self)
        about_dialog.present()

    def on_application_quit(self, window, event):
        self.save_window_size()

    def on_chapter_clicked(self, listbox, row):
        self.reader.init(self.manga, row.chapter_id)

        self.show_page('reader')

    def on_delete_button_clicked(self, action, param):
        print('delete manga')
        self.manga.delete()
        self.populate_library()
        self.show_page('library')

    def on_left_button_clicked(self, action, param):
        if self.page == 'library':
            AddDialog(self).open(action, param)
        elif self.page == 'manga':
            self.show_page('library')
        elif self.page == 'reader':
            self.show_page('manga')

    def on_manga_clicked(self, flowbox, child):
        self.manga = Manga(child.get_children()[0].manga_id)

        user_home_path = str(Path.home())
        root_path = os.path.join(user_home_path, 'MangaScan')
        manga_path = os.path.join(root_path, self.manga.id)
        cover_path = os.path.join(manga_path, 'cover.jpg')

        pixbuf = Pixbuf.new_from_file_at_scale(cover_path, 180, -1, True)
        self.builder.get_object('cover_image').set_from_pixbuf(pixbuf)

        self.builder.get_object('author_value_label').set_text(self.manga.data['author'] or '-')
        self.builder.get_object('type_value_label').set_text(self.manga.data['type'] or '-')
        self.builder.get_object('status_value_label').set_text(self.manga.data['status'] or '-')
        self.builder.get_object('server_value_label').set_text(
            '{0} ({1} chapters)'.format(self.manga.server.name, len(self.manga.data['chapters'])))

        self.builder.get_object('synopsis_value_label').set_text(self.manga.data['synopsis'] or '-')

        listbox = self.builder.get_object('chapters_listbox')
        listbox.connect("row-activated", self.on_chapter_clicked)

        for child in listbox.get_children():
            child.destroy()

        for id, chapter_data in self.manga.data['chapters'].items():
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class('listboxrow-chapter')
            row.chapter_id = id
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.add(box)

            # Chapter title
            label = Gtk.Label(xalign=0)
            label.set_line_wrap(True)
            label.set_text(chapter_data['title'])
            box.pack_start(label, True, True, 0)

            listbox.add(row)

        listbox.show_all()

        self.show_page('manga')

    def on_settings_menu_clicked(self, action, param):
        SettingsDialog(self).open(action, param)

    def on_shortcuts_menu_clicked(self, action, param):
        builder = Gtk.Builder()
        builder.add_from_resource("/com/gitlab/valos/MangaScan/shortcuts_overview.ui")

        shortcuts_overview = builder.get_object("shortcuts_overview")
        shortcuts_overview.set_modal(True)
        shortcuts_overview.set_transient_for(self)
        shortcuts_overview.present()

    def populate_library(self):
        root_path = os.path.join(str(Path.home()), 'MangaScan')
        mangas = os.listdir(root_path)

        flowbox = self.builder.get_object('library_page_flowbox')

        for child in flowbox.get_children():
            flowbox.remove(child)
            child.destroy()

        for manga_id in mangas:
            cover_path = os.path.join(root_path, manga_id, 'cover.jpg')
            if os.path.exists(cover_path):
                cover_image = Gtk.Image()
                pixbuf = Pixbuf.new_from_file_at_scale(cover_path, 180, -1, True)
                cover_image.set_from_pixbuf(pixbuf)
                cover_image.manga_id = manga_id

                flowbox.insert(cover_image, -1)

        flowbox.show_all()

    def responsive_listener(self, window):
        if self.get_allocation().width < 700:
            if self.mobile_width is True:
                return

            self.mobile_width = True
            self.change_layout()
        else:
            if self.mobile_width is True:
                self.mobile_width = False
                self.change_layout()

    def save_window_size(self):
        window_size = [self.get_size().width, self.get_size().height]
        mangascan.config_manager.set_window_size(window_size)

    def show_page(self, name):
        if name == 'library':
            self.headerbar.set_title('Manga Scan')
            self.builder.get_object('menubutton').set_popover(self.builder.get_object('menubutton_popover'))
        elif name == 'manga':
            self.headerbar.set_title(self.manga.data['name'])
            self.builder.get_object('menubutton').set_popover(self.builder.get_object('manga_page_menubutton_popover'))
        elif name == 'reader':
            pass

        self.left_button_stack.set_visible_child_name(name)
        self.stack.set_visible_child_name(name)
        self.page = name
