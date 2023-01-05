# -*- coding: utf-8 -*-

# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Manga3asq(Madara):
    id = 'manga3asq'
    name = 'مانجا العاشق'
    lang = 'ar'

    date_format = '%Y \u060c%B %-d'

    base_url = 'https://3asq.org'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
    chapter_url = base_url + '/manga/{0}/{1}/'
