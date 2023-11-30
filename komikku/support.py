# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import logging

from gi.repository import Adw
from gi.repository import Gtk

logger = logging.getLogger('komikku.support')


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/support.ui')
class SupportPage(Adw.NavigationPage):
    __gtype_name__ = 'SupportPage'

    title_box = Gtk.Template.Child('title_box')
    liberapay_button = Gtk.Template.Child('liberapay_button')
    paypal_button = Gtk.Template.Child('paypal_button')
    kofi_button = Gtk.Template.Child('kofi_button')

    payment_methods = {
        'liberapay': 'https://liberapay.com/valos/donate',
        'paypal': 'https://www.paypal.com/donate?business=GSRGEQ78V97PU&no_recurring=0&item_name=You+can+help+me+to+keep+developing+apps+through+donations.&currency_code=EUR',
        'ko-fi': 'https://ko-fi.com/X8X06EM3L',
    }

    def __init__(self, window):
        Adw.NavigationPage.__init__(self)

        self.window = window

        self.window.breakpoint.add_setter(self.title_box, 'orientation', Gtk.Orientation.VERTICAL)
        self.window.navigationview.add(self)

        self.liberapay_button.connect('clicked', self.on_button_clicked, 'liberapay')
        self.paypal_button.connect('clicked', self.on_button_clicked, 'paypal')
        self.kofi_button.connect('clicked', self.on_button_clicked, 'ko-fi')

    def on_button_clicked(self, button, method):
        if uri := self.payment_methods.get(method):
            Gtk.UriLauncher.new(uri=uri).launch()

    def show(self):
        self.window.navigationview.push(self)
