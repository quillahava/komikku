# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gi.repository import Gtk


class ActivityIndicator(Gtk.Box):
    def __init__(self):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)

        self.props.can_target = False

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(50, 50)

        self.append(self.spinner)

    def stop(self):
        self.spinner.stop()

    def start(self):
        self.spinner.start()
