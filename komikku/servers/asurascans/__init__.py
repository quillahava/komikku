# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Asurascans(MangaStream):
    id = 'asurascans'
    name = 'Asura Scans'
    lang = 'en'

    base_url = 'https://asura.gg'

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

    authors_selector = '.infox .fmed:-soup-contains("Yazar") span, .infox .fmed:-soup-contains("Çizer") span'
    genres_selector = '.infox .mgen a'
    scanlators_selector = '.infox .fmed:-soup-contains("Seri Yayını") span'
    status_selector = '.tsinfo .imptdt:-soup-contains("Durum") i'
    synopsis_selector = '.summary__content, [itemprop="description"]'  # 2 selectors exist at least

    ignored_chapters_keywords = ['tanitim', ]
    ignored_pages = ['page100-10.jpg', 'zzzzzzz999999.jpg', ]
