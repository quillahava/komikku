# -*- coding: utf-8 -*-

# Copyright (C) 2021 Mariusz Kurek
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Mariusz Kurek <mariuszkurek@pm.me>

from bs4 import BeautifulSoup
import logging
import requests

from komikku.servers import convert_date_string
from komikku.servers import get_buffer_mime_type
from komikku.servers import Server
from komikku.servers import USER_AGENT

logger = logging.getLogger('komikku.servers.tapas')

# each page is 10 entries
SEARCH_RESULTS_PAGES = 10
CHAPTERS_PER_REQUEST = 100


class Tapas(Server):
    id = 'tapas'
    name = 'Tapas'
    lang = 'en'

    base_url = 'https://tapas.io'
    # g=0 is all genres, no parameter means looking only for romances
    # F2R means only comics available for free, TODO: premium support
    most_populars_url = base_url + '/comics?g=0&f=F2R'
    search_url = base_url + '/search'
    manga_url = base_url + '/series/{0}'
    manga_info_url = base_url + '/series/{0}/info'
    chapters_url = base_url + '/series/{0}/episodes'
    chapter_url = base_url + '/episode/{0}'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})
            for name in ('birthDate', 'adjustedBirthDate'):
                cookie = requests.cookies.create_cookie(
                    name=name,
                    value='2001-01-01',
                    domain='tapas.io',
                    path='/',
                    expires=None,
                )
                self.session.cookies.set_cookie(cookie)

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(self.manga_info_url.format(initial_data['slug']))
        if r is None:
            return None

        mime_type = get_buffer_mime_type(r.content)

        if r.status_code != 200 or mime_type != 'text/html':
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
            cover=None,
        ))

        data['name'] = soup.find(class_='section__top--simple').find(class_='title').text
        data['synopsis'] = soup.find('meta', property='og:description').get('content')
        data['cover'] = soup.find(class_='section__top--simple').find(class_='thumb').img.get('src')

        for author_element in soup.find(class_='creator').find_all('a'):
            data['authors'].append(author_element.text)

        for genre in soup.find(class_='detail-row__body--genre').find_all('a'):
            data['genres'].append(genre.text)

        data['chapters'] = self.resolve_chapters(initial_data['slug'])

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(chapter_slug))
        if r is None:
            return None

        mime_type = get_buffer_mime_type(r.content)

        if r.status_code != 200 or mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            slug=chapter_slug,
            title=soup.find(class_='title').text,
            pages=[],
            date=convert_date_string(soup.find(class_='date').text, format='%b %d, %Y'),
        )

        for page in soup.find(class_='js-episode-article').find_all('img'):
            data['pages'].append(dict(
                slug=None,
                image=page.get('data-src'),
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(page['image'])
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

    def get_most_populars(self):
        r = self.session_get(self.most_populars_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for div_element in soup.find_all(class_='item__thumb'):
            results.append(dict(
                slug=div_element.a.get('data-series-id'),
                url=div_element.a.get('href'),
                name=div_element.a.img.get('alt'),
            ))

        return results

    def resolve_chapters(self, manga_slug, page=1):
        r = self.session_get(
            self.chapters_url.format(manga_slug),
            params=dict(max_limit=CHAPTERS_PER_REQUEST, page=page)
        )
        if r.status_code != 200:
            return None

        content = r.json()['data']['body']

        soup = BeautifulSoup(content, 'html.parser')

        chapters = []
        for chapter in soup.find_all('li'):
            if 'js-coming-soon' in chapter.get('class') or 'js-have-to-sign' in chapter.get('class'):
                continue

            chapters.append(dict(
                slug=chapter.get('data-id'),
                title='{0} - {1}'.format(
                    chapter.find(class_='info__label').text.strip(),
                    chapter.find(class_='info__title').text.strip()
                ),
                date=None,  # Unfortunately, date is missing at this stage
            ))

        if r.json()['data']['pagination']['has_next']:
            chapters += self.resolve_chapters(manga_slug, page + 1)

        return chapters

    def search(self, term, page_number=1):
        r = self.session_get(self.search_url, params=dict(q=term, pageNumber=page_number))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for li_element in soup.find_all(class_='search-item-wrap'):
            a_element = li_element.find(class_='title').a

            if a_element.get('data-sale-type') not in ('FREE', 'WAIT_OR_MUST_PAY'):
                continue

            results.append(dict(
                slug=a_element.get('data-series-id'),
                url=a_element.get('href'),
                name=a_element.text,
            ))

        if page_number == 1:
            try:
                no_of_pages = int(soup.find_all(class_='paging__button--num')[-1].text)
            except TypeError:
                return results

            for page in range(2, min(SEARCH_RESULTS_PAGES + 1, no_of_pages + 1)):
                results += self.search(term, page)

        return results
