# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import logging

from komikku.servers import Server
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.webview import bypass_cf

logger = logging.getLogger('komikku.servers.legacyscans')


class Legacyscans(Server):
    id = 'legacyscans'
    name = 'LegacyScans'
    lang = 'fr'

    has_cf = True

    base_url = 'https://legacy-scans.com'
    api_url = 'https://api.legacy-scans.com'
    api_search_url = api_url + '/misc/home/search'
    api_latest_updates_url = api_url + '/misc/comic/home/updates'
    api_most_popular_url = api_url + '/misc/views/monthly'
    manga_url = base_url + '/comics/{0}'
    chapter_url = base_url + '/comics/{0}/{1}'
    image_url = api_url + '/public/chapterImages/{0}'

    def __init__(self):
        self.session = None

    @bypass_cf
    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],  # not available
            genres=[],
            status=None,  # not available
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        data['name'] = soup.select_one('.serieTitle h1').text.strip()
        data['cover'] = soup.select_one('.serieImg img').get('src')

        #  Details
        for element in soup.select('.serieGenre > span'):
            data['genres'].append(element.text.strip())

        if author1 := soup.select_one('div.serieAdd > p:nth-child(2) > strong'):
            if author1.text.strip() != 'Inconnu':
                data['authors'].append(author1.text.strip())
        if author2 := soup.select_one('div.serieAdd > p:nth-child(3) > strong'):
            if author2.text.strip() != 'Inconnu':
                data['authors'].append(author2.text.strip())

        # Synopsis
        if synopsis_element := soup.select_one('.serieDescription > div'):
            data['synopsis'] = synopsis_element.text.strip()

        # Chapters
        for a_element in reversed(soup.select('.chapterList a')):
            data['chapters'].append(dict(
                slug='/'.join(a_element.get('href').split('/')[-2:]),
                title=a_element.select_one('div span:first-child').text.strip(),
                date=convert_date_string(a_element.select_one('div span:last-child').text.strip(), format='%d/%m/%Y'),
            ))

        return data

    @bypass_cf
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(
            self.chapter_url.format(manga_slug, chapter_slug),
            headers={
                'Referer': self.manga_url.format(manga_slug),
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        data = dict(
            pages=[],
        )
        for img_element in soup.select('.readerComics > img'):
            data['pages'].append(dict(
                slug=None,
                image='/'.join(img_element.get('src').split('/')[-3:]),
            ))

        return data

    @bypass_cf
    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            self.image_url.format(page['image']),
            headers={
                'Referer': self.chapter_url.format(manga_slug, chapter_slug),
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

    @bypass_cf
    def get_latest_updates(self):
        r = self.session_get(
            self.api_latest_updates_url,
            params=dict(
                start=1,
                end=24,
            ),
            headers={
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        results = []
        for item in r.json():
            results.append(dict(
                cover='{0}/{1}'.format(self.api_url, item['cover']),
                slug=item['slug'],
                name=item['title'],
            ))

        return results

    @bypass_cf
    def get_most_populars(self):
        r = self.session_get(
            self.api_most_popular_url,
            headers={
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        results = []
        for item in r.json():
            results.append(dict(
                cover='{0}/{1}'.format(self.api_url, item['cover']),
                slug=item['slug'],
                name=item['title'],
            ))

        return results

    @bypass_cf
    def search(self, term=None, orderby=None):
        params = dict(
            title=term,
        )

        r = self.session_get(
            self.api_search_url,
            params=params,
            headers={
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        results = []
        for item in r.json()['results']:
            results.append(dict(
                slug=item['slug'],
                name=item['title'],
            ))

        return results
