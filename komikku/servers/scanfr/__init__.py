# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.my_manga_reader_cms import MyMangaReaderCMS


class Scanfr(MyMangaReaderCMS):
    id = 'scanfr'
    name = 'Scan FR'
    lang = 'fr'

    base_url = 'https://www.scan-fr.org'
    search_url = base_url + '/search'
    most_populars_url = base_url + '/filterList?page=1&sortBy=views&asc=false'
    manga_url = base_url + '/manga/{0}'
    chapter_url = base_url + '/manga/{0}/{1}'
    image_url = None  # For some manga chapters, chapter slug can't be used to compute images URLs
    cover_url = 'https://opfrcdn.xyz/uploads/manga/{0}/cover/cover_250x350.jpg'
