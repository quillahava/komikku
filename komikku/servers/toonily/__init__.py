# -*- coding: utf-8 -*-

# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Toonily(Madara):
    id = 'toonily'
    name = 'Toonily'
    lang = 'en'

    date_format = None
    series_name = 'webtoon'

    base_url = 'https://toonily.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'

    def search(self, term, orderby=None, medium=None):
        return self._search(term, orderby=orderby, medium=medium)

    def is_long_strip(self, _manga_data):
        return True
