# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
import threading

from gi.repository import Adw
from gi.repository import GLib
from gi.repository import Gtk

from komikku.models import Category
from komikku.models import CategoryVirtual
from komikku.models import create_db_connection
from komikku.models import delete_rows
from komikku.models import insert_rows
from komikku.models import Settings


class CategoriesList:
    edit_mode = False  # mode to edit categories (of a manga selection) in bulk

    def __init__(self, library):
        self.library = library
        self.listbox = self.library.categories_listbox
        self.stack = self.library.categories_stack
        self.edit_mode_buttonbox = self.library.categories_edit_mode_buttonbox

        self.listbox.connect('row-activated', self.on_category_activated)
        self.library.categories_edit_mode_ok_button.connect('clicked', self.on_edit_mode_ok_button_clicked)
        self.library.categories_edit_mode_cancel_button.connect('clicked', self.on_edit_mode_cancel_button_clicked)

    def clear(self):
        row = self.listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            self.listbox.remove(row)
            row = next_row

    def on_category_activated(self, _listbox, row):
        if self.edit_mode:
            return

        Settings.get_default().selected_category = row.category.id if isinstance(row.category, Category) else row.category

        self.listbox.unselect_all()
        self.listbox.select_row(row)

        self.library.update_title()
        self.library.flowbox.invalidate_filter()

    def on_edit_mode_cancel_button_clicked(self, _button):
        self.library.flap.set_reveal_flap(False)

    def on_edit_mode_ok_button_clicked(self, _button):
        def run():
            insert_data = []
            delete_data = []

            # List of selected manga
            manga_ids = []
            for thumbnail in self.library.flowbox.get_selected_children():
                manga_ids.append(thumbnail.manga.id)

            for row in self.listbox:
                if row.get_activatable_widget().get_active():
                    if Settings.get_default().selected_category == row.category.id:
                        # No insert, we are sure that category is already associated with all selected manga
                        continue

                    associated_manga_ids = row.category.mangas
                    for manga_id in manga_ids:
                        if manga_id in associated_manga_ids:
                            # No insert, category is already associated with this manga
                            continue

                        insert_data.append(dict(
                            manga_id=manga_id,
                            category_id=row.category.id,
                        ))
                elif Settings.get_default().selected_category == row.category.id:
                    for manga_id in manga_ids:
                        delete_data.append(dict(
                            manga_id=manga_id,
                            category_id=row.category.id,
                        ))

            db_conn = create_db_connection()
            with db_conn:
                if insert_data:
                    insert_rows(db_conn, 'categories_mangas_association', insert_data)
                if delete_data:
                    delete_rows(db_conn, 'categories_mangas_association', delete_data)

            db_conn.close()

            GLib.idle_add(complete)

        def complete():
            self.library.window.activity_indicator.stop()

            # Leave library section mode and refresh library
            self.library.leave_selection_mode()
            self.library.populate()

        self.library.window.activity_indicator.start()

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def populate(self):
        db_conn = create_db_connection()
        categories = db_conn.execute('SELECT * FROM categories ORDER BY label ASC').fetchall()
        nb_categorized = db_conn.execute('SELECT count(*) FROM categories_mangas_association').fetchone()[0]
        db_conn.close()

        if not categories and self.edit_mode:
            return

        self.clear()

        self.edit_mode_buttonbox.set_visible(self.edit_mode)

        if categories:
            self.stack.set_visible_child_name('list')

            items = ['all'] + categories
            if nb_categorized > 0:
                items += ['uncategorized']

            for item in items:
                if item == 'all':
                    if self.edit_mode:
                        continue

                    category = 0
                    label = _('All')
                elif item == 'uncategorized':
                    if self.edit_mode:
                        continue

                    category = -1
                    label = _('Uncategorized')
                else:
                    category = Category.get(item['id'])
                    label = category.label

                row = Adw.ActionRow(activatable=True)
                row.category = category
                row.set_title(label)

                if (isinstance(category, Category) and Settings.get_default().selected_category == category.id) or \
                        (isinstance(category, int) and Settings.get_default().selected_category == category):
                    self.listbox.select_row(row)

                if self.edit_mode:
                    switch = Gtk.Switch()
                    switch.set_active(Settings.get_default().selected_category == category.id)
                    switch.set_valign(Gtk.Align.CENTER)
                    row.set_activatable_widget(switch)
                    row.add_suffix(switch)

                self.listbox.append(row)
        else:
            Settings.get_default().selected_category = CategoryVirtual.ALL
            self.stack.set_visible_child_name('empty')

    def set_edit_mode(self, edit_mode):
        self.edit_mode = edit_mode
