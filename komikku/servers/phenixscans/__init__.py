# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.manga_stream import MangaStream


class Phenixscans(MangaStream):
    id = 'phenixscans'
    name = 'PhenixScans'
    lang = 'fr'

    has_cf = True

    base_url = 'https://phenixscans.fr'

    authors_selector = '.infox .fmed:-soup-contains("Artiste") span, .infox .fmed:-soup-contains("Auteur") span'
    genres_selector = '.infox .mgen a'
    scanlators_selector = '.infox .fmed:-soup-contains("Serialization") span'
    status_selector = '.tsinfo .imptdt:-soup-contains("Statut") i'
    synopsis_selector = '[itemprop="description"]'
