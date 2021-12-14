# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Rawmanga(MangaStream):
    id = 'rawmanga'
    name = 'Raw Manga 生漫画'
    lang = 'ja'

    base_url = 'https://mangaraw.org'
    search_url = base_url + '/ajax/search'
    manga_url = base_url + '/{0}'
    chapter_url = base_url + '/{0}/{1}'
    page_url = base_url + '/viewer/{0}/{1}/{2}'

    name_selector = '.infox h1'
    thumbnail_selector = '.thumb img'
    authors_selector = '.infox span:contains("Author")'
    genres_selector = '.infox span:contains("Genres") a'
    scanlators_selector = '.infox span:contains("Serialization")'
    status_selector = '.infox span:contains("Status")'
    synopsis_selector = '[itemprop="articleBody"]'

    search_query_param = 'q'
