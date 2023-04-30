# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Flamescans(MangaStream):
    id = 'flamescans'
    name = 'Flame Scans'
    lang = 'en'

    base_url = 'https://flamescans.org'

    series_name = 'series'

    authors_selector = '.tsinfo .imptdt:-soup-contains("Artist") i, .tsinfo .imptdt:-soup-contains("Author") i'
    genres_selector = '.info-half .mgen a'
    scanlators_selector = '.tsinfo .imptdt:-soup-contains("Serialization") i, .tsinfo .imptdt:-soup-contains("Translation") i'
    status_selector = '.status i'
    synopsis_selector = '[itemprop="description"]'
