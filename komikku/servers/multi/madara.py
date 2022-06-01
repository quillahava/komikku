# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Madara – WordPress Theme for Manga

# Supported servers:
# 24hRomance [EN]
# AkuManga [AR]
# Aloalivn [EN] (disabled)
# Apoll Comics [ES]
# ArazNovel [TR]
# Argos Scan [PT] (disabled)
# Atikrost [TR]
# Best Manga [RU]
# Colored Council [EN]
# Leomanga [ES]
# Reaperscans [EN]
# Reaperscans [PT]
# Submanga [ES]
# Wakascan [FR] (disabled)

from bs4 import BeautifulSoup
import datetime
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import get_soup_element_inner_text


class Madara(Server):
    base_url: str = None
    chapters_url: str = None

    series_name: str = 'manga'
    date_format: str = '%B %d, %Y'

    def __init__(self):
        self.api_url = self.base_url + '/wp-admin/admin-ajax.php'
        self.manga_url = self.base_url + '/' + self.series_name + '/{0}/'
        self.chapter_url = self.base_url + '/' + self.series_name + '/{0}/{1}/?style=list'

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
        ))

        data['name'] = get_soup_element_inner_text(soup.find('h1'))
        if cover_div := soup.find('div', class_='summary_image'):
            data['cover'] = cover_div.a.img.get('data-src')
            if data['cover'] is None:
                data['cover'] = cover_div.a.img.get('src')

        # Details
        for element in soup.find('div', class_='summary_content').find_all('div', class_='post-content_item'):
            label = element.find('div', class_='summary-heading').text.strip()
            content_element = element.find('div', class_='summary-content')

            if label.startswith(('Author', 'Artist', 'Autor', 'Artista', 'Yazar', 'Sanatçı', 'Çizer', 'الرسام', 'المؤلف', 'Автор', 'Художник')):
                for author in content_element.text.strip().split(','):
                    author = author.strip()
                    if author in ('', 'Updating'):
                        continue
                    if author not in data['authors']:
                        data['authors'].append(author)
            elif label.startswith(('Tradutor', 'Revisor')):
                for scanlator in content_element.text.strip().split(','):
                    scanlator = scanlator.strip()
                    if scanlator == '' or scanlator in data['scanlators']:
                        continue
                    data['scanlators'].append(scanlator)
            elif label.startswith(('Genre', 'Gênero', 'Tür', 'Kategoriler', 'التصنيف', 'Жанр')):
                for genre in content_element.text.strip().split(','):
                    genre = genre.strip()
                    if genre == '':
                        continue
                    data['genres'].append(genre)
            elif label.startswith(('Status', 'Durum', 'الحالة', 'Статус')):
                status = content_element.text.strip()
                if status in ('Completed', 'Completo', 'Concluído', 'Tamamlandı', 'مكتملة', 'Закончена'):
                    data['status'] = 'complete'
                elif status in ('OnGoing', 'Updating', 'Devam Ediyor', 'Em Lançamento', 'Em andamento', 'مستمرة', 'Продолжается', 'Выпускается'):
                    data['status'] = 'ongoing'

        summary_container = soup.find('div', class_='summary__content')
        if summary_container:
            if p_elements := summary_container.find_all('p'):
                data['synopsis'] = '\n\n'.join([p_element.text.strip() for p_element in p_elements])
            else:
                data['synopsis'] = summary_container.text.strip()

        # Chapters
        chapters_container = soup.find('div', id='manga-chapters-holder')
        if chapters_container:
            # Chapters list is empty and is loaded via an Ajax call
            if self.chapters_url:
                r = self.session_post(
                    self.chapters_url.format(data['slug']),
                    headers={
                        'origin': self.base_url,
                        'referer': self.manga_url.format(data['slug']),
                        'x-requested-with': 'XMLHttpRequest',
                    }
                )
            else:
                r = self.session_post(
                    self.api_url,
                    data=dict(
                        action='manga_get_chapters',
                        manga=chapters_container.get('data-id'),
                    ),
                    headers={
                        'origin': self.base_url,
                        'referer': self.manga_url.format(data['slug']),
                        'x-requested-with': 'XMLHttpRequest',
                    }
                )

            soup = BeautifulSoup(r.text, 'html.parser')

        elements = soup.find_all('li', class_='wp-manga-chapter')
        for element in reversed(elements):
            a_element = element.a
            date_element = element.find(class_='chapter-release-date').extract()

            if date := date_element.text.strip():
                date = convert_date_string(date, format=self.date_format)
            else:
                date = datetime.date.today().strftime('%Y-%m-%d')

            data['chapters'].append(dict(
                slug=a_element.get('href').split('/')[-2],
                title=a_element.text.strip(),
                date=date,
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

        soup = BeautifulSoup(r.content, 'lxml')

        data = dict(
            pages=[],
        )
        for img_element in soup.find(class_='reading-content').find_all('img'):
            img_url = img_element.get('data-src')
            if img_url is None:
                img_url = img_element.get('src')

            data['pages'].append(dict(
                slug=None,
                image=img_url.strip(),
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

    def get_most_populars(self):
        """
        Returns list of most viewed manga
        """
        return self.search('', True)

    def search(self, term, populars=False):
        data = {
            'action': 'madara_load_more',
            'page': 0,
            'template': 'madara-core/content/content-archive' if populars else 'madara-core/content/content-search',
            'vars[orderby]': 'meta_value_num' if populars else '',
            'vars[paged]': 0,
            'vars[template]': 'archive' if populars else 'search',
            'vars[post_type]': 'wp-manga',
            'vars[post_status]': 'publish',
            'vars[manga_archives_item_layout]': 'default',

            'vars[meta_query][0][0][value]': 'manga',  # allows to ignore novels
            'vars[meta_query][0][orderby]': '',
            'vars[meta_query][0][paged]': '0',
            'vars[meta_query][0][template]': 'archive' if populars else 'search',
            'vars[meta_query][0][meta_query][relation]': 'AND',
            'vars[meta_query][0][post_type]': 'wp-manga',
            'vars[meta_query][0][post_status]': 'publish',
            'vars[meta_query][relation]': 'AND'
        }
        if populars:
            data['vars[order]'] = 'desc'
            data['vars[posts_per_page]'] = 100
            data['vars[meta_key]'] = '_wp_manga_views'
        else:
            data['vars[meta_query][0][s]'] = term
            data['vars[s]'] = term

        r = self.session_post(self.api_url, data=data, headers={
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': self.base_url
        })
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.find_all('div', class_='post-title'):
            a_element = element.h3.a
            results.append(dict(
                slug=a_element.get('href').split('/')[-2],
                name=a_element.text.strip(),
            ))

        return results
