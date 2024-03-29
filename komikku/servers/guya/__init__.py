# Copyright (C) 2021-2024 Lili Kurek
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Lili Kurek <lilikurek@proton.me>

import komikku.servers.multi.guya


class Guya(komikku.servers.multi.guya.Guya):
    id = 'guya'
    name = 'Guya.moe'
    lang = 'en'
    base_url = 'https://guya.cubari.moe'
    manga_url = base_url + '/read/manga/{0}/'
    api_manga_url = base_url + '/api/series/{0}/'
    page_image_url = base_url + '/media/manga/{0}/chapters/{1}/{2}'
