# Copyright (C) 2020-2024 GrownNed
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: GrownNed <grownned@gmail.com>

from bs4 import BeautifulSoup
import datetime
import json
import requests

from komikku.servers import Server
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Readmanga(Server):
    id = 'readmanga'
    name = 'Read Manga'
    lang = 'ru'
    is_nsfw = True

    base_url = 'https://readmanga.live'
    search_url = base_url + '/search/advancedResults'
    manga_url = base_url + '/{0}'
    chapter_url = manga_url + '/{1}?mtr=1'

    pages_js_start = 'rm_h.readerInit'
    pages_js_offset = 19
    remove_image_url_qs = True

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'User-Agent': 'arora'})

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

        info_element = soup.find('div', class_='leftContent')

        title_element = info_element.find('span', class_='name')
        data['name'] = title_element.text.strip()

        cover_element = info_element.find('img', attrs={'data-full': True})
        data['cover'] = cover_element.get('data-full')

        # Details
        elements = info_element.find('div', class_='subject-meta').find_all('p', recursive=False)

        if status_element := elements[0].span:
            status = status_element.text.strip()
            if 'продолжается' in status:
                data['status'] = 'ongoing'
            elif 'завершен' in status:
                data['status'] = 'complete'

        for element in elements[1:]:
            label_element = element.span
            if not label_element:
                continue
            label = label_element.text.strip()

            if label.startswith('Автор') or label.startswith('Сценарист') or label.startswith('Художник'):
                value = [author.text.strip() for author in element.find_all('a', class_='person-link')]
                data['authors'].extend(value)
            elif label.startswith('Переводчик'):
                value = [scanlator.text.strip() for scanlator in element.find_all('a', class_='person-link')]
                data['scanlators'].extend(value)
            elif label.startswith('Жанр'):
                value = [genre.text.strip() for genre in element.find_all('a', class_='element-link')]
                data['genres'].extend(value)

        # Synopsis
        data['synopsis'] = info_element.find('div', class_='manga-description').text.strip()

        # Chapters
        chapters_element = info_element.find('div', id='chapters-list', recursive=False)
        if not chapters_element:
            return data

        for element in reversed(chapters_element.table.find_all('tr', recursive=False)):
            a_element = element.find('a', class_='chapter-link')
            slug = a_element.get('href').split('/', 2)[2]
            title = a_element.find(text=True, recursive=False).strip()
            date = element.find('td', class_='text-right').text.strip()

            data['chapters'].append(dict(
                slug=slug,
                title=title,
                date=convert_date_string(date, format='%d.%m.%y'),
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

        data = dict(
            pages=[],
        )

        for script_element in soup.find_all('script'):
            script = script_element.string
            if not script or not script.strip().startswith('var prevLink'):
                continue

            for line in script.split('\n'):
                line = line.strip()
                if not line.startswith(self.pages_js_start):
                    continue

                pages_data = '[{0}]'.format(line[self.pages_js_offset:-2].replace('\'', '"'))
                urls = json.loads(pages_data)[0]
                for split_url in urls:
                    url = split_url[0] + split_url[2]
                    if not url.startswith('http'):
                        # Required by AllHentai
                        url = self.base_url.split('://')[0] + ':' + url
                    if self.remove_image_url_qs:
                        url = url.split('?')[0]

                    data['pages'].append(dict(
                        slug=None,
                        image=url,
                    ))
                break
            break

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            page['image'],
            headers={'Referer': self.base_url}
        )
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

    def get_most_populars(self):
        """
        Returns best noted manga
        """
        return self.search('', 'POPULARITY')

    def get_latest_updates(self):
        """
        Returns latest updated manga
        """
        return self.search('', 'DATE_UPDATE')

    def search(self, term, orderby='NAME'):
        r = self.session_get(
            self.search_url,
            params=dict(
                q=term,
                offset='',
                years=f'1950,{datetime.date.today().year + 1}',
                sortType=orderby,
            )
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type not in ('text/plain', 'text/html'):
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        for element in soup.select('.tile'):
            a_element = element.select_one('.desc > h3 > a')
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href')[1:],
                cover=element.select_one('.img img.img-fluid').get('data-original'),
            ))

        return sorted(results, key=lambda m: m['name'])


class Allhentai(Readmanga):
    id = 'allhentai:readmanga'
    name = 'AllHentai'
    is_nsfw = False
    is_nsfw_only = True
    # FIXME: requires to be logged in

    base_url = 'http://2023.allhen.online'
    search_url = base_url + '/search/advanced'
    manga_url = base_url + '/{0}'
    chapter_url = manga_url + '/{1}?mtr=1'

    remove_image_url_qs = False


class Mintmanga(Readmanga):
    id = 'mintmanga:readmanga'
    name = 'Mint Manga'
    is_nsfw = True

    # 16
    base_url = 'https://mintmanga.live'
    search_url = base_url + '/search/advancedResults'
    manga_url = base_url + '/{0}'
    chapter_url = manga_url + '/{1}?mtr=1'

    remove_image_url_qs = False


class Selfmanga(Readmanga):
    id = 'selfmanga:readmanga'
    name = 'Self Manga'
    is_nsfw = True

    base_url = 'https://selfmanga.live'
    search_url = base_url + '/search/advancedResults'
    manga_url = base_url + '/{0}'
    chapter_url = manga_url + '/{1}?mtr=1'

    remove_image_url_qs = False
