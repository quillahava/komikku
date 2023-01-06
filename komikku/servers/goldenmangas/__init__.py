# -*- coding: utf-8 -*-

# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Goldenmangas(Server):
    id = 'goldenmangas'
    name = 'Golden Mangás'
    lang = 'pt_BR'

    base_url = 'https://goldenmangas.top'
    search_url = base_url + '/mangabr'
    manga_url = base_url + '/mangabr/{0}'
    chapter_url = base_url + '/mangabr/{0}/{1}'
    image_url = base_url + '/mm-admin/uploads/mangas/{0}/{1}/{2}'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': USER_AGENT,
            })

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug']))
        if r.status_code != 200:
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

        info_element = soup.select_one('div.container.manga > div.row')

        # Name & cover
        data['name'] = info_element.select_one('div.col-sm-8 > div.row > div.col-sm-8 > h2:nth-child(1)').text.strip()
        data['cover'] = '{0}{1}'.format(
            self.base_url,
            info_element.select_one('div.col-sm-8 > div.row > div.col-sm-4.text-right > img').get('src')
        )

        # Details
        for h5_element in info_element.select('div.col-sm-8 > div.row > div.col-sm-8 > h5'):
            label = h5_element.strong.text.strip().lower()

            if label.startswith('genero'):
                for a_element in h5_element.find_all('a'):
                    if genre := a_element.text.strip():
                        data['genres'].append(genre)

            elif label.startswith(('autor', 'artista')):
                for a_element in h5_element.find_all('a'):
                    author = a_element.text.strip()
                    if author and author not in data['authors']:
                        data['authors'].append(author)

            elif label.startswith('status'):
                status = h5_element.a.text.strip().lower()
                if status == 'completo':
                    data['status'] = 'complete'
                elif status == 'ativo':
                    data['status'] = 'ongoing'

        # Synopsis
        data['synopsis'] = info_element.find(id='manga_capitulo_descricao').text.strip()

        # Chapters
        for li_element in reversed(soup.find(id='capitulos').find_all('li')):
            title_element = li_element.select_one('a > div.col-sm-5')
            date_element = title_element.span.extract()
            if scanlator_element := li_element.select_one('div > a.label.label-default'):
                scanlator = scanlator_element.text.strip()

            data['chapters'].append(dict(
                slug=li_element.a.get('href').split('/')[-1],
                title=title_element.text.strip(),
                scanlators=[scanlator, ],
                date=convert_date_string(date_element.text.strip()[1:-1], format='%d/%m/%Y'),
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

        soup = BeautifulSoup(r.content, 'html.parser')

        data = dict(
            pages=[],
        )
        for img_element in soup.find_all('img', class_='img-manga'):
            data['pages'].append(dict(
                slug=img_element.get('src').split('/')[-1],
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(self.image_url.format(manga_slug, chapter_slug, page['slug']))
        if r.status_code != 200:
            return None

        buffer = r.content
        mime_type = get_buffer_mime_type(buffer)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=buffer,
            mime_type=mime_type,
            name=page['slug'],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self):
        r = self.session_get(self.base_url)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text.encode('utf-8'), 'html.parser', from_encoding='utf-8')

        results = []
        for a_element in soup.select('.atualizacao > a'):
            results.append(dict(
                name=a_element.find('h3').text.strip(),
                slug=a_element.get('href').split('/')[-1],
            ))

        return results

    def get_most_populars(self, types=None, statuses=None):
        r = self.session_get(self.base_url)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text.encode('utf-8'), 'html.parser', from_encoding='utf-8')

        results = []
        for a_element in soup.select('#capitulosdestaque > a'):
            results.append(dict(
                name=a_element.find_all('span')[-1].text.strip(),
                slug=a_element.get('href').split('/')[-2],
            ))

        return results

    def search(self, term, types=None, statuses=None, orderby=None):
        r = self.session_get(self.search_url, params=dict(busca=term))
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.content, 'html.parser')

        results = []
        for element in soup.find_all(class_='mangas'):
            results.append(dict(
                name=element.h3.text.strip(),
                slug=element.a.get('href').split('/')[-1],
            ))

        return results
