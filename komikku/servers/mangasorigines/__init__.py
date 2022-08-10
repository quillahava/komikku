# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara2


class Mangasorigines(Madara2):
    id = 'mangasorigines'
    name = 'Mangas Origines'
    lang = 'fr'

    date_format = None
    series_name = 'catalogues'

    base_url = 'https://mangas-origines.fr'
    chapters_url = base_url + '/catalogues/{0}/ajax/chapters/'
