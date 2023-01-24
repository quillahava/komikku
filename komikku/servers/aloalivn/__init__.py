# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.madara import Madara


class Aloalivn(Madara):
    id = 'aloalivn'
    name = 'Aloalivn'
    lang = 'en'
    status = 'disabled'

    base_url = 'https://aloalivn.com'
