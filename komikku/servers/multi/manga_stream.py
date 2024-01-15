# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Manga Strean/Manga Reader – WordPress Themes for read manga

# Supported servers:
# Asura Scans [EN]
# Asura Scans [TR]
# Flam Scans [EN]
# PhenixScans [FR]
# Rawkuma [JA]
# Raw Manga [JA]

from bs4 import BeautifulSoup
from gettext import gettext as _
import json
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
    api_url: str = None
    manga_list_url: str = None
    manga_url: str = None
    chapter_url: str = None

    date_format: str = '%B %d, %Y'
    series_name: str = 'manga'

    name_selector: str = '.entry-title'
    thumbnail_selector: str = '.thumb img'
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
            'default': '',
            'options': [
                {'key': '', 'name': _('All')},
                {'key': 'manga', 'name': _('Manga')},
                {'key': 'manhwa', 'name': _('Manhwa')},
                {'key': 'manhua', 'name': _('Manhua')},
                {'key': 'comic', 'name': _('Comic')},
            ],
        },
    ]

    ignored_chapters_keywords: list = []
    ignored_pages: list = []

    def __init__(self):
        if self.api_url is None:
            self.api_url = self.base_url + '/wp-admin/admin-ajax.php'

        if self.manga_list_url is None:
            self.manga_list_url = self.base_url + '/' + self.series_name + '/?status=&type={0}&order={1}'

        if self.manga_url is None:
            self.manga_url = self.base_url + '/manga/{0}/'

        if self.chapter_url is None:
            self.chapter_url = self.base_url + '/{chapter_slug}/'

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

            # Ongoing
            labels = (
                'ongoing',
                'coming soon',
                'mass released',
                'daily release',
                'en cours',  # fr
                'devam ediyor',  # tr
            )
            if any(re.findall('|'.join(labels), label, re.IGNORECASE)):
                return 'ongoing'

            # Complete
            labels = (
                'completed',
                'fini',  # fr
                'tamamlandı',  # tr
            )
            if any(re.findall('|'.join(labels), label, re.IGNORECASE)):
                return 'complete'

            # Hiatus
            labels = (
                'hiatus',
                'en pause',  # fr
                'bırakıldı',  # tr
            )
            if any(re.findall('|'.join(labels), label, re.IGNORECASE)):
                return 'hiatus'

            # Suspended
            labels = (
                'cancelled',
                'dropped',
                'durduruldu',  # tr
            )
            if any(re.findall('|'.join(labels), label, re.IGNORECASE)):
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
        if self.authors_selector:
            if elements := soup.select(self.authors_selector):
                for element in elements:
                    author = get_soup_element_inner_text(element)
                    if author not in data['authors']:
                        data['authors'].append(author)
        if self.genres_selector:
            if elements := soup.select(self.genres_selector):
                data['genres'] = [element.text.strip() for element in elements]
        if self.scanlators_selector:
            if elements := soup.select(self.scanlators_selector):
                data['scanlators'] = [get_soup_element_inner_text(element) for element in elements]
        if self.status_selector:
            if element := soup.select_one(self.status_selector):
                data['status'] = compute_status(get_soup_element_inner_text(element))
        if self.synopsis_selector:
            if element := soup.select_one(self.synopsis_selector):
                data['synopsis'] = element.text.strip()

        # Chapters
        data['chapters'] = self.get_manga_chapters_data(soup)

        return data

    def get_manga_chapters_data(self, soup):
        chapters = []

        for li_element in reversed(soup.select('#chapterlist ul li')):
            a_element = li_element.select_one('a')

            slug = a_element.get('href').split('/')[-2]
            ignore = False
            for keyword in self.ignored_chapters_keywords:
                if keyword in slug:
                    ignore = True
                    break
            if ignore:
                continue

            title = li_element.select_one('.chapternum').text.strip().replace('\n', ' ')
            if date_element := li_element.select_one('.chapterdate'):
                date = convert_date_string(date_element.text.strip(), format=self.date_format)
            else:
                date = None

            chapters.append(dict(
                slug=slug,
                title=title,
                date=date,
            ))

        return chapters

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

        img_elements = soup.find('div', id='readerarea').find_all('img')
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

        return data

    @bypass_cf
    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        headers = {
            'Referer': self.chapter_url.format(manga_slug=manga_slug, chapter_slug=chapter_slug),
        }
        r = self.session_get(page['image'], headers=headers)
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

    def get_manga_list(self, type, orderby):
        r = self.session_get(self.manga_list_url.format(type, orderby))
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for a_element in soup.select('.listupd .bs a'):
            results.append(dict(
                slug=a_element.get('href').split('/')[-2],
                name=a_element.get('title'),
                cover=a_element.select_one('img.ts-post-image').get('src'),
            ))

        return results

    @bypass_cf
    def get_latest_updates(self, type):
        return self.get_manga_list(type, 'update')

    @bypass_cf
    def get_most_populars(self, type):
        return self.get_manga_list(type, 'popular')

    @bypass_cf
    def search(self, term, type):
        r = self.session_post(
            self.api_url,
            data={
                'action': 'ts_ac_do_search',
                'ts_ac_query': term,
            },
            headers={
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        results = []
        for serie in r.json()['series'][0]['all']:
            if serie['post_type'] == 'Novel':
                continue

            results.append(dict(
                slug=serie['post_link'].split('/')[-2],
                name=serie['post_title'],
                cover=serie['post_image'],
                last_chapter=serie['post_latest'],
            ))

        return results
