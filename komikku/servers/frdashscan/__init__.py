# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Frdashscan(Madara):
    id = 'frdashscan'
    name = 'Fr-Scan'
    lang = 'fr'
    is_nsfw = True

    date_format = None

    base_url = 'https://fr-scan.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
