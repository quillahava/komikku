# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Asurascans(MangaStream):
    id = 'asurascans'
    name = 'Asura Scans'
    lang = 'en'

    ignored_pages = ['page100-10.jpg', 'zzzzzzz999999.jpg', ]

    base_url = 'https://www.asurascans.com'
    search_url = base_url + '/manga/'
    manga_url = base_url + '/comics/{0}/'
    chapter_url = base_url + '/{0}-chapter-{1}/'


class Asurascans_tr(MangaStream):
    id = 'asurascans_tr'
    name = 'Asura Scans'
    lang = 'tr'

    ignored_pages = ['page100-10.jpg', 'zzzzzzz999999.jpg', ]

    base_url = 'https://tr.asurascans.com'
    search_url = base_url + '/manga/'
    manga_url = base_url + '/manga/{0}/'
    chapter_url = base_url + '/{0}-bolum-{1}/'
