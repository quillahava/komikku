# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import requests
from urllib.parse import parse_qs
from urllib.parse import urlparse

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Xoxocomics(Server):
    id = 'xoxocomics'
    name = 'Xoxocomics'
    lang = 'en'
    is_nsfw = True

    base_url = 'https://xoxocomic.com'
    latest_updates_url = base_url + '/comic-update'
    most_populars_url = base_url + '/popular-comic'
    search_url = base_url + '/search-comic'
    manga_url = base_url + '/comic/{0}?page={1}'
    chapter_url = base_url + '/comic/{0}/{1}/all'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = {
                'User-Agent': USER_AGENT,
                'Origin': self.base_url,
            }

    def get_manga_data(self, initial_data):
        """
        Returns comic data by scraping manga HTML page content

        Initial data should contain at least comic's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug'], 1))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],  # not available
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        soup = BeautifulSoup(r.content, 'lxml')

        data['name'] = soup.find('ul', class_='breadcrumb').find_all('a')[-1].text.strip()
        data['cover'] = soup.find(id='item-detail').find('div', class_="col-image").img.get('src')

        for li_element in soup.find('ul', class_='list-info').find_all('li'):
            if 'author' in li_element.get('class'):
                data['authors'] = [author.strip() for author in li_element.select_one('p:last-child').text.split('-')]

            elif 'kind' in li_element.get('class'):
                data['genres'] = [a_element.text.strip() for a_element in li_element.find_all('a')]

            elif 'status' in li_element.get('class'):
                status = li_element.find_all('p')[-1].text.strip()
                if status == 'Completed':
                    data['status'] = 'complete'
                elif status == 'Ongoing':
                    data['status'] = 'ongoing'

        data['synopsis'] = soup.find('div', class_='detail-content').p.text.strip()

        # Chapters
        def walk_chapters_pages(num=None, soup=None):
            if soup is None and num is not None:
                r = self.session_get(self.manga_url.format(initial_data['slug'], num))
                if r.status_code != 200:
                    return None

                mime_type = get_buffer_mime_type(r.content)
                if mime_type != 'text/html':
                    return None

                soup = BeautifulSoup(r.content, 'lxml')

            for li_element in soup.find(id='nt_listchapter').find('ul').find_all('li'):
                if 'heading' in li_element.get('class'):
                    continue

                col_elements = li_element.find_all('div', recursive=False)

                data['chapters'].append(dict(
                    slug=col_elements[0].a.get('href').split('/')[-1],
                    title=col_elements[0].a.text.strip(),
                    date=convert_date_string(col_elements[1].text.strip(), '%m/%d/%Y'),
                ))

            if next_element := soup.find('a', rel='next'):
                next_url = next_element.get('href')
                next_num = parse_qs(urlparse(next_url).query)['page'][0]
                walk_chapters_pages(num=next_num)

        walk_chapters_pages(soup=soup)
        data['chapters'] = list(reversed(data['chapters']))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns comic chapter data

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
        for index, element in enumerate(soup.find_all(class_='page-chapter')):
            data['pages'].append(dict(
                slug=None,
                image=element.img.get('data-original'),
                index=index + 1,  # Added 2023-06-13
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
            name=f'{page["index"]:04d}.{mime_type.split("/")[-1]}' if page.get('index') else page['image'].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns comic absolute URL
        """
        return self.manga_url.format(slug, 1)

    def get_latest_updates(self):
        """
        Returns latest updates
        """
        results = []

        r = self.session.get(self.latest_updates_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'lxml')

        for a_element in soup.select('.list-chapter .row h3 > a'):
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
            ))

        return results

    def get_most_populars(self):
        """
        Returns most popular comics list
        """
        results = []

        r = self.session.get(self.most_populars_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'lxml')

        for element in soup.select('.items figure'):
            a_element = element.select_one('figcaption > h3 > a')
            img_element = element.select_one('.image > a > img')
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
                cover=img_element.get('data-original'),
            ))

        return results

    def search(self, term):
        results = []
        term = term.lower()

        r = self.session.get(self.search_url, params=dict(keyword=term))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'lxml')

        for element in soup.select('figure'):
            a_element = element.select_one('figcaption > h3 > a')
            img_element = element.select_one('.image > a > img')
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
                cover=img_element.get('data-original'),
            ))

        return results
