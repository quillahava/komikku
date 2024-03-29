# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Rawkuma(MangaStream):
    id = 'rawkuma'
    name = 'Rawkuma'
    lang = 'ja'
    is_nsfw = True

    base_url = 'https://rawkuma.com'

    authors_selector = '.infox .fmed:-soup-contains("Artist") span, .infox .fmed:-soup-contains("Author") span'
    genres_selector = '.infox .mgen a'
    scanlators_selector = '.infox .fmed:-soup-contains("Serialization") span'
    status_selector = '.tsinfo .imptdt:-soup-contains("Status") i'
    synopsis_selector = '[itemprop="description"] p'
