# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type

SERVER_NAME = 'View Comics'


class Viewcomics(Server):
    id = 'viewcomics'
    name = SERVER_NAME
    lang = 'en'
    is_nsfw = True

    base_url = 'https://viewcomics.org'
    search_url = base_url + '/search'
    api_search_url = base_url + '/ajax/search'
    latest_updates_url = base_url + '/comic-updates'
    most_populars_url = base_url + '/popular-comics'
    manga_url = base_url + '/comic/{0}'
    chapter_url = base_url + '/{0}/{1}/full'

    csrf_token = None

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns comic data by scraping comic HTML page content

        Initial data should contain at least comic slug (provided by search)
        """
        assert 'slug' in initial_data, 'Comic slug is missing in initial data'

        r = self.session_get(
            self.manga_url.format(initial_data['slug']),
            headers={
                'referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'html.parser')

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],  # not available
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
        ))

        details_element = soup.find('div', class_='anime-details')

        data['name'] = details_element.find('h1', class_='title').text.strip()
        data['cover'] = details_element.find('div', class_='anime-image').img.get('src')

        # Details
        for li_element in details_element.find('ul', class_='anime-genres').find_all('li'):
            genre = li_element.text.strip()
            if genre in ('Completed', 'Ongoing'):
                if genre == 'Completed':
                    data['status'] = 'complete'
                else:
                    data['status'] = 'ongoing'
            else:
                data['genres'].append(genre)

        data['authors'] = [details_element.find('div', class_='anime-desc').find_all('tr')[3].find_all('td')[1].text.strip(), ]
        data['synopsis'] = soup.find('div', class_='detail-desc-content').p.text.strip()

        # Chapters
        for li_element in reversed(soup.find('ul', class_='basic-list').find_all('li')):
            a_element = li_element.a

            data['chapters'].append(dict(
                slug=a_element.get('href').split('/')[-1],
                title=a_element.text.strip(),
                date=convert_date_string(li_element.span.text.strip(), '%m/%d/%Y'),
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns comic chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(manga_slug, chapter_slug))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'html.parser')

        data = dict(
            pages=[],
        )

        for img_element in soup.find('div', class_='chapter-container').find_all('img'):
            data['pages'].append(dict(
                slug=None,
                image=img_element.get('src'),
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            page['image'],
            headers={
                'referer': self.chapter_url.format(manga_slug, chapter_slug),
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
            name='{0}.{1}'.format(page['image'].split('/')[-1], mime_type.split('/')[1]),
        )

    def get_manga_url(self, slug, url):
        """
        Returns comic absolute URL
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self):
        """
        Returns latest updates
        """
        r = self.session_get(
            self.latest_updates_url,
            headers={
                'referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for a_element in soup.select('.line-list > li > a'):
            results.append(dict(
                slug=a_element.get('href').split('/')[-1],
                name=a_element.text.strip(),
            ))

        return results

    def get_most_populars(self):
        """
        Returns list of most popular comics
        """
        r = self.session_get(
            self.most_populars_url,
            headers={
                'referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for element in soup.select('.eg-list .eg-box'):
            a_element = element.select_one('.egb-serie')
            img_element = element.select_one('.eg-image img')
            results.append(dict(
                slug=a_element.get('href').split('/')[-1],
                name=a_element.text.strip(),
                cover=img_element.get('src'),
            ))

        return results

    def search(self, term):
        if self.csrf_token is None:
            r = self.session_get(self.search_url)
            if r.status_code != 200:
                return None

            soup = BeautifulSoup(r.text, 'html.parser')

            self.csrf_token = soup.select_one('meta[name="csrf-token"]')['content']

        r = self.session_get(
            self.api_search_url,
            params=dict(q=term),
            headers={
                'Referer': self.base_url,
                'X-Csrf-TOKEN': self.csrf_token,
                'X-Requested-With': 'XMLHttpRequest',
            }
        )
        if r.status_code != 200:
            return None

        resp_data = r.json()
        if resp_data['status'] != '1':
            return None

        results = []
        for item in resp_data['data']:
            results.append(dict(
                slug=item['slug'],
                name=item['title'],
                cover=item['img_url'],
                last_chapter=item['chapter_slug']
            ))

        return results
