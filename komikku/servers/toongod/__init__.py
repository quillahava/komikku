# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara2


class Toongod(Madara2):
    id = 'toongod'
    name = 'ToonGod'
    lang = 'en'
    is_nsfw_only = True

    has_cf = True

    date_format = '%d %b %Y'
    series_name = 'webtoon'

    base_url = 'https://www.toongod.org'
