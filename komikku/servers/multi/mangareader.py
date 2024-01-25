# Copyright (C) 2023-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Supported servers:
# MangaReader [EN/FR/JA/KO/ZH_HANS]

from bs4 import BeautifulSoup
from gettext import gettext as _
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.exceptions import ServerException
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import unscramble_image_rc4


class Mangareader(Server):
    base_url: str
    search_url: str
    list_url: str
    manga_url: str
    chapter_url: str
    api_chapter_images_url: str

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data from API

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(
            self.manga_url.format(initial_data['slug']),
            headers={
                'Referer': self.list_url,
            }
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],  # not available
            genres=[],
            status=None,
            cover=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
        ))

        data['name'] = soup.select_one('.manga-name').text.strip()
        data['cover'] = soup.select_one('.manga-poster > img').get('src')

        # Details
        for element in soup.select('.genres >a'):
            data['genres'].append(element.text.strip())

        for element in soup.select('.anisc-info .item'):
            label = element.span.text.strip()

            if label.startswith('Status'):
                value = element.select_one('.name').text.strip()
                if value == 'Publishing':
                    data['status'] = 'ongoing'
                elif value == 'Finished':
                    data['status'] = 'complete'
                elif value == 'Discontinued':
                    data['status'] = 'suspended'
                elif value == 'On Hiatus':
                    data['status'] = 'hiatus'

            elif label.startswith('Author'):
                for a_element in element.select('a'):
                    name = a_element.text.replace(',', '').strip()
                    func = a_element.next_sibling.replace(',', '').strip()
                    data['authors'].append(f'{name} {func}')

        if synopsis_element := soup.select_one('.description'):
            data['synopsis'] = synopsis_element.text.strip()

        # Chapters
        if ul_element := soup.select_one(f'#{self.languages_codes[self.lang]}-chapters'):
            for a_element in reversed(ul_element.select('li a')):
                data['chapters'].append(dict(
                    slug=a_element.get('href').split('/')[-1],
                    title=a_element.get('title').strip(),
                ))
        else:
            # Manga exists but has no chapters in self.lang (not filtered in search)
            raise ServerException(_('Not available in {0} language').format(self.lang.upper()))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        # Retrieve chapter ID in chapter HTML page
        chapter_url = self.chapter_url.format(manga_slug, self.languages_codes[self.lang], chapter_slug)
        r = self.session_get(
            chapter_url,
            headers={
                'Referer': self.manga_url.format(manga_slug),
            }
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        chapter_id = soup.select_one('#wrapper').get('data-reading-id')

        # Get chapter images (ajax)
        r = self.session_get(
            self.api_chapter_images_url.format(chapter_id),
            headers={
                'Referer': chapter_url,
                'x-requested-with': 'XMLHttpRequest',
            }
        )
        if r.status_code != 200:
            return None

        json_data = r.json()
        if json_data['status']:
            soup = BeautifulSoup(r.json()['html'], 'lxml')
        else:
            return None

        data = dict(
            pages=[],
        )
        for element in soup.select('.iv-card'):
            data['pages'].append(dict(
                slug=None,
                scrambled='shuffled' in element.get('class'),
                image=element.get('data-url'),
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            page['image'],
            headers={
                'Referer': self.base_url + '/',
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        if page['scrambled']:
            # js/read.min.js: key is 2nd argument of unShuffle function
            buffer = unscramble_image_rc4(r.content, 'stay', 200)
        else:
            buffer = r.content

        return dict(
            buffer=buffer,
            mime_type=mime_type,
            name=page['image'].split('?')[0].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_manga_list(self, sort='default'):
        params = {
            'type': None,
            'status': None,
            'rating_type': None,
            'score': None,
            'language': self.languages_codes[self.lang],
            'sy': None,
            'sm': None,
            'sd': None,
            'ey': None,
            'em': None,
            'ed': None,
            'sort': sort,
            'genre': None,
        }

        r = self.session_get(
            self.list_url,
            params=params,
            headers={
                'Referer': self.list_url,
            }
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for item in soup.select('.item-spc'):
            results.append(dict(
                slug=item.select_one('.manga-name > a').get('href').split('/')[-1],
                name=item.select_one('.manga-name').text.strip(),
                cover=item.select_one('.manga-poster > img').get('src'),
            ))

        return results

    def get_latest_updates(self):
        return self.get_manga_list(sort='latest-updated')

    def get_most_populars(self):
        return self.get_manga_list(sort='most-viewed')

    def search(self, term):
        # Beware: Search does not take language into account
        r = self.session_get(
            self.search_url,
            params=dict(keyword=term),
            headers={
                'Referer': self.base_url + '/',
            }
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for item in soup.select('.item-spc'):
            results.append(dict(
                slug=item.select_one('.manga-name > a').get('href').split('/')[-1],
                name=item.select_one('.manga-name').text.strip(),
                cover=item.select_one('.manga-poster > img').get('src'),
            ))

        return results
