# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gi.repository import GLib
from gi.repository import Gtk


class Controls:
    active = False
    is_visible = False
    pages_count = 0
    reader = None

    def __init__(self, reader):
        self.reader = reader
        self.window = reader.window

        self.bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, visible=False)
        self.bottom_box.props.margin_end = 12
        self.bottom_box.props.margin_bottom = 12
        self.bottom_box.props.margin_start = 12
        self.bottom_box.add_css_class('toolbar')
        self.bottom_box.add_css_class('osd')
        self.bottom_box.set_valign(Gtk.Align.END)

        # Number of pages
        self.label = Gtk.Label()
        self.label.add_css_class('monospace')
        self.label.props.margin_start = 6
        self.label.props.margin_end = 6
        self.label.set_halign(Gtk.Align.START)
        self.bottom_box.append(self.label)

        # Chapter's pages slider: current / nb
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 2, 1)
        self.scale.set_hexpand(True)
        self.scale.set_increments(1, 0)  # Disable scrolling with mouse wheel
        self.scale_handler_id = self.scale.connect('change-value', self.on_scale_value_changed)
        self.scale_timeout_id = None

        self.bottom_box.append(self.scale)
        self.reader.overlay.add_overlay(self.bottom_box)

    def hide(self):
        self.is_visible = False
        if self.window.is_fullscreen():
            self.window.headerbar_revealer.set_reveal_child(False)
        self.bottom_box.set_visible(False)

    def init(self, chapter):
        self.active = chapter.pages is not None
        if not self.active:
            return

        self.pages_count = len(chapter.pages)

        # Set slider range
        with self.scale.handler_block(self.scale_handler_id):
            self.scale.set_range(1, self.pages_count)

    def on_fullscreen(self):
        self.window.headerbar_revealer.set_reveal_child(self.is_visible)

    def on_scale_value_changed(self, _scale, scroll_type, value):
        if self.scale_timeout_id:
            GLib.source_remove(self.scale_timeout_id)
            self.scale_timeout_id = None

        def goto_page(index):
            self.reader.pager.goto_page(index)
            self.scale_timeout_id = None

        value = round(value)
        if scroll_type == Gtk.ScrollType.JUMP and value > 0:
            # Schedule event
            self.scale_timeout_id = GLib.timeout_add(250, goto_page, value - 1)

    def on_unfullscreen(self):
        self.window.headerbar_revealer.set_reveal_child(True)

    def set_scale_value(self, index):
        if not self.active:
            return

        with self.scale.handler_block(self.scale_handler_id):
            self.scale.set_value(index)
            self.label.set_text(f'{index}/{self.pages_count}')

    def set_scale_direction(self, inverted):
        self.scale.set_inverted(inverted)
        self.scale.set_value_pos(Gtk.PositionType.RIGHT if inverted else Gtk.PositionType.LEFT)
        if inverted:
            self.bottom_box.reorder_child_after(self.scale, self.label)
        else:
            self.bottom_box.reorder_child_after(self.label, self.scale)

    def show(self):
        if not self.active:
            return

        self.is_visible = True

        if self.window.is_fullscreen():
            self.window.headerbar_revealer.set_reveal_child(True)

        self.bottom_box.set_visible(True)
