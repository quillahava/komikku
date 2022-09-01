# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Rawkuma(MangaStream):
    id = 'rawkuma'
    name = 'Rawkuma'
    lang = 'ja'

    base_url = 'https://rawkuma.com'
    search_url = base_url + '/manga/'
    manga_url = base_url + '/manga/{0}/'
    chapter_url = base_url + '/{1}/'  # manga slug is not used

    name_selector = '.entry-title'
    thumbnail_selector = '.thumb img'
    authors_selector = '.infox .fmed:-soup-contains("Artist") span, .infox .fmed:-soup-contains("Author") span'
    genres_selector = '.infox .mgen a'
    scanlators_selector = '.infox .fmed:-soup-contains("Serialization") span'
    status_selector = '.tsinfo .imptdt:-soup-contains("Status") i'
    synopsis_selector = '[itemprop="description"] p'
