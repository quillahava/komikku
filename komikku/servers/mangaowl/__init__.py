# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara2


class Mangaowl(Madara2):
    id = 'mangaowl'
    name = 'Mangaowl'
    lang = 'en'

    series_name = '7xoehy'  # This value changes regularly!

    base_url = 'https://mangaowl.io'
    chapters_url = base_url + '/7xoehy/{0}/ajax/chapters/'
