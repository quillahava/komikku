# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.foolslide import FoOlSlide

#
# BEWARE: Jaimini's Box server is disabled
# Dead since 07/09/2020
#


class Jaiminisbox__old(FoOlSlide):
    id = 'jaiminisbox__old'
    name = "Jaimini's Box"
    lang = 'en'
    status = 'disabled'

    base_url = 'https://jaiminisbox.com/reader'
    search_url = base_url + '/search'
    mangas_url = base_url + '/directory'
    manga_url = base_url + '/series/{0}'
    chapter_url = base_url + '/read/{0}/en/{1}/page/1'
