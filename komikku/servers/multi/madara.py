# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Madara – WordPress Theme for Manga

# Supported servers:
# 24hRomance [EN] (disabled)
# 3asq [AR]
# AkuManga [AR] (disabled)
# Aloalivn [EN] (disabled)
# Apoll Comics [ES]
# ArazNovel [TR] (disabled)
# Argos Scan [PT] (disabled)
# Atikrost [TR] (disabled)
# Best Manga [RU]
# Colored Council [EN] (disabled)
# Fr-Scan (Id frdashscan) [FR]
# Leomanga [ES] (disabled)
# Leviatanscans [EN]
# Manga-Scantrad [FR]
# Mangas Origines [FR]
# Manhwa Hentai [EN]
# Phoenix Fansub [ES] (disabled)
# Reaperscans [EN/AR/FR/ID/TR]
# Submanga [ES] (disabled)
# ToonGod [EN]
# Toonily [EN]
# Wakascan [FR] (disabled)

from bs4 import BeautifulSoup
import datetime
from gettext import gettext as _
import logging
import requests

from komikku.models import Settings
from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import get_soup_element_inner_text
from komikku.servers.utils import remove_emoji_from_string
from komikku.webview import bypass_cf

logger = logging.getLogger('komikku.servers.madara')


class Madara(Server):
    base_url: str = None
    chapter_url: str = None
    chapters_url: str = None

    date_format: str = '%B %d, %Y'
    medium: str = 'manga'
    series_name: str = 'manga'

    chapters_list_selector = '#manga-chapters-holder'
    details_authors_selector = '.author-content a, .artist-content a'
    details_scanlators_selector = None
    details_genres_selector = '.genres-content a'
    details_status_selector = '.post-status .post-content_item:nth-child(2) .summary-content'
    details_synopsis_selector = '.summary__content'
    results_selector = '.row'
    result_name_slug_selector = '.post-title a'
    result_cover_selector = '.tab-thumb img'

    def __init__(self):
        self.api_url = self.base_url + '/wp-admin/admin-ajax.php'
        self.manga_url = self.base_url + '/' + self.series_name + '/{0}/'
        if self.chapter_url is None:
            self.chapter_url = self.base_url + '/' + self.series_name + '/{0}/{1}/?style=list'

        if self.session is None and not self.has_cf:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': USER_AGENT})

    @bypass_cf
    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        r = self.session_get(
            self.manga_url.format(initial_data['slug']),
            headers={
                'Referer': self.base_url,
            }
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type not in ('text/html', 'text/plain'):
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
        if r.history and r.history[-1].status_code == 301:
            # Slug has changed
            data['slug'] = r.url.split('/')[-2]

        data['name'] = get_soup_element_inner_text(soup.find('h1'))
        if cover_div := soup.find('div', class_='summary_image'):
            data['cover'] = cover_div.a.img.get('data-src')
            if data['cover'] is None:
                data['cover'] = cover_div.a.img.get('data-lazy-src')
                if data['cover'] is None:
                    data['cover'] = cover_div.a.img.get('data-lazy-srcset')
                    if data['cover']:
                        # data-lazy-srcset can contain several covers with sizes: url1 size1 url2 size2...
                        data['cover'] = data['cover'].split()[0]
                    else:
                        data['cover'] = cover_div.a.img.get('src')

        # Details
        for element in soup.select(self.details_authors_selector):
            author = element.text.strip()
            if author not in data['authors']:
                data['authors'].append(author)

        if self.details_scanlators_selector:
            for element in soup.select(self.details_scanlators_selector):
                data['scanlators'].append(element.text.strip())

        for element in soup.select(self.details_genres_selector):
            genre = element.text.strip()
            if genre not in data['genres']:
                data['genres'].append(genre)

        if self.details_status_selector:
            if element := soup.select_one(self.details_status_selector):
                status = element.text.strip()
                # Remove emoji
                status = remove_emoji_from_string(status)

                if status in ('Completed', 'Terminé', 'Completé', 'Completo', 'Concluído', 'Tamamlandı', 'مكتملة', 'Закончена'):
                    data['status'] = 'complete'
                elif status in ('OnGoing', 'En Cours', 'En cours', 'Updating', 'Devam Ediyor', 'Em Lançamento', 'Em andamento', 'مستمرة', 'Продолжается', 'Выпускается'):
                    data['status'] = 'ongoing'
                elif status in ('On Hold', 'En pause'):
                    data['status'] = 'hiatus'

        if self.details_synopsis_selector:
            if summary_container := soup.select_one(self.details_synopsis_selector):
                if p_elements := summary_container.select('p'):
                    data['synopsis'] = '\n\n'.join([p_element.text.strip() for p_element in p_elements])
                else:
                    data['synopsis'] = summary_container.text.strip()

        # Chapters
        chapters_container = soup.select_one(self.chapters_list_selector)
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

            soup = BeautifulSoup(r.text, 'lxml')

        elements = soup.find_all('li', class_='wp-manga-chapter')
        for element in reversed(elements):
            if element.select_one('i.fa-lock'):
                # Skip premium chapter (LeviatanScans ES for ex.)
                continue

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

    @bypass_cf
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

        soup = BeautifulSoup(r.content, 'lxml')

        data = dict(
            pages=[],
        )
        for img_element in soup.select_one('.read-container, .reading-content').select('img'):
            if img_element.parent.name == 'noscript':
                # In case server uses a second <img> encapsulated in a <noscript> element
                continue

            img_url = img_element.get('data-src')
            if img_url is None:
                img_url = img_element.get('data-lazy-src')
                if img_url is None:
                    img_url = img_element.get('src')

            data['pages'].append(dict(
                slug=None,
                image=img_url.strip(),
            ))

        return data

    @bypass_cf
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
        Returns list of latest updates manga
        """
        return self.search('', orderby='latest')

    def get_most_populars(self):
        """
        Returns list of most viewed manga
        """
        return self.search('', orderby='populars')

    @bypass_cf
    def search(self, term, orderby=None):
        data = {
            'action': 'madara_load_more',
            'page': 0,
            'template': 'madara-core/content/content-search',
            'vars[orderby]': 'meta_value_num' if orderby else '',
            'vars[paged]': 0,
            'vars[template]': 'search',
            'vars[post_type]': 'wp-manga',
            'vars[post_status]': 'publish',
            'vars[manga_archives_item_layout]': 'default',
        }

        if self.medium:
            data['vars[meta_query][0][0][value]'] = self.medium  # allows to ignore novels
            data['vars[meta_query][0][orderby]'] = ''
            data['vars[meta_query][0][paged]'] = '0'
            data['vars[meta_query][0][template]'] = 'search'
            data['vars[meta_query][0][meta_query][relation]'] = 'AND'
            data['vars[meta_query][0][post_type]'] = 'wp-manga'
            data['vars[meta_query][0][post_status]'] = 'publish'
            data['vars[meta_query][relation]'] = 'AND'

        if orderby:
            data['vars[order]'] = 'desc'
            data['vars[posts_per_page]'] = 100
            if orderby == 'populars':
                data['vars[meta_key]'] = '_wp_manga_views'
            elif orderby == 'latest':
                data['vars[meta_key]'] = '_latest_update'
        else:
            data['vars[meta_query][0][s]'] = term
            data['vars[s]'] = term

        r = self.session_post(
            self.api_url,
            data=data,
            headers={
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': self.base_url
            }
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.select(self.results_selector):
            a_element = element.select_one(self.result_name_slug_selector)
            slug = a_element.get('href').split('/')[-2]
            name = a_element.text.strip()
            if not name or not slug:
                continue

            if cover_img := element.select_one(self.result_cover_selector):
                cover = cover_img.get('data-src')
                if cover is None:
                    cover = cover_img.get('src')

            results.append(dict(
                slug=slug,
                name=name,
                cover=cover,
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

    @bypass_cf
    def get_latest_updates(self, nsfw):
        """
        Returns list of latest updates manga
        """
        r = self.session_get(
            f'{self.base_url}/',
            params=dict(
                s='',
                post_type='wp-manga',
                op='',
                author='',
                artist='',
                release='',
                adult='' if nsfw else 0,
                m_orderby='new-manga',
            )
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.find_all('div', class_='post-title'):
            if not element.h3:
                continue
            a_element = element.h3.a
            results.append(dict(
                slug=a_element.get('href').split('/')[-2],
                name=a_element.text.strip(),
            ))

        return results

    @bypass_cf
    def get_most_populars(self, nsfw):
        """
        Returns list of most viewed manga
        """
        r = self.session_get(
            f'{self.base_url}/',
            params=dict(
                s='',
                post_type='wp-manga',
                op='',
                author='',
                artist='',
                release='',
                adult='' if nsfw else 0,
                m_orderby='views',
            )
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.find_all('div', class_='post-title'):
            if not element.h3:
                continue
            a_element = element.h3.a
            results.append(dict(
                slug=a_element.get('href').split('/')[-2],
                name=a_element.text.strip(),
            ))

        return results

    @bypass_cf
    def search(self, term, nsfw):
        r = self.session_post(
            self.api_url,
            data={
                'action': 'wp-manga-search-manga',
                'title': term,
            },
            headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Referer': self.base_url,
                'X-Requested-With': 'XMLHttpRequest',
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
