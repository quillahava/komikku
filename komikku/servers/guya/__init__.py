# -*- coding: utf-8 -*-

# Copyright (C) 2021 Mariusz Kurek
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Mariusz Kurek <mariuszkurek@pm.me>

from komikku.servers import SERVERS_PATH
if SERVERS_PATH:
    # External module
    import multi.guya as multi_guya
else:
    import komikku.servers.multi.guya as multi_guya


class Guya(multi_guya.Guya):
    id = 'guya'
    name = 'Guya'
    lang = 'en'
    base_url = 'https://guya.moe'
    manga_url = base_url + '/read/manga/{0}/'
    api_manga_url = base_url + '/api/series/{0}/'
    api_page_url = base_url + '/media/manga/{0}/chapters/{1}/{2}'
