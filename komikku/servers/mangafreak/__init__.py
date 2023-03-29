# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import logging
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.webview import bypass_cf

logger = logging.getLogger('komikku.servers.mangafreak')


class Mangafreak(Server):
    id = 'mangafreak'
    name = 'MangaFreak'
    lang = 'en'
    is_nsfw = True

    has_cf = True

    base_url = 'https://w15.mangafreak.net'
    most_populars_url = base_url
    latest_updates_url = base_url + '/Latest_Releases'
    search_url = base_url + '/Search/{term}'
    manga_url = base_url + '/Manga/{slug}'
    chapter_url = base_url + '/{chapter_slug}'
    image_url = 'https://images.mangafreak.net/mangas/{slug}'
    bypass_cf_url = base_url + '/Manga/One_Piece'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': USER_AGENT})

    @bypass_cf
    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(self.manga_url.format(slug=initial_data['slug']))
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

        details_container_element = soup.find('div', class_='manga_series_data')

        # Name & cover
        data['name'] = details_container_element.h1.text.strip()
        data['cover'] = soup.find('div', class_='manga_series_image').img.get('src')

        # Details
        details_elements = details_container_element.find_all('div')

        status = details_elements[1].text.strip()
        if status == 'COMPLETED':
            data['status'] = 'complete'
        elif status == 'ON-GOING':
            data['status'] = 'ongoing'

        author = details_elements[2].text.strip()
        if author:
            data['authors'].append(author)
        author = details_elements[3].text.strip()
        if author:
            data['authors'].append(author)

        for a_element in details_elements[5].find_all('a'):
            data['genres'].append(a_element.text.strip())

        # Synopsis
        data['synopsis'] = soup.find('div', class_='manga_series_description').p.text.strip()

        # Chapters
        for tr_element in soup.find('div', class_='manga_series_list').find_all('tr'):
            tds_elements = tr_element.find_all('td')

            slug = tds_elements[0].a.get('href').split('/')[-1]
            title = tds_elements[0].a.text.strip()
            date = tds_elements[1].text.strip()

            data['chapters'].append(dict(
                slug=slug,
                title=title,
                date=convert_date_string(date, format='%Y/%m/%d'),
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(chapter_slug=chapter_slug))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )
        for div_element in soup.find('div', class_='slideshow-container').find_all('div', class_='mySlides'):
            data['pages'].append(dict(
                slug='/'.join(div_element.img.get('src').split('/')[-3:]),
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            self.image_url.format(slug=page['slug']),
            headers={
                'referer': self.chapter_url.format(chapter_slug=chapter_slug),
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
            name=page['slug'].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug=slug)

    def get_latest_updates(self):
        """
        Returns latest released
        """
        r = self.session_get(self.latest_updates_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for element in soup.select('.latest_releases_item'):
            img_element = element.select_one('.latest_releases_item img')
            a_element = element.select_one('.latest_releases_info a')
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
                cover=img_element.get('src'),
            ))

        return results

    def get_most_populars(self):
        """
        Returns featured manga list
        """
        r = self.session_get(self.most_populars_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for element in soup.select('.featured_item'):
            img_element = element.select_one('.featured_item_image a img')
            a_element = element.select_one('.featured_item_info a')
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
                cover=img_element.get('src'),
            ))

        return results

    @bypass_cf
    def search(self, term):
        r = self.session_get(self.search_url.format(term=term))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for item in soup.find_all('div', class_='manga_search_item'):
            a_element = item.find('h3').a
            results.append(dict(
                slug=a_element.get('href').strip().split('/')[-1],
                name=a_element.text.strip(),
                cover=item.span.a.img.get('src'),
            ))

        return results
