# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.my_manga_reader_cms import MyMangaReaderCMS


class Jpmangas(MyMangaReaderCMS):
    id = 'jpmangas'
    name = 'Jpmangas'
    lang = 'fr'
    is_nsfw = True

    base_url = 'https://jpmangas.xyz'
    search_url = base_url + '/search'
    most_populars_url = base_url + '/filterList?page=1&cat=&alpha=&sortBy=views&asc=false&author=&tag=&artist='
    manga_url = base_url + '/manga/{0}'
    chapter_url = base_url + '/manga/{0}/{1}'
    image_url = None  # Not predictable, for ex. chapter slug can be formatted `42` or `0042`
    cover_url = base_url + '/uploads/manga/{0}/cover/cover_250x350.jpg'
