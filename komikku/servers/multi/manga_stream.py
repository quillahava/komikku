# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Manga Strean – WordPress Theme for read manga

# Supported servers:
# Asura Scans [EN]
# Asura Scans [TR]
# Rawkuma [JA]
# Raw Manga [JA]

from bs4 import BeautifulSoup
from gettext import gettext as _
import json
import os
import re
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import get_soup_element_inner_text
from komikku.webview import bypass_cf


class MangaStream(Server):
    base_url: str
    search_url: str
    manga_url: str
    chapter_url: str
    page_url: str

    name_selector: str
    thumbnail_selector: str
    authors_selector: str
    genres_selector: str
    scanlators_selector: str
    status_selector: str
    synopsis_selector: str

    filters = [
        {
            'key': 'type',
            'type': 'select',
            'name': _('Type'),
            'description': _('Filter by type'),
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

    ignored_chapters_keywords: list = []
    ignored_pages: list = []
    search_query_param = 's'

    def __init__(self):
        if self.session is None and not self.has_cf:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': USER_AGENT})

    @bypass_cf
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

        def compute_status(label):
            if not label:
                return None

            label = label.strip()

            if any(re.findall(r'ongoing|devam ediyor', label, re.IGNORECASE)):
                return 'ongoing'
            if any(re.findall(r'completed|tamamlandı', label, re.IGNORECASE)):
                return 'complete'
            if any(re.findall(r'hiatus|bırakıldı', label, re.IGNORECASE)):
                return 'hiatus'
            if any(re.findall(r'dropped|durduruldu', label, re.IGNORECASE)):
                return 'suspended'

            return None

        # Name & cover
        data['name'] = soup.select_one(self.name_selector).text.strip()
        data['cover'] = soup.select_one(self.thumbnail_selector).get('data-src')
        if not data['cover']:
            data['cover'] = soup.select_one(self.thumbnail_selector).get('src')
            if not data['cover'].startswith('http'):
                data['cover'] = f'https:{data["cover"]}'

        # Details
        data['authors'] = list({get_soup_element_inner_text(element) for element in soup.select(self.authors_selector)})
        data['genres'] = [element.text.strip() for element in soup.select(self.genres_selector)]
        if self.scanlators_selector:
            data['scanlators'] = [get_soup_element_inner_text(soup.select_one(self.scanlators_selector)), ]
        data['status'] = compute_status(get_soup_element_inner_text(soup.select_one(self.status_selector)))
        data['synopsis'] = soup.select_one(self.synopsis_selector).text.strip()

        # Chapters
        if container_element := soup.find('div', id='chapterlist'):
            for item in reversed(container_element.find_all('li')):
                a_element = item.div.div.a

                slug = a_element.get('href').split('/')[-2]
                ignore = False
                for keyword in self.ignored_chapters_keywords:
                    if keyword in slug:
                        ignore = True
                        break
                if ignore:
                    continue

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
            for item in reversed(soup.select('.bixbox li')):
                a_element = item.find('a')

                slug = a_element.get('href').split('/')[-1]
                ignore = False
                for keyword in self.ignored_chapters_keywords:
                    if keyword in slug:
                        ignore = True
                        break
                if ignore:
                    continue

                data['chapters'].append(dict(
                    slug=slug,
                    title=a_element.text.strip(),
                    date=convert_date_string(item.find('time').get('title').split()[0], format='%Y-%m-%d'),
                ))

        return data

    @bypass_cf
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(
            self.chapter_url.format(manga_slug=manga_slug, chapter_slug=chapter_slug),
            headers={
                'Referer': self.manga_url.format(manga_slug),
            })
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
            img_elements = reader_element.find_all('img')
            if not img_elements:
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
                for img_element in img_elements:
                    image = img_element.get('data-src')
                    if not image:
                        image = img_element.get('src')
                        if not image.startswith('http'):
                            image = f'https:{image}'
                    if image.split('/')[-1] in self.ignored_pages:
                        continue

                    data['pages'].append(dict(
                        slug=None,
                        image=image,
                    ))

        elif reader_element := soup.find('div', class_='reader'):
            for option_element in soup.find_all('select', {'name': 'page'})[0].find_all('option'):
                data['pages'].append(dict(
                    slug=option_element.get('value'),
                    image=None,
                ))

        return data

    @bypass_cf
    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        headers = {
            'Referer': self.chapter_url.format(manga_slug=manga_slug, chapter_slug=chapter_slug),
        }
        if page['slug']:
            r = self.session_get(self.page_image_url.format(manga_slug, chapter_slug, page['slug']), headers=headers)
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

    def get_latest_updates(self, type):
        """
        Returns list of latest updates
        """
        return self.search('', type, orderby='latest')

    def get_most_populars(self, type):
        """
        Returns list of most popular manga
        """
        return self.search('', type, orderby='populars')

    @bypass_cf
    def search(self, term, type, orderby=None):
        if orderby:
            data = dict(
                order='popular' if orderby == 'populars' else 'update',
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
                slug = a_element.get('href').split('/')[-2]

                # Hack for asurascans (EN)
                # Some slugs contain additional digits (ex. 11) at start
                # Delete them if they are not present in manga title
                title = a_element.get('title').lower()
                if slug[0] != title[0]:
                    slug = '-'.join(slug.split('-')[1:])

                results.append(dict(
                    slug=slug,
                    name=a_element.get('title').strip(),
                ))
        elif mime_type == 'text/plain':
            for item in r.json():
                results.append(dict(
                    slug=item['slug'],
                    name=item['title'],
                ))

        return results
