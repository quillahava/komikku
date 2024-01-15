# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Mangascantrad(Madara):
    id = 'mangascantrad'
    name = 'Manga-Scantrad'
    lang = 'fr'
    is_nsfw = True

    has_cf = True

    date_format = None

    base_url = 'https://manga-scantrad.io'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
    bypass_cf_url = base_url + '/manga/tales-of-demons-and-gods-scan-fr/'
