# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Monkeyuser(Server):
    id = 'monkeyuser'
    name = 'MonkeyUser'
    lang = 'en'
    true_search = False

    base_url = 'https://www.monkeyuser.com'
    manga_url = base_url + '/toc/'
    chapter_url = base_url + '/{0}/'
    image_url = base_url + '/assets/images/{0}'
    cover_url = base_url + '/assets/images/2021/226-update.png'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content
        """
        r = self.session_get(self.manga_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = initial_data.copy()
        data.update(dict(
            authors=['Stefanache Cornel', 'Constantin Orasanu', 'Maria Sîrbu'],
            scanlators=[],
            genres=['Humor', 'Satire'],
            status='ongoing',
            synopsis='Software development satire in a web comic.',
            chapters=[],
            server_id=self.id,
            cover=self.cover_url,
        ))

        # Chapters
        for element in reversed(soup.select('.toc-entry')):
            a_element = element.select_one('a')
            title = a_element.text.strip()
            if 'animated' in title.lower():
                continue

            data['chapters'].append(dict(
                slug='/'.join(a_element.get('href').split('/')[1:-1]),
                date=convert_date_string(element.select_one('strong').text.strip(), '%B %d, %Y'),
                title=title,
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

        if img_element := soup.select_one('.content img'):
            # Some chapters have no image but an embedded Youtube video
            return dict(
                pages=[
                    dict(
                        slug='/'.join(img_element.get('src').split('/')[-2:]),
                        image=None,
                    ),
                ]
            )

        return None

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(self.image_url.format(page['slug']))
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
        return self.manga_url

    def get_most_populars(self):
        return [dict(
            slug='',
            name='MonkeyUser',
            cover=self.cover_url,
        )]

    def search(self, term=None):
        # This server does not have a search
        # but a search method is needed for `Global Search` in `Explorer`
        # In order not to be offered in `Explorer`, class attribute `true_search` must be set to False

        results = []
        for item in self.get_most_populars():
            if term and term.lower() in item['name'].lower():
                results.append(item)

        return results
