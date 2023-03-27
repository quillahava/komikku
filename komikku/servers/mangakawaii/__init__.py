# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import cloudscraper
from functools import wraps
import json
import requests
from urllib.parse import urlparse

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type

SERVER_NAME = 'MangaKawaii'


def set_lang(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        server = args[0]
        if not server.is_lang_set:
            server.session_get(server.base_url + '/lang/' + server.lang)
            server.is_lang_set = True

        return func(*args, **kwargs)

    return wrapper


class Mangakawaii(Server):
    id = 'mangakawaii'
    name = SERVER_NAME
    lang = 'fr'
    is_nsfw = True
    long_strip_genres = ['Webtoon', ]

    base_url = 'https://www.mangakawaii.io'
    search_url = base_url + '/recherche-manga'
    manga_list_url = base_url + '/filterMangaList'
    manga_list_referer_url = base_url + '/liste-manga'
    manga_url = base_url + '/manga/{0}'
    chapter_url = base_url + '/manga/{0}/{1}/{2}/1'
    chapters_url = base_url + '/loadChapter?page={0}'
    cdn_base_url = 'https://cdn.mangakawaii.pics'
    image_url = cdn_base_url + '/uploads/manga/{0}/chapters_{1}/{2}/{3}?{4}'
    cover_url = cdn_base_url + '/uploads/manga/{0}/cover/cover_250x350.jpg'

    csrf_token = None
    is_lang_set = False

    def __init__(self):
        if self.session is None:
            self.session = cloudscraper.create_scraper()
            cookie = requests.cookies.create_cookie(
                name='mk_search_type',
                value='manga',
                domain=urlparse(self.base_url).netloc,
                path='/',
                expires=None,
            )
            self.session.cookies.set_cookie(cookie)
            cookie = requests.cookies.create_cookie(
                name='mk_cookie_consent',
                value='1',
                domain=urlparse(self.base_url).netloc,
                path='/',
                expires=None,
            )
            self.session.cookies.set_cookie(cookie)

            self.session.headers.update({'User-Agent': USER_AGENT})

    @set_lang
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

        self.csrf_token = soup.select_one('meta[name="csrf-token"]')['content']

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

        data['name'] = soup.find('h1').text.strip()
        if data.get('cover') is None:
            data['cover'] = self.cover_url.format(data['slug'])

        # Details
        elements = soup.find('div', class_='col-md-8 mt-4 mt-md-0').find_all('dl')
        for element in elements:
            label = element.dt.text.strip()

            if label.startswith(('Author', 'Auteur', 'Artist', 'Artiste')):
                value = element.dd.span.text.strip()
                for t in value.split(','):
                    t = t.strip()
                    if t not in data['authors']:
                        data['authors'].append(t)

            elif label.startswith('Scantrad'):
                for a_element in element.dd.find_all('a', itemprop='name'):
                    data['scanlators'].append(a_element.text.replace('[', '').replace(']', '').strip())

            elif label.startswith('Genres'):
                a_elements = element.dd.find_all('a')
                data['genres'] = [a_element.text.strip() for a_element in a_elements]

            elif label.startswith(('Status', 'Statut')):
                status = element.dd.span.text.strip().lower()
                if status in ('ongoing', 'en cours'):
                    data['status'] = 'ongoing'
                elif status in ('completed', 'terminé'):
                    data['status'] = 'complete'
                elif status in ('abandoned', 'abandonné'):
                    data['status'] = 'suspended'
                elif status in ('paused', 'en pause'):
                    data['status'] = 'hiatus'

            elif label.startswith(('Summary', 'Description')):
                data['synopsis'] = element.dd.text.strip()

        #
        # Chapters
        # They are displayed in reverse order and loaded by page (if many)
        #
        # First, we get the oeuvreId
        oeuvre_id = None
        for script_element in reversed(soup.find_all('script')):
            script = script_element.string
            if not script or not script.strip().startswith('var ENDPOINT'):
                continue

            for line in script.split('\n'):
                line = line.strip()
                if not line.startswith('var oeuvreId'):
                    continue

                oeuvre_id = line.split("'")[-2]
                break

            break

        # Next, we retrieve fisrt chapters available in page's HTML
        for tr_element in soup.find('table', class_='table--manga').find_all('tr'):
            td_element = tr_element.find('td', class_='table__chapter')
            if not td_element:
                continue

            date_element = tr_element.find('td', class_='table__date')
            if date_element.div:
                date_element.div.extract()

            data['chapters'].append(dict(
                slug=td_element.a.get('href').strip().split('/')[-1],
                title=' '.join(td_element.a.span.text.strip().split()),
                date=convert_date_string(date_element.text.strip(), format='%d.%m.%Y'),
            ))

        # Finally, we recursively retrieve other chapters by page (via a web service)
        data['chapters'] += self.get_manga_chapters_data(data['slug'], oeuvre_id)
        data['chapters'].reverse()

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(manga_slug, self.lang, chapter_slug))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )
        for script_element in reversed(soup.find_all('script')):
            script = script_element.string
            if not script or not script.strip().startswith('var title'):
                continue

            for line in script.split('\n'):
                line = line.strip()
                if not line.startswith('var pages'):
                    continue

                pages = json.loads(line[12:-1])
                for index, page in enumerate(pages):
                    data['pages'].append(dict(
                        slug=None,
                        image=page['page_image'],
                        index=index,
                        version=page['page_version'],
                    ))

                break

        return data

    def get_manga_chapters_data(self, manga_slug, oeuvre_id, page=2):
        r = self.session_post(
            self.chapters_url.format(page),
            data=dict(
                oeuvreType='manga',
                oeuvreId=oeuvre_id,
                oeuvreSlug=manga_slug,
                oeuvreDownload='0',
            ),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Referer': self.manga_url.format(manga_slug),
                'X-CSRF-TOKEN': self.csrf_token,
                'X-Requested-With': 'XMLHttpRequest',
            }
        )
        if r.status_code != 200:
            return []

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return []

        soup = BeautifulSoup(r.content, 'html.parser')

        chapters = []
        for tr_element in soup.find_all('tr'):
            td_element = tr_element.find('td', class_='table__chapter')
            if not td_element:
                continue

            date_element = tr_element.find('td', class_='table__date')
            if date_element.div:
                date_element.div.extract()

            chapters.append(dict(
                slug=td_element.a.get('href').strip().split('/')[-1],
                title=' '.join(td_element.a.span.text.strip().split()),
                date=convert_date_string(date_element.text.strip(), format='%d.%m.%Y'),
            ))

        chapters += self.get_manga_chapters_data(manga_slug, oeuvre_id, page + 1)

        return chapters

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            self.image_url.format(manga_slug, self.lang, chapter_slug, page['image'], page['version']),
            headers={
                'Referer': self.base_url,
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
            name=page['image'].split('?')[0].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_manga_list(self, orderby):
        """
        Returns manga list sorted
        """
        params = dict(
            page=1,
            cat='',
            alpha='',
            asc='false',
            author='',
        )
        params['sortBy'] = 'views' if orderby == 'populars' else 'last_updated'

        r = self.session_get(
            self.manga_list_url,
            params=params,
            headers={
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': self.manga_list_url,
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/plain':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for element in soup.find_all('div', class_='media-thumbnail'):
            results.append(dict(
                name=element.find('div', class_='media-thumbnail__overlay').find('h3').text.strip(),
                slug=element.find('a').get('href').split('/')[-1],
            ))

        return results

    @set_lang
    def get_latest_updates(self):
        """
        Returns latest updates
        """
        return self.get_manga_list('latest')

    @set_lang
    def get_most_populars(self):
        """
        Returns list of most viewed manga
        """
        return self.get_manga_list('populars')

    @set_lang
    def search(self, term):
        r = self.session_get(
            self.search_url,
            params=dict(query=term),
            headers={
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': self.base_url,
            }
        )

        if r.status_code == 200:
            try:
                # Returned data for each manga:
                # value: name of the manga
                # slug: slug of the manga
                # imageUrl: cover of the manga
                data = r.json()['suggestions']

                results = []
                for item in data:
                    results.append(dict(
                        slug=item['slug'],
                        name=item['value'],
                    ))
            except Exception:
                return None
            else:
                return results

        return None


class Mangakawaii_en(Mangakawaii):
    id = 'mangakawaii_en'
    lang = 'en'
