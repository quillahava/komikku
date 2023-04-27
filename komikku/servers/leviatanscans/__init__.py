# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.genkan import Genkan
from komikku.servers.multi.genkan import GenkanInitial
from komikku.servers.multi.madara import Madara2


class Leviatanscans(Madara2):
    id = 'leviatanscans'
    name = 'LeviatanScans'
    lang = 'en'

    base_url = 'https://en.leviatanscans.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'


class Leviatanscans_es(Madara2):
    id = 'leviatanscans_es'
    name = 'Escaneos de Leviatan'
    lang = 'es'

    base_url = 'https://es.leviatanscans.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'


class Leviatanscans__old(Genkan):
    id = 'leviatanscans__old'
    name = 'Leviatan Scans'
    lang = 'en'
    status = 'disabled'  # Switch to Madara (Wordpress)

    base_url = 'https://leviatanscans.com'
    search_url = base_url + '/comics?query={0}'
    most_populars_url = base_url + '/home'
    manga_url = base_url + '/comics/{0}'
    chapter_url = base_url + '/comics/{0}/{1}'
    image_url = base_url + '{0}'


class Leviatanscans_es_old(GenkanInitial):
    id = 'leviatanscans_es_old'
    name = 'Leviatan Scans'
    lang = 'es'
    status = 'disabled'  # Switch to Madara (Wordpress)

    # Search is broken -> inherit from GenkanInitial instead of Genkan class

    base_url = 'https://es.leviatanscans.com'
    search_url = base_url + '/comics'
    most_populars_url = base_url + '/home'
    manga_url = base_url + '/comics/{0}'
    chapter_url = base_url + '/comics/{0}/{1}'
    image_url = base_url + '{0}'
