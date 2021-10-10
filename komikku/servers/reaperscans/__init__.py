# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.genkan import GenkanInitial
from komikku.servers.multi.madara import Madara
from komikku.servers.multi.manga_stream import MangaStream


class Reaperscans(Madara):
    id = 'reaperscans'
    name = 'Reaper Scans'
    lang = 'en'

    series_name = 'series'

    base_url = 'https://reaperscans.com'


class Reaperscans_fr(MangaStream):
    id = 'reaperscans_fr'
    name = 'Reaper Scans'
    lang = 'fr'

    info_selector = '.main-info'

    base_url = 'https://reaperscans.fr'
    search_url = base_url + '/manga/'
    manga_url = base_url + '/manga/{0}/'
    chapter_url = base_url + '/{0}-{1}/'


class Reaperscans_pt(Madara):
    id = 'reaperscans_pt'
    name = 'Reaper Scans'
    lang = 'pt'

    date_format = '%d/%m/%Y'
    series_name = 'obra'

    base_url = 'https://reaperscans.com.br'


class Reaperscans__old(GenkanInitial):
    id = 'reaperscans__old'
    name = 'Reaper Scans'
    lang = 'en'
    status = 'disabled'

    # Use Cloudflare
    # Search is partially broken -> inherit from GenkanInitial instead of Genkan class

    base_url = 'https://reaperscans.com'
    search_url = base_url + '/comics'
    most_populars_url = base_url + '/home'
    manga_url = base_url + '/comics/{0}'
    chapter_url = base_url + '/comics/{0}/{1}'
    image_url = base_url + '{0}'
