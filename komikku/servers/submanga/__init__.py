# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara

# BEWARE: Submanga server is disabled
# Since ~06/2022, submanga.io domain is redirected to https://lectormanga.online (Leomanga server)


class Submanga(Madara):
    id = 'submanga'
    name = 'Submanga'
    lang = 'es'
    status = 'disabled'

    base_url = 'https://submanga.io'
    chapters_url = base_url + '/manga/{0}/ajax/chapters/'
