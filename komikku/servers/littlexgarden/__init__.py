# Copyright (C) 2023-2024 Pierre-Emmanuel Devin
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-late
# Author: Pierre-Emmanuel Devin <pierreemmanuel.devin@posteo.net>

import json
from regex import Regex
import requests

from bs4 import BeautifulSoup

from komikku.servers import Server, USER_AGENT
from komikku.servers.exceptions import NotFoundError
from komikku.servers.utils import get_buffer_mime_type


class Littlexgarden(Server):
    id = 'littlexgarden'
    name = 'Little Garden'
    lang = 'fr'

    base_url = 'https://littlexgarden.com'
    api_url = base_url + '/graphql'
    manga_url = base_url + '/{0}'
    chapter_url = manga_url + '/{1}'
    image_url = base_url + '/static/images/{0}'
    cover_url = base_url + '/static/images/webp/{0}.webp'

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

        soup = BeautifulSoup(r.text, 'lxml')

        if soup.find(class_='error'):
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

        data['name'] = soup.find('h2', class_='super-title font-weight-bold').find('span').text.strip()
        data['chapters'], data['cover'] = self.get_manga_chapters_data(initial_data['slug'])

        return data

    def get_manga_chapters_data(self, slug):
        def build_query(query):
            return query.replace('%', '$')

        query = build_query("""
            query chapters(
                %slug: String,
                %limit: Float,
                %skip: Float,
                %order: Float!,
                %isAdmin: Boolean!
            ) {
                chapters(
                    limit: %limit,
                    skip: %skip,
                    where: {
                        deleted: false,
                        published: %isAdmin,
                        manga: {
                            slug: %slug,
                            published: %isAdmin,
                            deleted: false
                        }
                    },
                    order: [{ field: "number", order: %order }]
                ) {
                    published
                    likes
                    id
                    number
                    thumb
                    manga {
                        id
                        name
                        slug
                        __typename
                    }
                    __typename
                }
            }
        """)

        variables = json.dumps(dict(
            slug=slug,
            order=1,
            limit=2000,
            skip=0,
            isAdmin=True,
        ))

        body = json.dumps(dict(
            operationName='chapters',
            query=query,
            variables=variables,
        ))

        # Request directly their data rather than scraping a page as chapters are dynamically loaded
        r = requests.post(
            self.api_url,
            data=body,
            headers={
                'Content-Length': str(len(body)),
                'Content-Type': 'application/json; charset=utf-8',
            }
        )
        if r.status_code != 200:
            return None

        chapters = json.loads(r.text)['data']['chapters']

        cover = None
        results = []
        for chap in chapters:
            if cover is None:
                # Used first chapter cover as manga cover
                cover = self.cover_url.format(chap['thumb'])
            results.append(dict(
                slug=str(chap['number']) + '/1',
                title=str(chap['number']),
            ))

        return results, cover

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

        soup = BeautifulSoup(r.text, 'lxml')
        if soup.find(class_='error'):
            raise NotFoundError

        chap_nb = int(soup.find('div', class_='chapter-number').text)

        pages = []
        if soup.find('div', class_='manga-name').text.strip() == 'One Piece' and chap_nb > 1004:
            # to get colored one piece content (this is the main advantage of this website).
            original_colored_page_regex = Regex('\\{colored:(?<colored>.*?(?=,)),original:(?<original>.*?(?=,))')
            all_colored_pages = original_colored_page_regex.findall(r.text)
            for (colored_page, page) in all_colored_pages:
                if colored_page[0] == '"':
                    pages.append(dict(
                        slug=colored_page.replace('"', ''),
                        image=None,
                    ))
                else:
                    pages.append(dict(
                        slug=page.replace('"', ''),
                        image=None,
                    ))

        else:
            original_page_regex = Regex('original:"(.*?(?="))')
            all_pages = original_page_regex.findall(r.text)
            for page in all_pages:
                pages.append(dict(
                    slug=page.replace('"', ''),
                    image=None,
                ))

        return dict(pages=pages)

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
        Returns manga absolute url
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self):
        """
        Returns latest updated manga
        """
        r = self.session_get(self.base_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        slugs = []
        for a_element in soup.select('a.last'):
            slug = a_element.get('href').split('/')[1]
            if slug in slugs:
                continue

            cover_el = a_element.select_one('.img.image-item.background-image')
            results.append(dict(
                name=a_element.div.h3.text.strip(),
                slug=slug,
                cover=cover_el.get('style')[21:-2],
            ))
            slugs.append(slug)

        return results

    def get_most_populars(self):
        """
        Returns most popular manga
        """

        r = self.session_get(self.base_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.select('#manga-list a'):
            cover_el = element.select_one('.thumb')
            results.append(dict(
                name=element.get('title').strip(),
                slug=element.get('href').split('/')[1],
                cover=cover_el.get('style')[21:-2],
            ))

        return results

    def search(self, term):
        all_mangas = self.get_most_populars()
        if all_mangas is None:
            return None

        results = []
        for el in all_mangas:
            if term.lower() in el['name'].lower():
                results.append(el)

        return results
