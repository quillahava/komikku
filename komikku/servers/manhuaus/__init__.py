# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Manhuaus(Madara):
    id = 'manhuaus'
    name = 'Manhuaus'
    lang = 'en'
    is_nsfw = True

    base_url = 'https://manhuaus.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
