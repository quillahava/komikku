# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import requests

from komikku.utils import skip_past
from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.exceptions import NotFoundError
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type

# NOTE: https://mangakakalot.com seems to be a clone (same IP)
SERVER_NAME = 'MangaNato (MangaNelo)'


class Manganelo(Server):
    id = 'manganelo'
    name = SERVER_NAME
    lang = 'en'
    long_strip_genres = ['Webtoons', ]

    base_url = 'https://manganato.com'
    search_url = base_url + '/getstorysearchjson'
    manga_list_url = base_url + '/genre-all'
    manga_url = 'https://chapmanganato.com/manga-{0}'
    chapter_url = manga_url + '/chapter-{1}'

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

        if soup.find(class_='panel-not-found'):
            # No longer exists
            raise NotFoundError

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

        # Name & cover
        data['name'] = soup.find('div', class_='story-info-right').find('h1').text.strip()
        if data.get('cover') is None:
            data['cover'] = soup.find('span', class_='info-image').img.get('src')

        # Details
        tr_elements = soup.find('table', class_='variations-tableInfo').find_all('tr')
        for tr_element in tr_elements:
            td_elements = tr_element.find_all('td')
            label = td_elements[0].text.strip()
            value = td_elements[1].text.strip()

            if label.startswith('Author'):
                data['authors'] = [t.strip() for t in value.split('-') if t]
            elif label.startswith('Genres'):
                data['genres'] = [t.strip() for t in value.split('-')]
            elif label.startswith('Status'):
                status = value.lower()
                if status == 'completed':
                    data['status'] = 'complete'
                elif status == 'ongoing':
                    data['status'] = 'ongoing'

        # Synopsis
        div_synopsis = soup.find('div', id='panel-story-info-description')
        div_synopsis.h3.extract()
        data['synopsis'] = div_synopsis.text.strip()

        # Chapters
        li_elements = soup.find('ul', class_='row-content-chapter').find_all('li')
        for li_element in reversed(li_elements):
            span_elements = li_element.find_all('span')

            href = li_element.a.get('href')
            slug = href[skip_past(href, '/chapter-'):]
            title = li_element.a.text.strip()
            date = span_elements[1].get('title')[:-6]

            data['chapters'].append(dict(
                slug=slug,
                title=title,
                date=convert_date_string(date, format='%b %d,%y'),
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

        if soup.find(class_='panel-not-found'):
            # No longer exists
            raise NotFoundError

        pages_imgs = soup.find('div', class_='container-chapter-reader').find_all('img')

        data = dict(
            pages=[],
        )
        for img in pages_imgs:
            data['pages'].append(dict(
                slug=None,  # slug can't be used to forge image URL
                image=img.get('src'),
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(page['image'], headers={'referer': self.chapter_url.format(manga_slug, chapter_slug)})
        if r.status_code == 404:
            raise NotFoundError
        elif r.status_code != 200:
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

    def get_latest_updates(self):
        """
        Returns latest manga list
        """
        return self.get_manga_list(orderby='latest')

    def get_most_populars(self):
        """
        Returns hot manga list
        """
        return self.get_manga_list(orderby='populars')

    def get_manga_list(self, orderby=None):
        """
        Returns hot manga list
        """
        params = {}
        if orderby == 'populars':
            params['type'] = 'topview'

        r = self.session_get(self.manga_list_url, params=params)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for element in soup.select('.content-genres-item'):
            url = element.div.h3.a.get('href')
            results.append(dict(
                name=element.div.h3.a.get('title').strip(),
                slug=url[skip_past(url, '/manga-'):],
                cover=element.a.img.get('src'),
            ))

        return results

    def search(self, term):
        r = self.session_post(self.search_url, data=dict(searchword=term))
        if r.status_code != 200:
            return None

        data = r.json()

        results = []
        for item in data['searchlist']:
            link = item['url_story']
            results.append(dict(
                slug=link[skip_past(link, '/manga-'):],
                name=BeautifulSoup(item['name'], 'html.parser').text,
                cover=item['image'],
            ))

        return results
