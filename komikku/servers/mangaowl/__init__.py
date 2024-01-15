# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Mangaowl(Madara):
    id = 'mangaowl'
    name = 'Mangaowl'
    lang = 'en'
    is_nsfw = True

    series_name = 'manga'  # This value changes regularly!

    base_url = 'https://mangaowl.io'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
