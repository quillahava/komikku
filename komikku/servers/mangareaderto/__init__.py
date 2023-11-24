# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.mangareader import Mangareader


class Mangareaderto(Mangareader):
    id = 'mangareaderto'
    name = 'MangaReader'
    lang = 'en'
    is_nsfw = True

    languages_codes = dict(
        en='en',
        fr='fr',
        ja='ja',
        ko='ko',
        zh_Hans='zh',
    )

    base_url = 'https://mangareader.to'
    list_url = base_url + '/filter'
    search_url = base_url + '/search'
    manga_url = base_url + '/{0}'
    chapter_url = base_url + '/read/{0}/{1}/{2}'
    api_chapter_images_url = base_url + '/ajax/image/list/chap/{0}?mode=vertical&quality=medium&hozPageSize=1'


class Mangareaderto_fr(Mangareaderto):
    id = 'mangareaderto_fr'
    lang = 'fr'


class Mangareaderto_ja(Mangareaderto):
    id = 'mangareaderto_ja'
    lang = 'ja'


class Mangareaderto_ko(Mangareaderto):
    id = 'mangareaderto_ko'
    lang = 'ko'


class Mangareaderto_zh_hans(Mangareaderto):
    id = 'mangareaderto_ko'
    lang = 'zh_Hans'
