# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from gi.repository import Adw
from gi.repository import GObject
from gi.repository import Gtk

from komikku.models import Category
from komikku.models import create_db_connection
from komikku.models import Settings


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/categories_editor.ui')
class CategoriesEditor(Gtk.ScrolledWindow):
    __gtype_name__ = 'CategoriesEditor'

    window = NotImplemented
    edited_row = None

    add_entry = Gtk.Template.Child('add_entry')
    add_button = Gtk.Template.Child('add_button')

    stack = Gtk.Template.Child('stack')
    listbox = Gtk.Template.Child('listbox')

    def __init__(self, window):
        Gtk.ScrolledWindow.__init__(self)

        self.window = window

        self.add_entry.connect('activate', self.add_category)
        self.add_button.connect('clicked', self.add_category)

        self.window.stack.add_named(self, 'categories_editor')

    def add_category(self, _button):
        label = self.add_entry.get_text().strip()
        if not label:
            return

        category = Category.new(label)
        if category:
            self.stack.set_visible_child_name('list')

            self.add_entry.set_text('')
            row = CategoryRow(category)
            row.delete_button.connect('clicked', self.delete_category, row)
            row.save_button.connect('clicked', self.update_category, row)
            row.connect('edit-mode-changed', self.on_category_edit_mode_changed)

            self.listbox.append(row)

            self.window.library.categories_list.populate()

    def delete_category(self, _button, row):
        def confirm_callback():
            deleted_is_current = Settings.get_default().selected_category == row.category.id

            row.category.delete()
            self.listbox.remove(row)

            if not self.listbox.get_first_child():
                # No more categories
                self.stack.set_visible_child_name('empty')

            # If category is current selected category in Library, reset selected category
            if deleted_is_current:
                Settings.get_default().selected_category = 0

            self.window.library.categories_list.populate(refresh_library=deleted_is_current)

        self.window.confirm(
            _('Delete?'),
            _('Are you sure you want to delete\n"{0}" category?').format(row.category.label),
            confirm_callback
        )

    def on_category_edit_mode_changed(self, row, active):
        if not active:
            if self.edited_row == row:
                self.edited_row = None
            return

        if self.edited_row:
            self.edited_row.set_edit_mode(active=False)

        self.edited_row = row

    def populate(self):
        # Clear
        row = self.listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            self.listbox.remove(row)
            row = next_row

        db_conn = create_db_connection()
        records = db_conn.execute('SELECT * FROM categories ORDER BY label ASC').fetchall()
        db_conn.close()

        if records:
            for record in records:
                category = Category.get(record['id'])

                row = CategoryRow(category)
                row.delete_button.connect('clicked', self.delete_category, row)
                row.save_button.connect('clicked', self.update_category, row)
                row.connect('edit-mode-changed', self.on_category_edit_mode_changed)

                self.listbox.append(row)

            self.stack.set_visible_child_name('list')
        else:
            self.stack.set_visible_child_name('empty')

    def show(self, transition=True):
        self.populate()

        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.library_flap_reveal_button.hide()

        self.window.right_button_stack.hide()

        self.window.menu_button.hide()

        self.window.show_page('categories_editor', transition=transition)

    def update_category(self, _button, row):
        label = row.edit_entry.get_text().strip()
        if not label:
            return

        res = row.category.update(dict(
            label=label,
        ))
        if res:
            row.set_label(label)
            row.set_edit_mode(active=False)

            self.window.library.categories_list.populate()


class CategoryRow(Gtk.ListBoxRow):
    __gsignals__ = {
        'edit-mode-changed': (GObject.SIGNAL_RUN_FIRST, None, (bool, )),
    }

    category = None

    def __init__(self, category):
        Gtk.ListBoxRow.__init__(self, activatable=False)

        self.box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=8, margin_start=12, margin_bottom=8, margin_end=12
        )

        self.category = category

        label = category.label
        if nb_mangas := len(category.mangas):
            label = f'{label} ({nb_mangas})'
        self.label = Gtk.Label(label=label, hexpand=True)
        self.label.set_halign(Gtk.Align.START)
        self.box.append(self.label)

        self.edit_entry = Gtk.Entry(visible=False, hexpand=True)
        self.edit_entry.set_valign(Gtk.Align.CENTER)
        self.edit_entry.set_halign(Gtk.Align.FILL)
        self.box.append(self.edit_entry)

        self.edit_button = Gtk.Button.new_from_icon_name('document-edit-symbolic')
        self.edit_button.set_valign(Gtk.Align.CENTER)
        self.edit_button.connect('clicked', self.set_edit_mode, True)
        self.box.append(self.edit_button)

        self.delete_button = Gtk.Button.new_from_icon_name('user-trash-symbolic')
        self.delete_button.set_valign(Gtk.Align.CENTER)
        self.box.append(self.delete_button)

        self.cancel_button = Gtk.Button.new_from_icon_name('edit-undo-symbolic')
        self.cancel_button.set_valign(Gtk.Align.CENTER)
        self.cancel_button.hide()
        self.cancel_button.connect('clicked', self.set_edit_mode, False)
        self.box.append(self.cancel_button)

        self.save_button = Gtk.Button.new_from_icon_name('document-save-symbolic')
        self.save_button.set_valign(Gtk.Align.CENTER)
        self.save_button.hide()
        self.box.append(self.save_button)

        self.set_child(self.box)

    def set_edit_mode(self, _button=None, active=False):
        if active:
            self.label.hide()
            self.edit_entry.set_text(self.category.label)
            self.edit_entry.show()
            self.delete_button.hide()
            self.edit_button.hide()
            self.cancel_button.show()
            self.save_button.show()
        else:
            self.label.show()
            self.edit_entry.set_text('')
            self.edit_entry.hide()
            self.delete_button.show()
            self.edit_button.show()
            self.cancel_button.hide()
            self.save_button.hide()

        self.emit('edit-mode-changed', active)

    def set_label(self, text):
        self.label.set_text(text)
