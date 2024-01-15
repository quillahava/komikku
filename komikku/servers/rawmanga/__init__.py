# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup

from komikku.servers.multi.manga_stream import MangaStream
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.webview import bypass_cf


class Rawmanga(MangaStream):
    id = 'rawmanga'
    name = 'Raw Manga 生漫画'
    lang = 'ja'
    is_nsfw = True

    has_cf = True

    base_url = 'https://mangaraw.org'
    search_url = base_url + '/search'
    manga_url = base_url + '/{0}'
    chapter_url = base_url + '/{manga_slug}/{chapter_slug}'
    page_url = base_url + '/{0}/{1}/{2}'

    name_selector = '.infox h1'
    authors_selector = '.infox span:-soup-contains("Author")'
    genres_selector = '.infox span:-soup-contains("Genres") a'
    scanlators_selector = '.infox span:-soup-contains("Serialization")'
    status_selector = '.infox span:-soup-contains("Status")'
    synopsis_selector = '[itemprop="articleBody"]'

    def get_manga_chapters_data(self, soup):
        chapters = []
        for item in reversed(soup.select('.bixbox li')):
            a_element = item.find('a')

            slug = a_element.get('href').split('/')[-1]
            ignore = False
            for keyword in self.ignored_chapters_keywords:
                if keyword in slug:
                    ignore = True
                    break
            if ignore:
                continue

            chapters.append(dict(
                slug=slug,
                title=a_element.text.strip(),
                date=convert_date_string(item.find('time').get('title').split()[0], format='%Y-%m-%d'),
            ))

        return chapters

    @bypass_cf
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(
            self.chapter_url.format(manga_slug=manga_slug, chapter_slug=chapter_slug),
            headers={
                'Referer': self.manga_url.format(manga_slug),
            })
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )

        for option_element in soup.find_all('select', {'name': 'page'})[0].find_all('option'):
            data['pages'].append(dict(
                slug=option_element.get('value'),
                image=None,
            ))

        return data

    @bypass_cf
    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        headers = {
            'Referer': self.chapter_url.format(manga_slug=manga_slug, chapter_slug=chapter_slug),
        }
        r = self.session_get(self.page_url.format(manga_slug, chapter_slug, page['slug']), headers=headers)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        image_url = soup.select_one('.reader a img.picture').get('src')

        r = self.session_get(image_url, headers=headers)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=image_url.split('/')[-1],
        )

    def get_latest_updates(self, type):
        """
        Returns list of latest updates
        """
        return self.search('', type, orderby='latest')

    def get_most_populars(self, type):
        """
        Returns list of most popular manga
        """
        return self.search('', type, orderby='populars')

    @bypass_cf
    def search(self, term, type, orderby=None):
        if orderby:
            data = dict(
                order='popular' if orderby == 'populars' else 'update',
                status='',
                type=type,
            )
        else:
            data = dict(
                s=term,
                author='',
                released='',
                status='',
                order='title',
                type=type,
            )

        r = self.session_get(self.search_url, params=data)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for a_element in soup.select('.bsx > a'):
            type_ = a_element.select_one('.type').text.strip()
            if type_ == 'Novel':
                continue

            img_element = a_element.select_one('img')
            slug = a_element.get('href').split('/')[-1]

            results.append(dict(
                slug=slug,
                name=img_element.get('alt').strip(),
                cover=img_element.get('src'),
            ))

        return results
