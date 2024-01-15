# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.pizzareader import PizzaReader


class Gtotgs(PizzaReader):
    id = 'gtotgs'
    name = 'GTO TGS'
    lang = 'it'
    is_nsfw = True

    base_url = 'https://reader.gtothegreatsite.net'
