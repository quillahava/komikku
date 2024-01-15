# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Toonily(Madara):
    id = 'toonily'
    name = 'Toonily'
    lang = 'en'
    is_nsfw = True

    base_url = 'https://toonily.com'

    date_format = '%b %-d, %y'
    medium = None
    series_name = 'webtoon'

    results_selector = '.manga'
    result_name_slug_selector = '.post-title a'
    result_cover_selector = '.item-thumb img'

    def is_long_strip(self, _manga_data):
        return True
