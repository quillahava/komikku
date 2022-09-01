# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Phoenixfansub(MangaStream):
    id = 'phoenixfansub'
    name = 'Phoenix Fansub'
    lang = 'es'

    base_url = 'https://phoenixfansub.com'
    search_url = base_url + '/manga/'
    manga_url = base_url + '/manga/{0}/'
    chapter_url = base_url + '/{1}/'  # manga slug is not used

    name_selector = '.entry-title'
    thumbnail_selector = '.thumb img'
    authors_selector = '.tsinfo.bixbox .imptdt:-soup-contains("Artist") i, .tsinfo.bixbox .imptdt:-soup-contains("Author") i'
    genres_selector = '.info-right .mgen a'
    scanlators_selector = '.tsinfo.bixbox .imptdt:-soup-contains("Serialization") i'
    status_selector = '.tsinfo.bixbox .imptdt:-soup-contains("Status") i'
    synopsis_selector = '[itemprop="description"] p'
