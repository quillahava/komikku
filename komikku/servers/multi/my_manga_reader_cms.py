# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# My Manga Reader CMS

# Supported servers:
# FR Scan [FR]
# Jpmangas [FR]
# Lelscan-VF [FR] (disabled)
# Leomanga [ES] (v1)
# Mangadoor [ES]
# Mangasin [ES]
# Read Comics Online [RU]
# Scan FR [FR]
# Scan OP [FR]
# ScanOnePiece [FR]
# Submanga [ES]

from bs4 import BeautifulSoup
import re
import requests
from urllib.parse import urljoin

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import get_soup_element_inner_text


class MyMangaReaderCMS(Server):
    base_url: str
    search_url: str
    most_populars_url: str
    manga_url: str
    chapter_url: str
    image_url: str
    cover_url: str

    search_query_param: str = 'query'

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

        data['name'] = soup.find('h2', class_=re.compile(r'widget-title|listmanga-header')).text.strip()
        data['cover'] = self.cover_url.format(data['slug'])

        # Details
        elements = soup.find('dl', class_='dl-horizontal').findChildren(recursive=False)
        for element in elements:
            if element.name not in ('dt', 'dd'):
                continue

            if element.name == 'dt':
                label = element.text.strip()
                continue

            if label.startswith(('Author', 'Auteur', 'Autor', 'Artist')):
                value = element.text.strip()
                for t in value.split(','):
                    t = t.strip()
                    if t not in data['authors']:
                        data['authors'].append(t)
            elif label.startswith(('Categories', 'Catégories', 'Categorías', 'Género', 'Tags')):
                data['genres'] = [a_element.text.strip() for a_element in element.find_all('a')]
            elif label.startswith(('Status', 'Statut', 'Estado')):
                value = element.text.strip().lower()
                if value in ('ongoing', 'en cours', 'en curso'):
                    data['status'] = 'ongoing'
                elif value in ('complete', 'terminé', 'completa'):
                    data['status'] = 'complete'

        synopsis_element = soup.find('div', class_='well').p
        if synopsis_element.p:
            # Difference encountered on `mangasin` server
            # Note: HTML is borken in this part, this is why we use html.parser above
            # Anyway, the retrieved synopsis is not entirely correct, there is a surplus of text.
            synopsis_element = synopsis_element.p
        data['synopsis'] = synopsis_element.text.strip()
        alert_element = soup.find('div', class_='alert-danger')
        if alert_element:
            data['synopsis'] += '\n\n' + alert_element.text.strip()

        # Chapters
        elements = soup.find('ul', class_=re.compile(r'chapter.*')).find_all('li', recursive=False)
        for element in reversed(elements):
            h5 = element.h5
            if not h5:
                continue

            if h5.eee:
                # Difference encountered on `mangasin` server
                slug = h5.eee.a.get('href').split('/')[-1]
                title = h5.eee.a.text.strip()
                date = element.div.div.text.strip().split()[0]
                date_format = '%Y-%m-%d'
            else:
                slug = h5.a.get('href').split('/')[-1]
                title = h5.a.text.strip()
                if h5.em and h5.em.text.strip():
                    title = '{0}: {1}'.format(title, h5.em.text.strip())
                date = element.div.div.text.strip()
                date_format = '%d %b. %Y'

            data['chapters'].append(dict(
                slug=slug,
                date=convert_date_string(date, format=date_format),
                title=title
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages (list of images filenames) are expected.
        """
        r = self.session_get(self.chapter_url.format(manga_slug, chapter_slug))
        if r is None:
            return None

        mime_type = get_buffer_mime_type(r.content)

        if r.status_code != 200 or mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        pages_imgs = soup.find('div', id='all').find_all('img')

        data = dict(
            pages=[],
        )
        for index, img in enumerate(pages_imgs):
            if self.image_url:
                slug = img.get('data-src').strip().split('/')[-1]
                image = None
            else:
                slug = None
                src = img.get('data-src').strip()
                if src.startswith('http'):
                    image = src
                elif src.startswith('//'):
                    image = 'https:' + src
                else:
                    image = urljoin(self.base_url, src.lstrip('/'))

            data['pages'].append(dict(
                slug=slug,
                image=image,
                index=index + 1,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        if page['slug']:
            r = self.session_get(self.image_url.format(manga_slug, chapter_slug, page['slug']))
        else:
            r = self.session_get(page['image'])
        if r is None or r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=page['slug'] if page['slug'] else '{0}.{1}'.format(page['index'], mime_type.split('/')[-1]),
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_most_populars(self):
        """
        Returns list of most viewed manga
        """
        r = self.session_get(self.most_populars_url)
        if r is None:
            return None

        mime_type = get_buffer_mime_type(r.content)

        if r.status_code != 200 or mime_type not in ('text/html', 'text/plain'):
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for a_element in soup.find_all('a', class_='chart-title'):
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
            ))

        return results

    def search(self, term):
        params = {}
        params[self.search_query_param] = term
        r = self.session_get(self.search_url, params=params)
        if r is None:
            return None

        if r.status_code == 200:
            try:
                # Returned data for each manga:
                # value: name of the manga
                # data: slug of the manga
                data = r.json()
                if 'suggestions' in data:
                    data = data['suggestions']

                results = []
                for item in data:
                    results.append(dict(
                        slug=item['data'],
                        name=item['value'],
                    ))

                return results
            except Exception:
                return None

        return None


class MyMangaReaderCMSv1(MyMangaReaderCMS):
    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug']))
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

        data['name'] = get_soup_element_inner_text(soup.find('div', class_='panel-heading').h3)
        data['cover'] = self.cover_url.format(data['slug'])

        # Details
        elements = soup.find('div', class_=['panel', 'panel-default']).find_all('span', class_='list-group-item')
        for element in elements:
            label = element.b.text.strip()
            element.b.extract()
            value = element.text.strip()

            if label.startswith(('Author', 'Auteur', 'Autor', 'Artist')):
                for author in value.split(','):
                    author = author.strip()
                    if author not in data['authors']:
                        data['authors'].append(author)
            elif label.startswith(('Categories', 'Catégories', 'Categorías', 'Género')):
                data['genres'] = [genre.strip() for genre in value.split(',')]
            elif label.startswith(('Status', 'Statut', 'Estado')):
                value = value.lower()
                if value in ('ongoing', 'en cours'):
                    data['status'] = 'ongoing'
                elif value in ('complete', 'terminé'):
                    data['status'] = 'complete'
            elif label.startswith('Resumen'):
                data['synopsis'] = value

        # Chapters
        elements = soup.find('div', class_='capitulos-list').find_all('tr')
        for element in reversed(elements):
            td_elements = element.find_all('td')

            data['chapters'].append(dict(
                slug=td_elements[0].a.get('href').split('/')[-1],
                date=convert_date_string(td_elements[1].text.strip(), format='%d %b. %Y'),
                title=td_elements[0].a.text.strip(),
            ))

        return data

    def get_most_populars(self):
        """
        Returns list of most viewed manga
        """
        r = self.session_get(self.most_populars_url)
        if r is None:
            return None

        mime_type = get_buffer_mime_type(r.content)

        if r.status_code != 200 or mime_type not in ('text/html', 'text/plain'):
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for element in soup.find_all('div', class_='thumbnail'):
            results.append(dict(
                name=element.a.img.get('alt').strip(),
                slug=element.a.get('href').split('/')[-1],
            ))

        return results
