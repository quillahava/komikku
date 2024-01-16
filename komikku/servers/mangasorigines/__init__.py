# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Mangasorigines(Madara):
    id = 'mangasorigines'
    name = 'Mangas Origines'
    lang = 'fr'
    is_nsfw = True

    base_url = 'https://mangas-origines.xyz'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
    chapter_url = base_url + '/manga/{0}/{1}/'
    bypass_cf_url = base_url + '/manga/sakamoto-days/'

    details_synopsis_selector = '.manga-excerpt'
