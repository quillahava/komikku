# Copyright (C) 2020-2023 GrownNed
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: GrownNed <grownned@gmail.com>

from bs4 import BeautifulSoup
import requests
import json

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type

headers = {
    'User-Agent': USER_AGENT,
}


class Mangalib(Server):
    id = 'mangalib'
    name = 'MangaLib'
    lang = 'ru'

    base_url = 'https://mangalib.org'
    search_url = base_url + '/manga-list'
    manga_url = base_url + '/{0}'
    chapter_url = manga_url + '/{1}'
    image_url = '{0}/{1}/{2}'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = headers

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

        title_element = soup.select_one('.media-name__main')
        data['name'] = title_element.text.strip()

        cover_element = soup.select_one('.media-sidebar__cover > img')
        data['cover'] = cover_element.get('src')

        # Details
        for element in soup.select('.media-info-list__item'):
            label = element.select_one('.media-info-list__title').text.strip()
            value_element = element.select_one('.media-info-list__value')

            if label.startswith('Автор'):
                data['authors'] = [author.text.strip() for author in value_element.find_all('a')]
            elif label.startswith('Художник'):
                data['authors'] = [
                    author.text.strip()
                    for author in value_element.find_all('a')
                    if author.text.strip() not in data['authors']
                ]
            elif label.startswith('Переводчик'):
                data['scanlators'] = [scanlator.text.strip() for scanlator in value_element.find_all('a')]
            elif label.startswith('Статус тайтла'):
                status = value_element.text.strip()
                if status == 'Онгоинг':
                    data['status'] = 'ongoing'
                elif status == 'Завершён':
                    data['status'] = 'complete'

        data['genres'] = [genre.text.strip() for genre in soup.select('.media-tags a')]

        # Synopsis
        synopsis_element = soup.select_one('.media-description__text')
        if synopsis_element:
            data['synopsis'] = synopsis_element.text.strip()

        # Chapters
        info = None
        for script_element in soup.find_all('script'):
            script = script_element.string
            if script is None:
                continue

            for line in script.split('\n'):
                line = line.strip()
                if line.startswith('window.__DATA__ ='):
                    info = json.loads(line[18:-1])
                    break

            if info:
                break

        for chapter in reversed(info['chapters']['list']):
            data['chapters'].append(dict(
                slug=f'v{chapter["chapter_volume"]}/c{chapter["chapter_number"]}',
                title=f'Том {chapter["chapter_volume"]} Глава {chapter["chapter_number"]} - {chapter["chapter_name"]}',
                date=convert_date_string(chapter['chapter_created_at'][:10], format='%Y-%m-%d'),
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

        soup = BeautifulSoup(r.text, 'lxml')

        info = None
        pages = None
        for script_element in soup.find_all('script'):
            script = script_element.string
            if not script:
                continue

            for line in script.split('\n'):
                line = line.strip()
                if info is None and line.startswith('window.__info ='):
                    info = json.loads(line[16:-1])
                elif pages is None and line.startswith('window.__pg ='):
                    pages = json.loads(line[14:-1])

            if info is not None and pages is not None:
                break

        if info is None or pages is None:
            return None

        data = dict(
            pages=[],
        )

        for page in pages:
            data['pages'].append(dict(
                slug=None,
                image=self.image_url.format(info['servers'][info['img']['server']], info['img']['url'], page['u']),
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
            name=page['image'].split('/')[-1].split('?')[0],
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
        return self.search('', orderby='latest')

    def get_most_populars(self):
        """
        Returns best noted manga list
        """
        return self.search('', orderby='populars')

    def search(self, term, orderby=None):
        if orderby == 'latest':
            params = dict(sort='last_chapter_at', dir='desc')
        elif orderby == 'populars':
            params = dict(sort='views', dir='desc')
        else:
            params = dict(name=term)

        r = self.session_get(self.search_url, params=params)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for card in soup.find_all('a', class_='media-card'):
            results.append(dict(
                name=card.div.h3.text.strip(),
                slug=card.get('href').split('/')[-1],
                cover=card.get('data-src'),
            ))

        return sorted(results, key=lambda m: m['name']) if term else results


# NSFW
class Hentailib(Mangalib):
    id = 'hentailib:mangalib'
    name = 'HentaiLib'
    lang = 'ru'
    is_nsfw_only = True
    status = 'disabled'

    base_url = 'https://hentailib.me'
    search_url = base_url + '/manga-list?name={0}'
    most_populars_url = base_url + '/manga-list?sort=views'
    manga_url = base_url + '/{0}'
    chapter_url = manga_url + '/{1}'
    image_url = 'https://img{0}.hentailib.me{1}'
