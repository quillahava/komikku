# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.pizzareader import PizzaReader


class Lupiteam(PizzaReader):
    id = 'lupiteam'
    name = 'LupiTeam'
    lang = 'it'

    base_url = 'https://lupiteam.net'
