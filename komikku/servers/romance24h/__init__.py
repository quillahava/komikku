# -*- coding: utf-8 -*-

# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Romance24h(Madara):
    id = 'romance24h'
    name = '24hRomance'
    lang = 'en'
    status = 'disabled'

    base_url = 'https://24hromance.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
