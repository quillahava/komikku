# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Mangalek(Madara):
    id = 'mangalek'
    name = 'مانجا ليك Mangalek'
    lang = 'ar'

    date_format = '%Y ,%d %B'

    base_url = 'https://mangaleku.com'
    chapter_url = base_url + '/manga/{0}/{1}/'
