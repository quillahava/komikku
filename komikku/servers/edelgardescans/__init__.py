# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.genkan import Genkan


class Edelgardescans(Genkan):
    id = 'edelgardescans'
    name = 'Edelgarde Scans'
    lang = 'en'
    status = 'disabled'

    base_url = 'https://edelgardescans.com'
    search_url = base_url + '/comics?query={0}'
    most_populars_url = base_url + '/home'
    manga_url = base_url + '/comics/{0}'
    chapter_url = base_url + '/comics/{0}/{1}'
    image_url = base_url + '{0}'
