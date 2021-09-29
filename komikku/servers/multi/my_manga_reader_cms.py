# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# My Manga Reader CMS

# Supported servers:
# Jpmangas [FR]: https://jpmangas.co
# Leomanga [ES]: https://leomanga.me V1
# Read Comics Online [RU]: https://readcomicsonline.ru
# ScanOnePiece [FR]: https://www.scan-vf.net

from bs4 import BeautifulSoup
import re
import requests

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
            elif label.startswith(('Categories', 'Catégories', 'Categorías')):
                data['genres'] = [a_element.text.strip() for a_element in element.find_all('a')]
            elif label.startswith(('Status', 'Statut', 'Estado')):
                value = element.text.strip().lower()
                if value in ('ongoing', 'en cours', 'en curso'):
                    data['status'] = 'ongoing'
                elif value in ('complete', 'terminé', 'completa'):
                    data['status'] = 'complete'

        data['synopsis'] = soup.find('div', class_='well').p.text.strip()
        alert_element = soup.find('div', class_='alert-danger')
        if alert_element:
            data['synopsis'] += '\n\n' + alert_element.text.strip()

        # Chapters
        elements = soup.find('ul', class_='chapters').find_all('li', recursive=False)
        for element in reversed(elements):
            h5 = element.h5
            if not h5:
                continue

            slug = h5.a.get('href').split('/')[-1]
            title = h5.a.text.strip()
            if h5.em:
                title = '{0}: {1}'.format(title, h5.em.text.strip())
            date = element.div.div

            data['chapters'].append(dict(
                slug=slug,
                date=convert_date_string(date.text.strip(), format='%d %b. %Y'),
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
                image = self.base_url + img.get('data-src')

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
        self.session_get(self.base_url)
        r = self.session_get(self.search_url, params=dict(query=term))
        if r is None:
            return None

        if r.status_code == 200:
            try:
                # Returned data for each manga:
                # value: name of the manga
                # data: slug of the manga
                data = r.json()['suggestions']

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
            elif label.startswith(('Categories', 'Catégories', 'Categorías')):
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
