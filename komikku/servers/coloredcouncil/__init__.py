# Copyright (C) 2021-2023 Mariusz Kurek
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Mariusz Kurek <mariuszkurek@pm.me>

from komikku.servers.multi.madara import Madara


class Coloredcouncil(Madara):
    id = 'coloredcouncil'
    name = 'Colored Manga'
    lang = 'en'

    series_name = 'mangas'
    date_format = '%d-%b'

    base_url = 'https://coloredmanga.com'
