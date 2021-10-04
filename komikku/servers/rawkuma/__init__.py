# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
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
    chapter_url = base_url + '/{0}-chapter-{1}/'
