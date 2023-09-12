# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Phoenixfansub(Madara):
    id = 'phoenixfansub'
    name = 'Phoenix Fansub'
    lang = 'es'
    status = 'disabled'  # 2023-09

    base_url = 'https://phoenixmangas.com'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
