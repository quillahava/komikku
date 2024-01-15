# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type


class Tcbscans(Server):
    id = 'tcbscans'
    name = 'TCB Scans'
    lang = 'en'

    base_url = 'https://onepiecechapters.com'
    most_populars_url = base_url + '/projects'
    manga_url = base_url + '/mangas/{0}'
    chapter_url = base_url + '/chapters/{0}'
    image_url = 'https://cdn.onepiecechapters.com/file/CDN-M-A-N/{0}'

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
            scanlators=[self.name, ],
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        data['name'] = soup.find('h1').text.strip()
        data['cover'] = soup.select_one('.grid .bg-card > .flex > img').get('src')

        # Details
        data['synopsis'] = soup.select_one('p.leading-6').text.strip()

        # Chapters
        for a_element in reversed(soup.select('a.block')):
            slug = '/'.join(a_element.get('href').split('/')[-2:])
            index = a_element.select_one('div:first-child').text.strip().split()[-1]
            title = a_element.select_one('div:last-child').text.strip()

            data['chapters'].append(dict(
                slug=slug,
                title=f'Chapter {index} - {title}' if title else f'Chapter {index}',
                date=None,
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(chapter_slug))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )
        for img_element in soup.select('picture > img'):
            data['pages'].append(dict(
                slug=img_element.get('src').split('/')[-1],
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            self.image_url.format(page['slug']),
            headers={
                'Referer': self.chapter_url.format(chapter_slug),
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
            name=page['slug'],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_most_populars(self):
        """
        Returns manga list
        """
        r = self.session_get(self.most_populars_url)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for a_element in soup.select('.grid .bg-card .flex .relative a'):
            results.append(dict(
                slug='/'.join(a_element.get('href').split('/')[-2:]),
                name=a_element.img.get('alt'),
                cover=a_element.img.get('src'),
            ))

        return results

    def search(self, term):
        results = []
        for item in self.get_most_populars():
            if term and term.lower() in item['name'].lower():
                results.append(item)

        return results
