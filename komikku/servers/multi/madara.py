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
# Leviatanscans [EN]
# Manga-Scantrad [FR]
# Mangas Origines [FR]
# Reaperscans [EN]
# Submanga [ES] (disabled)
# Wakascan [FR] (disabled)

from bs4 import BeautifulSoup
import datetime
from gettext import gettext as _
import logging
import requests

from komikku.models import Settings
from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.headless_browser import bypass_cloudflare_invisible_challenge
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import get_soup_element_inner_text

logger = logging.getLogger('komikku.servers.madara')


class Madara(Server):
    base_url: str = None
    chapters_url: str = None

    series_name: str = 'manga'
    date_format: str = '%B %d, %Y'

    def __init__(self):
        self.api_url = self.base_url + '/wp-admin/admin-ajax.php'
        self.manga_url = self.base_url + '/' + self.series_name + '/{0}/'
        self.chapter_url = self.base_url + '/' + self.series_name + '/{0}/{1}/?style=list'

        if not self.has_cloudflare_invisible_challenge:
            if self.session is None:
                self.session = requests.Session()
                self.session.headers.update({'User-Agent': USER_AGENT})
        else:
            self.session = None

    @bypass_cloudflare_invisible_challenge
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
                data['cover'] = cover_div.a.img.get('data-lazy-srcset')
                if data['cover']:
                    # data-lazy-srcset can contain several covers with sizes: url1 size1 url2 size2...
                    data['cover'] = data['cover'].split()[0]
            if data['cover'] is None:
                data['cover'] = cover_div.a.img.get('src')

        # Details
        for element in soup.find('div', class_='summary_content').find_all('div', class_='post-content_item'):
            label_element = element.find('div', class_='summary-heading')
            if not label_element:
                label_element = element.find('h5')
            if label_element:
                label = get_soup_element_inner_text(label_element)
            else:
                continue

            label = label.encode('ascii', 'ignore').decode('utf-8').strip()  # remove none-ASCII characters

            content_element = element.find('div', class_='summary-content')
            if content_element:
                content = content_element.text.strip()

            if label.startswith(('Author', 'Artist', 'Auteur', 'Autor', 'Artista', 'Yazar', 'Sanatçı', 'Çizer', 'الرسام', 'المؤلف', 'Автор', 'Художник')):
                for author in content.split(','):
                    author = author.strip()
                    if author in ('', 'Updating'):
                        continue
                    if author not in data['authors']:
                        data['authors'].append(author)
            elif label.startswith(('Team', 'Tradutor', 'Revisor')):
                for scanlator in content.split(','):
                    scanlator = scanlator.strip()
                    if scanlator == '' or scanlator in data['scanlators']:
                        continue
                    data['scanlators'].append(scanlator)
            elif label.startswith(('Genre', 'Gênero', 'Tür', 'Kategoriler', 'التصنيف', 'Жанр')):
                for genre in content.split(','):
                    genre = genre.strip()
                    if genre == '':
                        continue
                    data['genres'].append(genre)
            elif label.startswith(('Status', 'État', 'Statut', 'STATUS', 'Durum', 'الحالة', 'Статус')):
                status = content.encode('ascii', 'ignore').decode('utf-8').strip()

                if status in ('Completed', 'Terminé', 'Completé', 'Completo', 'Concluído', 'Tamamlandı', 'مكتملة', 'Закончена'):
                    data['status'] = 'complete'
                elif status in ('OnGoing', 'En Cours', 'En cours', 'Updating', 'Devam Ediyor', 'Em Lançamento', 'Em andamento', 'مستمرة', 'Продолжается', 'Выпускается'):
                    data['status'] = 'ongoing'
                elif status in ('On Hold', 'En pause'):
                    data['status'] = 'hiatus'
            elif label.startswith(('Summary')):
                # In case of synopsis has been moved with details
                data['synopsis'] = element.find('p').text.strip()

        summary_container = soup.find('div', class_=['summary__content', 'manga-excerpt'])
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
                        'Origin': self.base_url,
                        'Referer': self.manga_url.format(data['slug']),
                        'X-Requested-With': 'XMLHttpRequest',
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
                        'Origin': self.base_url,
                        'Referer': self.manga_url.format(data['slug']),
                        'X-rRquested-With': 'XMLHttpRequest',
                    }
                )

            soup = BeautifulSoup(r.text, 'html.parser')

        elements = soup.find_all('li', class_='wp-manga-chapter')
        for element in reversed(elements):
            a_element = element.a
            date_element = element.find(class_='chapter-release-date').extract()
            if view_element := element.find(class_='view'):
                view_element.extract()

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

    @bypass_cloudflare_invisible_challenge
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

    @bypass_cloudflare_invisible_challenge
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

    @bypass_cloudflare_invisible_challenge
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


class Madara2(Madara):
    filters = [
        {
            'key': 'nsfw',
            'type': 'checkbox',
            'name': _('NSFW Content'),
            'description': _('Whether to show manga containing NSFW content'),
            'default': False,
        },
    ]

    def __init__(self):
        super().__init__()

        # Update NSFW filter default value according to current settings
        if Settings.instance:
            self.filters[0]['default'] = Settings.get_default().nsfw_content

    @bypass_cloudflare_invisible_challenge
    def get_most_populars(self, nsfw):
        """
        Returns list of most viewed manga
        """
        r = self.session_get(f'{self.base_url}/', params=dict(
            s='',
            post_type='wp-manga',
            op='',
            author='',
            artist='',
            release='',
            adult='' if nsfw else 0
        ))
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

    @bypass_cloudflare_invisible_challenge
    def search(self, term, nsfw):
        r = self.session_post(
            self.api_url,
            data={
                'action': 'wp-manga-search-manga',
                'title': term,
            },
            headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        data = r.json()

        if not data['success']:
            return None

        results = []
        for item in data['data']:
            if item['type'] != 'manga':
                continue

            results.append(dict(
                slug=item['url'].split('/')[-2],
                name=item['title'],
            ))

        return results
