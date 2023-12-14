# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Hean CMS

# Supported servers:
# Perf scan [FR]
# Reaper Scans [pt_BR]

from bs4 import BeautifulSoup
import json
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Heancms(Server):
    base_url: str
    api_url: str
    manga_url: str = None
    chapter_url: str = None

    cover_css_path: str
    authors_css_path: str
    synopsis_css_path: str

    def __init__(self):
        if self.manga_url is None:
            self.manga_url = self.base_url + '/series/{0}'
        if self.chapter_url is None:
            self.chapter_url = self.base_url + '/series/{0}/{1}'

        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': USER_AGENT})

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
            status='ongoing',
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        data['name'] = soup.find('h1').text.strip()
        if img_element := soup.select_one(self.cover_css_path):
            data['cover'] = self.base_url + img_element.get('src')

        # Details
        if element := soup.select_one(self.authors_css_path):
            for author in element.text.split('|'):
                data['authors'].append(author.strip())

        data['synopsis'] = soup.select_one(self.synopsis_css_path).text.strip()

        # Chapters
        chapters = dict()

        def rwalk(obj):
            if isinstance(obj, list):
                for v in obj:
                    rwalk(v)

            elif isinstance(obj, dict):
                if 'chapters' in obj:
                    for chapter in obj['chapters']:
                        if chapter['id'] in chapters:
                            continue

                        title = chapter['chapter_name']
                        if chapter.get('chapter_title'):
                            title = f'{title} - {chapter["chapter_title"]}'

                        chapters[chapter['id']] = dict(
                            title=title,
                            slug=chapter['chapter_slug'],
                            date=convert_date_string(chapter['created_at'].split('T')[0], '%Y-%m-%d'),
                        )
                else:
                    for _k, v in obj.items():
                        rwalk(v)

        for script_element in soup.find_all('script'):
            script = script_element.string
            if not script or 'self.__next_f.push' not in script or 'chapters' not in script:
                continue

            json_data = script[19:-1]
            json_data = json.loads(json_data)
            json_data = json.loads(json_data[1].split(':', 1)[1])
            rwalk(json_data)

            data['chapters'] = list(reversed(chapters.values()))
            break

        return data

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

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )
        for img_element in soup.select('p.flex.flex-col > img'):
            data['pages'].append(dict(
                slug=None,
                image=img_element.get('src') or img_element.get('data-src'),
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            page['image'],
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

    def get_latest_updates(self):
        """
        Returns latest updates
        """
        return self.get_manga_list(orderby='latest')

    def get_manga_list(self, term=None, orderby=None):
        params = dict(
            series_type='Comic',
        )
        if term:
            params['query_string'] = term
        else:
            params.update(dict(
                visibility='Public',
                order='desc',
                page=1,
                perPage=12
            ))
            if orderby == 'latest':
                params['orderBy'] = 'latest'
            elif orderby == 'popular':
                params['orderBy'] = 'total_views'

        r = self.session_get(
            self.api_url + '/query',
            params=params,
            headers={
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        results = []
        for item in r.json()['data']:
            results.append(dict(
                slug=item['series_slug'],
                name=item['title'],
                cover=item['thumbnail'],
                last_chapter=item['chapters'][0]['chapter_name'] if item.get('chapters') else None,
            ))

        return results

    def get_most_populars(self):
        """
        Returns most popular mangas
        """
        return self.get_manga_list(orderby='popular')

    def search(self, term):
        return self.get_manga_list(term=term)
