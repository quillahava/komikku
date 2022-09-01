# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Asurascans(MangaStream):
    id = 'asurascans'
    name = 'Asura Scans'
    lang = 'en'

    base_url = 'https://www.asurascans.com'
    search_url = base_url + '/manga/'
    manga_url = base_url + '/manga/{0}/'
    chapter_url = base_url + '/{1}/'  # manga slug is not used

    name_selector = '.entry-title'
    thumbnail_selector = '.thumb img'
    authors_selector = '.infox .fmed:-soup-contains("Artist") span, .infox .fmed:-soup-contains("Author") span'
    genres_selector = '.infox .mgen a'
    scanlators_selector = '.infox .fmed:-soup-contains("Serialization") span'
    status_selector = '.tsinfo .imptdt:-soup-contains("Status") i'
    synopsis_selector = '[itemprop="description"]'

    ignored_pages = ['page100-10.jpg', 'zzzzzzz999999.jpg', ]


class Asurascans_tr(MangaStream):
    id = 'asurascans_tr'
    name = 'Asura Scans'
    lang = 'tr'

    base_url = 'https://asurascanstr.com'
    search_url = base_url + '/manga/'
    manga_url = base_url + '/manga/{0}/'
    chapter_url = base_url + '/{1}/'  # manga slug is not used

    name_selector = '.entry-title'
    thumbnail_selector = '.thumb img'
    authors_selector = '.infox .fmed:-soup-contains("Yazar") span'
    genres_selector = '.infox .mgen a'
    scanlators_selector = '.infox .fmed:-soup-contains("Seri Yayını") span'
    status_selector = '.tsinfo .imptdt:-soup-contains("Durum") i'
    synopsis_selector = '.summary__content, [itemprop="description"]'  # 2 selectors exist at least

    ignored_chapters_keywords = ['tanitim', ]
    ignored_pages = ['page100-10.jpg', 'zzzzzzz999999.jpg', ]

    def search(self, term, type, populars=False):
        # Remove novels from results
        return [item for item in super().search(term, type, populars) if 'novel' not in item['name'].lower()]
