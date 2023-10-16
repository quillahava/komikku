# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from komikku.servers.multi.heancms import Heancms


class Perfscan(Heancms):
    id = 'perfscan'
    name = 'Perf Scan'
    lang = 'fr'

    base_url = 'https://perf-scan.fr'
    api_url = 'https://api.perf-scan.fr'

    cover_css_path = 'div div div.container.px-5.text-gray-50 div.grid.grid-cols-12.pt-3.gap-x-3 div.col-span-12.relative.flex.justify-center.w-full div.flex.flex-col.items-center.justify-center.gap-y-2.w-full img'
    authors_css_path = 'div div.container.px-5.text-gray-50 div.grid.grid-cols-12.pt-3.gap-x-3 div.col-span-12.flex.flex-col.gap-y-3 div div.flex.flex-col.gap-y-2 p:nth-child(3) strong'
    synopsis_css_path = 'div div.container.px-5.text-gray-50 div.grid.grid-cols-12.pt-3.gap-x-3 div.col-span-12.flex.flex-col.gap-y-3 div.bg-gray-800.text-gray-50.rounded-xl.p-5'

    def check_slug(self, initial_data):
        # A random number is always added to slug and it changes regulary
        # Try to retrieve new slug.
        res = self.search(initial_data['name'])
        if not res:
            return None

        for item in res:
            base_slug = '-'.join(initial_data['slug'].split('-')[:-1])
            current_base_slug = '-'.join(item['slug'].split('-')[:-1])
            if current_base_slug == base_slug and initial_data['slug'] != item['slug']:
                return item['slug']

    def get_manga_data(self, initial_data):
        if new_slug := self.check_slug(initial_data):
            initial_data['slug'] = new_slug

        return Heancms.get_manga_data(self, initial_data)
