# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
from gettext import gettext as _
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type


class Mangapill(Server):
    id = 'mangapill'
    name = 'Mangapill'
    lang = 'en'
    is_nsfw = True

    base_url = 'https://mangapill.com'
    latest_updates_url = base_url + '/chapters'
    most_populars_url = base_url
    search_url = base_url + '/search'
    manga_url = base_url + '/manga/{0}'
    chapter_url = base_url + '/chapters/{0}'

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
                {'key': 'novel', 'name': _('Novel')},
                {'key': 'one-shot', 'name': _('One Shot')},
                {'key': 'doujinshi', 'name': _('Doujinshi')},
                {'key': 'manhwa', 'name': _('Manhwa')},
                {'key': 'manhua', 'name': _('Manhua')},
                {'key': 'oel', 'name': _('OEL')},
            ],
        },
    ]

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = {
                'User-Agent': USER_AGENT,
            }

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's url (provided by search)
        """
        assert 'url' in initial_data, 'url is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['url']))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        data = initial_data.copy()
        data.update(dict(
            authors=[],  # not available
            scanlators=[],  # not available
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        info_element = soup.select_one('div.container:nth-child(2) > .flex-col')

        data['name'] = info_element.find('h1').text.strip()
        data['cover'] = info_element.find('img', class_='object-cover').get('data-src')

        #  Details
        for element in info_element.select('.grid > div'):
            label = element.label.text.strip()
            if label == 'Status':
                status = element.div.text
                if status == 'publishing':
                    data['status'] = 'ongoing'
                elif status == 'finished':
                    data['status'] = 'complete'
                elif status == 'on hiatus':
                    data['status'] = 'hiatus'
                elif status == 'discontinued':
                    data['status'] = 'suspended'

        for element in info_element.select('.mb-3:nth-child(4) a'):
            data['genres'].append(element.text.strip())

        # Synopsis
        if synopsis_element := info_element.find('p'):
            data['synopsis'] = synopsis_element.text.strip()

        # Chapters
        for a_element in reversed(soup.select('#chapters a')):
            data['chapters'].append(dict(
                slug=a_element.get('href').split('/')[2],  # not used
                url='/'.join(a_element.get('href').split('/')[2:]),
                title=a_element.text.strip(),
                date=None,  # not available
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(chapter_url))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        data = dict(
            pages=[],
        )
        for img_element in soup.find_all('img', class_='js-page'):
            data['pages'].append(dict(
                slug=None,
                image=img_element.get('data-src'),
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            page['image'],
            headers={
                'Referer': self.manga_url.format(manga_slug)
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
        return self.manga_url.format(url)

    def get_latest_updates(self, type=None):
        """
        Returns latest updates
        """
        r = self.session_get(self.latest_updates_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.select('.container .grid > div'):
            a_element = element.select_one('a.text-secondary')
            results.append(dict(
                name=a_element.select_one('div:first-child').text.strip(),
                url='/'.join(a_element.get('href').split('/')[-2:]),
                slug=a_element.get('href').split('/')[-1],  # not used
                cover=element.a.figure.img.get('data-src'),
            ))

        return results

    def get_most_populars(self, type=None):
        """
        Returns Trending mangas
        """
        r = self.session_get(self.most_populars_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.select('.container:nth-child(4) .grid > div'):
            a_element = element.select_one('a.mb-2')
            results.append(dict(
                name=a_element.select_one('div:first-child').text.strip(),
                url='/'.join(a_element.get('href').split('/')[-2:]),
                slug=a_element.get('href').split('/')[-1],  # not used
                cover=element.a.figure.img.get('data-src'),
            ))

        return results

    def search(self, term, type=None):
        r = self.session_get(
            self.search_url,
            params=dict(
                q=term,
                type=type if type != 'all' else None,
                status=None,
            )
        )

        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.select('div.container:nth-child(2) .grid:nth-child(3) > div'):
            a_element = element.select_one('a.mb-2')
            results.append(dict(
                name=a_element.select_one('div:first-child').text.strip(),
                url='/'.join(a_element.get('href').split('/')[-2:]),
                slug=a_element.get('href').split('/')[-1],  # not used
                cover=element.a.figure.img.get('data-src'),
            ))

        return results
