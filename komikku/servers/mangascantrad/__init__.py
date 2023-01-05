# -*- coding: utf-8 -*-

# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Mangascantrad(Madara):
    id = 'mangascantrad'
    name = 'Manga-Scantrad'
    lang = 'fr'

    date_format = None

    base_url = 'https://manga-scantrad.net'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
