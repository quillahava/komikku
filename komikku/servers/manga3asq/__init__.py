# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara2


class Manga3asq(Madara2):
    id = 'manga3asq'
    name = 'مانجا العاشق'
    lang = 'ar'

    date_format = '%Y \u060c%B %-d'

    base_url = 'https://3asq.org'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
    chapter_url = base_url + '/manga/{0}/{1}/'

    details_synopsis_selector = '.manga-excerpt'
