# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import json

from komikku.servers.multi.my_manga_reader_cms import MyMangaReaderCMS
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Mangasin(MyMangaReaderCMS):
    id = 'mangasin'
    name = 'Mangas.in (Mangas.pw)'
    lang = 'es'

    search_query_param = 'q'

    base_url = 'https://mangas.in'
    search_url = base_url + '/search'
    most_populars_url = base_url + '/filterList?page=1&cat=&alpha=&sortBy=views&asc=false&author=&tag=&artist='
    manga_url = base_url + '/manga/{0}'
    chapter_url = base_url + '/manga/{0}/{1}'
    image_url = None  # Images URLs can't be computed with manga/chapter/image slugs
    cover_url = base_url + '/uploads/manga/{0}/cover/cover_250x350.jpg'

    def get_manga_chapters_data(self, soup):
        rnd_var = None
        data = None
        for script_element in reversed(soup.find_all('script')):
            script = script_element.string
            if script is None:
                continue

            for line in reversed(script.split('\n')):
                line = line.strip()
                if rnd_var is None:
                    if line.startswith('newChapterList ='):
                        rnd_var = line.split('(')[-1].split(',')[0]
                        break

                elif line.startswith(f'var {rnd_var} ='):
                    data = json.loads(line[len(rnd_var) + 6:-1])
                    break

            if id is not None and data is not None:
                break

        if data is None:
            return []

        chapters = []
        for chapter in reversed(data):
            chapters.append(dict(
                slug=chapter['slug'],
                title=chapter['name'],
                date=convert_date_string(chapter['updated_at'].split()[0], format='%Y-%m-%d'),
            ))

        return chapters

    def get_latest_updates(self):
        """
        Returns list of latest updated manga
        """
        r = self.session_get(
            self.base_url,
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for a_element in soup.select('.mangalist .manga-item h3 a:nth-child(3)'):
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
            ))

        return results
