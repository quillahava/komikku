# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.explorer.search import ExplorerSearchPage
from komikku.explorer.servers import ExplorerServersPage


class Explorer:
    def __init__(self, window):
        self.window = window

        self.servers_page = ExplorerServersPage(self)
        self.window.navigationview.add(self.servers_page)
        self.search_page = ExplorerSearchPage(self)
        self.window.navigationview.add(self.search_page)

    def show(self, servers=None):
        self.servers_page.show(servers)
