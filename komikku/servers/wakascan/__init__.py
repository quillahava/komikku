# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara

#
# BEWARE: Wakascan server is disabled
# Replaced by an anim site since 01/17/2021
#


class Wakascan(Madara):
    id = 'wakascan'
    name = 'Wakascan'
    lang = 'fr'
    status = 'disabled'

    base_url = 'https://wakascan.com'
