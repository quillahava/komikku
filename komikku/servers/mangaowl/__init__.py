# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara2


class Mangaowl(Madara2):
    id = 'mangaowl'
    name = 'Mangaowl'
    lang = 'en'

    series_name = 'read-manga'

    base_url = 'https://mangaowl.io'
    chapters_url = base_url + '/read-manga/{0}/ajax/chapters/'
