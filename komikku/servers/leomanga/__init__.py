# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Leomanga(Madara):
    id = 'leomanga'
    name = 'Lector Manga (Leomanga)'
    lang = 'es'
    is_nsfw = True

    base_url = 'https://lectormanga.fun'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
