# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gi.repository import Adw
from gi.repository import GLib
from gi.repository import Gtk

from komikku.models import create_db_connection
from komikku.models import Category
from komikku.models import Settings


class CategoriesList:
    def __init__(self, card):
        self.card = card
        self.window = card.window

        self.stack = self.card.categories_stack
        self.listbox = self.card.categories_listbox

    def clear(self):
        row = self.listbox.get_first_child()
        while row:
            next_row = row.get_next_sibling()
            self.listbox.remove(row)
            row = next_row

    def populate(self):
        self.clear()

        db_conn = create_db_connection()
        records = db_conn.execute('SELECT * FROM categories ORDER BY label ASC').fetchall()
        db_conn.close()

        if records:
            self.stack.set_visible_child_name('list')

            for record in records:
                category = Category.get(record['id'])

                action_row = Adw.ActionRow()
                action_row.set_title(category.label)
                action_row.set_activatable(True)

                switch = Gtk.Switch.new()
                switch.set_valign(Gtk.Align.CENTER)
                switch.set_halign(Gtk.Align.CENTER)
                switch.set_active(category.id in self.card.manga.categories)
                switch.connect('notify::active', self.on_category_activated, category.id)
                action_row.add_suffix(switch)
                action_row.set_activatable_widget(switch)

                self.listbox.append(action_row)
        else:
            self.stack.set_visible_child_name('empty')

    def on_category_activated(self, switch, _param, category_id):
        self.card.manga.toggle_category(category_id, switch.get_active())

        # Update the categories list in Library, just in case it's necessary to show/hide the 'Uncategorized' category
        self.window.library.categories_list.populate()

        # Update Library if the current selected category is the activated category or the 'Uncategorized' category
        if Settings.get_default().selected_category in (-1, category_id):
            GLib.idle_add(self.window.library.populate)
