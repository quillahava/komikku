# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Manhwahentai(Madara):
    id = 'manhwahentai'
    name = 'Manhwa Hentai'
    lang = 'en'
    is_nsfw_only = True

    date_format = '%d %B %Y'
    series_name = 'pornhwa'

    base_url = 'https://manhwahentai.to'
    chapters_url = base_url + '/pornhwa/{0}/ajax/chapters/'
