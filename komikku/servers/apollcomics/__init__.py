# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Apollcomics(Madara):
    id = 'apollcomics'
    name = 'Apoll Comics'
    lang = 'es'
    is_nsfw = True

    base_url = 'https://apollcomics.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
