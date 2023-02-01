# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import logging
import requests

from komikku.servers import Server
from komikku.servers.headless_browser import bypass_cloudflare
from komikku.servers.headless_browser import get_page_html
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import search_duckduckgo

logger = logging.getLogger('komikku.servers.japscan')


class Japscan(Server):
    id = 'japscan'
    name = 'JapScan'
    lang = 'fr'
    long_strip_genres = ['Webtoon', ]

    base_url = 'https://www.japscan.me'
    search_url = base_url + '/manga/'
    api_search_url = base_url + '/live-search/'
    manga_url = base_url + '/manga/{0}/'
    chapter_url = base_url + '/lecture-en-ligne/{0}/{1}/'
    page_url = '/lecture-en-ligne/{0}/{1}/{2}.html'
    cover_url = base_url + '{0}'

    def __init__(self):
        self.session = None

    @classmethod
    def get_manga_initial_data_from_url(cls, url):
        return dict(slug=url.split('/')[-2])

    @bypass_cloudflare
    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug']))
        if r is None:
            return None

        mime_type = get_buffer_mime_type(r.content)

        if r.status_code != 200 or mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],
            genres=[],
            status=None,
            chapters=[],
            server_id=self.id,
            synopsis=None,
        ))

        card_element = soup.find_all('div', class_='card')[0]

        # Main name: japscan handles several names for mangas (main + alternatives)
        # Name provided by search can be one of the alternatives
        # First word (Manga, Manhwa, ...) must be removed from name
        data['name'] = ' '.join(card_element.find('h1').text.strip().split()[1:])
        if data.get('cover') is None:
            data['cover'] = self.cover_url.format(card_element.find('img').get('src'))

        # Details
        if not card_element.find_all('div', class_='d-flex'):
            # mobile version
            elements = card_element.find_all('div', class_='row')[0].find_all('p')
        else:
            # desktop version
            elements = card_element.find_all('div', class_='d-flex')[0].find_all('p', class_='mb-2')

        for element in elements:
            label = element.span.text
            element.span.extract()
            value = element.text.strip()

            if label.startswith(('Auteur', 'Artiste')):
                for t in value.split(','):
                    t = t.strip()
                    if t not in data['authors']:
                        data['authors'].append(t)
            elif label.startswith('Genre'):
                data['genres'] = [genre.strip() for genre in value.split(',')]
            elif label.startswith('Statut'):
                # Possible values: ongoing, complete
                data['status'] = 'ongoing' if value == 'En Cours' else 'complete'

        # Synopsis
        synopsis_element = card_element.find('p', class_='list-group-item-primary')
        if synopsis_element:
            data['synopsis'] = synopsis_element.text.strip()

        # Chapters
        elements = soup.find('div', id='chapters_list').find_all('div', class_='chapters_list')
        for element in reversed(elements):
            if element.a.span:
                span = element.a.span.extract()
                # JapScan sometimes uploads some "spoiler preview" chapters, containing 2 or 3 untranslated pictures taken from a raw.
                # Sometimes they also upload full RAWs/US versions and replace them with a translation as soon as available.
                # Those have a span.badge "SPOILER", "RAW" or "VUS". We exclude these from the chapters list.
                if span.text.strip() in ('RAW', 'SPOILER', 'VUS', ):
                    continue

            slug = element.a.get('href').split('/')[3]

            data['chapters'].append(dict(
                slug=slug,
                title=element.a.text.strip(),
                date=convert_date_string(element.span.text.strip(), format='%d %b %Y'),
            ))

        return data

    @bypass_cloudflare
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url, decode=True):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages and scrambled are expected.
        """
        html = get_page_html(self.chapter_url.format(manga_slug, chapter_slug))
        soup = BeautifulSoup(html, 'lxml')

        if reader_element := soup.find(id='full-reader'):
            data = dict(
                pages=[],
            )

            img_elements = reader_element.find_all('img')
            if img_elements:
                # Full reader (several images)
                for img_element in img_elements:
                    data['pages'].append(dict(
                        url=None,
                        slug=None,
                        image=img_element.get('src'),
                    ))
            else:
                # Single reader (single image)
                for option_element in soup.find('select', id='pages').find_all('option'):
                    data['pages'].append(dict(
                        url=self.page_url.format(manga_slug, chapter_slug, int(option_element.get('value')) + 1),
                        slug=None,
                        image=None,
                    ))

            return data
        else:
            raise requests.exceptions.RequestException

    @bypass_cloudflare
    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        if page['image']:
            # We already know the image URL
            url = page['image']
        elif page['url']:
            soup = BeautifulSoup(get_page_html(self.base_url + page['url']), 'lxml')
            url = soup.find(id='single-reader').img.get('src')

        r = self.session_get(
            url,
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
            name=url.split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    @bypass_cloudflare
    def get_latest_updates(self):
        """
        Returns recent manga
        """
        r = self.session_get(self.base_url, headers={'Referer': self.base_url})
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for a_element in soup.select_one('div.card:nth-child(3) > div:nth-child(2) > ul').find_all('a'):
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-2],
            ))

        return results

    @bypass_cloudflare
    def get_most_populars(self):
        """
        Returns TOP manga
        """
        r = self.session_get(self.base_url, headers={'Referer': self.base_url})
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for li_element in soup.find('div', id='top_mangas_all_time').find_all('li'):
            a_element = li_element.find_all('a')[0]
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-2],
            ))

        return results

    @bypass_cloudflare
    def search(self, term):
        r = self.session_post(self.api_search_url, data=dict(search=term), headers={
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': '*/*',
            'Origin': self.base_url,
        })
        if r is None:
            return None

        if r.status_code == 200:
            try:
                data = r.json()

                results = []
                for item in data:
                    results.append(dict(
                        slug=item['url'].split('/')[-2],
                        name=item['name'],
                    ))

                return results
            except Exception:
                pass

        # Use DuckDuckGo Lite as fallback
        results = []
        for ddg_result in search_duckduckgo(self.search_url, term):
            # Remove first word in name (Manga, Manhua, Manhwa...)
            name = ' '.join(ddg_result['name'].split()[1:])
            # Keep only words before "|" character
            name = name.split('|')[0].strip()

            results.append(dict(
                name=name,
                slug=ddg_result['url'].split('/')[-2],
            ))

        return results
