# -*- coding: utf-8 -*-

# Copyright (C) 2021 Mariusz Kurek
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Mariusz Kurek <mariuszkurek@pm.me>

from komikku.servers.multi.madara import Madara


class Coloredcouncil(Madara):
    id = 'coloredcouncil'
    name = 'Colored Council'
    lang = 'en'

    base_url = 'https://coloredmanga.com/'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
