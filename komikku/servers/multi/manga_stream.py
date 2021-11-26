# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Manga Strean – WordPress Theme for read manga

# Supported servers:
# Asura Scans [EN]
# Asura Scans [TR]
# Phoenix Fansub [ES]
# Rawkuma [JA]
# Raw Manga [JA] (v1)
# Reaper Scans [FR]

from bs4 import BeautifulSoup
from gettext import gettext as _
import json
import os
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
    page_url: str

    info_selector = '.bixbox.animefull'
    details_selector = '.wd-full, .fmed'
    genres_selector = None
    status_selector = '.imptdt:first-child i'
    synopsis_selector = 'div[itemprop="description"]'

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
    search_query_param = 's'

    def __init__(self):
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

        info_element = soup.select_one(self.info_selector)

        # Name & cover
        thumb_element = info_element.find('div', class_='thumb')
        data['name'] = thumb_element.img.get('alt').strip()
        data['cover'] = thumb_element.img.get('src')

        # Details
        def compute_status(label):
            label = label.strip().lower()

            if label in ('ongoing', 'devam ediyor'):
                return 'ongoing'
            if label in ('completed', 'tamamlandı'):
                return 'complete'
            if label in ('hiatus', 'bırakıldı'):
                return 'hiatus'
            elif label in ('dropped', 'durduruldu'):
                return 'suspended'

            return None

        for element in info_element.select(self.details_selector):
            if element.b:
                label = element.b.text.strip()
                element.b.extract()
            elif element.name == 'tr':
                label = element.find_all('td')[0].text.strip()
                element = element.find_all('td')[1]
            else:
                continue

            if label.startswith(('Author', 'Artist', 'Yazar')):
                for author in element.text.strip().split(','):
                    author = author.strip()
                    if author != '-' and author not in data['authors']:
                        data['authors'].append(author)

            elif label.startswith(('Genres', 'Serinin Bulunduğu Kategoriler')):
                for a_element in element.find_all('a'):
                    data['genres'].append(a_element.text.strip())

            elif label.startswith(('Status',)):
                data['status'] = compute_status(element.text)

        if self.status_selector:
            status_element = info_element.select_one(self.status_selector)
            if status_element:
                data['status'] = compute_status(status_element.text)

        if self.genres_selector:
            genres_element = info_element.select_one(self.genres_selector)
            for a_element in genres_element:
                data['genres'].append(a_element.text.strip())

        synopsis_element = info_element.select_one(self.synopsis_selector)
        if synopsis_element:
            data['synopsis'] = synopsis_element.text.strip()

        # Chapters
        if container_element := soup.find('div', id='chapterlist'):
            for item in reversed(container_element.find_all('li')):
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
        else:
            # Specific to MangaStream_v1
            for item in reversed(soup.select('.bixbox li')):
                a_element = item.find('a')

                data['chapters'].append(dict(
                    slug=a_element.get('href').split('/')[-1],
                    title=a_element.text.strip(),
                    date=convert_date_string(item.find('time').get('title').split()[0], format='%Y-%m-%d'),
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

        if reader_element := soup.find('div', id='readerarea'):
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
                for img_element in reader_element.find_all('img'):
                    image = img_element.get('src')
                    if image.startswith('data:image'):
                        continue
                    if image.split('/')[-1] in self.ignored_pages:
                        continue

                    data['pages'].append(dict(
                        slug=None,
                        image=image,
                    ))

        elif reader_element := soup.find('div', class_='reader'):
            # Specific to MangaStream_v1
            for option_element in soup.find_all('select', {'name': 'page'})[0].find_all('option'):
                data['pages'].append(dict(
                    slug=option_element.get('value'),
                    image=None,
                ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        headers = {
            'Referer': self.chapter_url.format(manga_slug, chapter_slug),
        }
        if page['slug']:
            r = self.session_get(self.page_url.format(manga_slug, chapter_slug, page['slug']), headers=headers)
        else:
            r = self.session_get(page['image'], headers=headers)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        if page['slug']:
            name = page['slug']
            if not os.path.splitext(name)[1]:
                # Add extension if missing
                name = '{0}.{1}'.format(name, mime_type.split('/')[-1])
        else:
            name = page['image'].split('/')[-1]

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=name,
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
                type=type if type != 'all' else '',
            )
            data[self.search_query_param] = term

        r = self.session_get(self.search_url, params=data)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)

        results = []
        if mime_type == 'text/html':
            soup = BeautifulSoup(r.text, 'html.parser')

            for element in soup.find_all('div', class_='bsx'):
                a_element = element.a
                results.append(dict(
                    slug=a_element.get('href').split('/')[-2],
                    name=a_element.get('title').strip(),
                ))
        elif mime_type == 'text/plain':
            # Specific to MangaStream_v1
            for item in r.json():
                results.append(dict(
                    slug=item['slug'],
                    name=item['title'],
                ))

        return results


class MangaStream_v1(MangaStream):
    details_selector = 'span'
    status_selector = 'span:contains("Status:")'
    synopsis_selector = 'div[itemprop="articleBody"]'

    search_query_param = 'q'
