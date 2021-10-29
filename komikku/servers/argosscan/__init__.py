# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara

# BEWARE: Argosscan server is disabled
# Don't use Madara multi-server anymore


class Argosscan(Madara):
    id = 'argosscan'
    name = 'Argos Scan'
    lang = 'pt'
    status = 'disabled'

    base_url = 'https://argosscan.com'
