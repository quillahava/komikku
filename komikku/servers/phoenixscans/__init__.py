# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.pizzareader import PizzaReader


class Phoenixscans(PizzaReader):
    id = 'phoenixscans'
    name = 'Phoenix Scans'
    lang = 'it'

    base_url = 'https://www.phoenixscans.com'
