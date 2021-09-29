# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Manga Strean – WordPress Theme for read manga

# Supported servers:
# Asura Scans [EN]: https://www.asurascans.com
# Asura Scans [TR]: https://tr.asurascans.com
# Phoenix Fansub [ES]: https://phoenixfansub.com

from bs4 import BeautifulSoup
from gettext import gettext as _
import json
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class MangaStream(Server):
    base_url: str
    search_url: str
    manga_url: str
    chapter_url: str

    filters = [
        {
            'key': 'type',
            'type': 'select',
            'name': _('Type'),
            'description': _('Type of comics to search for'),
            'value_type': 'single',
            'default': 'all',
            'options': [
                {'key': 'all', 'name': _('All')},
                {'key': 'manga', 'name': _('Manga')},
                {'key': 'manhwa', 'name': _('Manhwa')},
                {'key': 'manhua', 'name': _('Manhua')},
                {'key': 'comic', 'name': _('Comic')},
            ],
        },
    ]
    ignored_pages: list = []

    def __init__(self):
        self.search_url = self.base_url + '/manga/'

        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
        ))

        data['name'] = soup.find('h1', class_='entry-title').text.strip()
        data['cover'] = soup.find('div', class_='thumb').img.get('src')

        # Details
        for element in soup.find('div', class_='infox').find_all('div', class_=['fmed', 'wd-full']):
            if not element.b:
                continue

            label = element.b.text.strip()
            if label.startswith(('Author', 'Artist')):
                for author in element.span.text.strip().split(','):
                    author = author.strip()
                    if author != '-' and author not in data['authors']:
                        data['authors'].append(author)

            elif label.startswith(('Genres',)):
                for a_element in element.span.find_all('a'):
                    genre = a_element.text.strip()
                    data['genres'].append(genre)

        status = soup.find('div', class_='tsinfo').div.i.text.strip().lower()
        if status == 'ongoing':
            data['status'] = 'ongoing'
        elif status == 'completed':
            data['status'] = 'complete'
        elif status == 'hiatus':
            data['status'] = 'hiatus'
        elif status == 'dropped':
            data['status'] = 'suspended'

        data['synopsis'] = soup.find('div', itemprop='description').text.strip()

        # Chapters
        for item in reversed(soup.find('div', id='chapterlist').find_all('li')):
            slug = item.get('data-num').replace('.', '-')

            a_element = item.div.div.a
            title = a_element.find('span', class_='chapternum').text.strip()
            if date_element := a_element.find('span', class_='chapterdate'):
                date = convert_date_string(date_element.text.strip(), format='%B %d, %Y')
            else:
                date = None

            data['chapters'].append(dict(
                slug=slug,
                title=title,
                date=date,
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(manga_slug, chapter_slug))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )

        reader_element = soup.find('div', id='readerarea')

        if reader_element.text == '':
            # Pages images are loaded via javascript
            for script_element in soup.find_all('script'):
                script = script_element.string
                if script is None:
                    continue

                for line in script.split('\n'):
                    line = line.strip()
                    if line.startswith('ts_reader'):
                        json_data = json.loads(line[14:-2])
                        for image in json_data['sources'][0]['images']:
                            if image.split('/')[-1] in self.ignored_pages:
                                continue

                            data['pages'].append(dict(
                                slug=None,
                                image=image,
                            ))
        else:
            for p_element in soup.find('div', id='readerarea').find_all('p'):
                image = p_element.img.get('src')
                if image.split('/')[-1] in self.ignored_pages:
                    continue

                data['pages'].append(dict(
                    slug=None,
                    image=image,
                ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            page['image'],
            headers={
                'referer': self.chapter_url.format(manga_slug, chapter_slug),
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=page['image'].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_most_populars(self, type):
        """
        Returns list of most popular manga
        """
        return self.search('', type, True)

    def search(self, term, type, populars=False):
        if populars:
            data = dict(
                order='popular',
                status='',
                type=type if type != 'all' else '',
            )
        else:
            data = dict(
                s=term,
                type=type if type != 'all' else '',
            )

        r = self.session_get(self.search_url, params=data)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for element in soup.find_all('div', class_='bsx'):
            a_element = element.a
            results.append(dict(
                slug=a_element.get('href').split('/')[-2],
                name=a_element.get('title').strip(),
            ))

        return results
