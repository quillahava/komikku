# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara2


class Manhuaus(Madara2):
    id = 'manhuaus'
    name = 'Manhuaus'
    lang = 'en'
    is_nsfw = True

    has_cf = True

    base_url = 'https://manhuaus.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
