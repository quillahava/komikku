# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.foolslide import FoOlSlide

#
# BEWARE: Kirei Cake server is disabled
# Dead since 11/2022
# Migrate as MangaDex group: https://mangadex.org/group/5fa94491-6f6f-4d53-b8ff-4a4967ac40b5/kirei-cake?tab=feed
#


class Kireicake(FoOlSlide):
    id = 'kireicake'
    name = 'Kirei Cake'
    lang = 'en'
    status = 'disabled'

    base_url = 'https://reader.kireicake.com'
    search_url = base_url + '/search'
    mangas_url = base_url + '/directory'
    manga_url = base_url + '/series/{0}'
    chapter_url = base_url + '/read/{0}/en/{1}/page/1'
