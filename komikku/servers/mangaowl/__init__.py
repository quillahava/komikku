# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Mangaowl(Madara):
    id = 'mangaowl'
    name = 'Mangaowl'
    lang = 'en'

    series_name = 'taekook'  # This value changes regularly!

    base_url = 'https://mangaowl.io'
    chapters_url = base_url + '/taekook/{0}/ajax/chapters/'
