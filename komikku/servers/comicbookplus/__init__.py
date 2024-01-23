# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import logging
import requests
from urllib.parse import parse_qs
from urllib.parse import urlparse

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import search_duckduckgo

logger = logging.getLogger('komikku.servers.comicbookplus')


class Comicbookplus(Server):
    id = 'comicbookplus'
    name = 'Comic Book Plus'
    lang = 'en'

    base_url = 'https://comicbookplus.com'
    latest_updates_url = base_url + '/?cbplus=latestuploads_s_s_0'
    most_populars_url = base_url + '/?cbplus=mostviewed_s_s_0'
    manga_url = base_url + '/?cid={0}'
    chapter_url = base_url + '/?dlid={0}'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    @classmethod
    def get_manga_initial_data_from_url(cls, url):
        qs = parse_qs(urlparse(url).query)
        return dict(slug=qs['cid'][0])

    def get_manga_data(self, initial_data):
        """
        Returns comic data by scraping comic HTML page content

        Initial data should contain at least comic's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Comic slug is missing in initial data'

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
            status='complete',
            chapters=[],
            server_id=self.id,
            synopsis=None,
        ))

        cards_elements = soup.select('.introtext')

        data['name'] = soup.select_one('.breadcrumbs > span:last-child').text.strip()
        data['cover'] = cards_elements[0].img.get('src')

        # Details
        if cards_elements[0].table:
            for tr_element in cards_elements[0].table.find_all('tr'):
                td_elements = tr_element.find_all('td')
                label = td_elements[0].text.strip()

                if label.startswith('Categories'):
                    for a_element in td_elements[1].find_all('a'):
                        data['genres'].append(a_element.text.strip())

        if len(cards_elements) == 2:
            data['synopsis'] = cards_elements[1].text.strip()

        # Chapters
        def get_volumes(page=0):
            nonlocal soup

            if page > 0:
                r = self.session_get(self.manga_url.format(initial_data['slug']) + f'&limit={page * 100}')

                soup = BeautifulSoup(r.text, 'lxml')

            chapters_element = soup.find('table', class_='catlistings')
            if chapters_element:
                for tr_element in chapters_element.find_all('tr', class_='overrow'):
                    tds_elements = tr_element.find_all('td')

                    data['chapters'].append(dict(
                        title=tds_elements[2].a.text.strip(),
                        slug=parse_qs(urlparse(tds_elements[2].a.get('href')).query)['dlid'][0],
                        date=convert_date_string(tds_elements[5].text.strip(), format='%b %d, %Y'),
                    ))

        get_volumes()

        # Parse next volumes list pages if exist
        paging_element = soup.find('table', class_='catlistings').find('tr', class_='tablefooter')
        if paging_element:
            for page in range(1, len(paging_element.find_all('a')) + 1):
                get_volumes(page)

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url, decode=True):
        """
        Returns comic volume data by scraping volume HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(chapter_slug))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        url = soup.find('img', id='maincomic').get('src')
        split_url = url.split('/')
        base_url = '/'.join(split_url[:-1])
        extension = split_url[-1].split('.')[-1]

        data = dict(
            pages=[],
        )
        for option_element in soup.find('select', id='comicbookpageselect').find_all('option'):
            index = option_element.get('value')
            data['pages'].append(dict(
                slug=None,
                image=f'{base_url}/{index}.{extension}',
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns volume page scan (image) content
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
            name=page['image'].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns comic absolute URL
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self):
        """
        Returns latest uploads
        """
        r = self.session_get(self.latest_updates_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        cids = []
        for tr_element in soup.find('div', class_='mainbody').find_all('table')[1].find_all('tr')[1:]:
            a_element = tr_element.find_all('td')[1].a
            qs = parse_qs(urlparse(a_element.get('href')).query)

            if qs['cid'][0] in cids:
                continue

            cids.append(qs['cid'][0])
            results.append(dict(
                name=a_element.text.strip(),
                slug=qs['cid'][0],
            ))

        return results

    def get_most_populars(self):
        """
        Returns most viewed comics
        """
        r = self.session_get(self.most_populars_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        results = []
        cids = []
        for tr_element in soup.find('div', class_='mainbody').find('table').find_all('tr')[1:]:
            a_element = tr_element.find_all('td')[1].a
            qs = parse_qs(urlparse(a_element.get('href')).query)

            if qs['cid'][0] in cids:
                continue

            cids.append(qs['cid'][0])
            results.append(dict(
                name=a_element.text.strip(),
                slug=qs['cid'][0],
            ))

        return results

    def search(self, term):
        # Use DuckDuckGo Lite
        results = []
        for ddg_result in search_duckduckgo(urlparse(self.base_url).netloc, term):
            qs = parse_qs(urlparse(ddg_result['url']).query)
            if 'cid' not in qs:
                # Not a comic url
                continue

            # Remove ' - Comic Book Plus' at end of name
            name = ddg_result['name'].replace(' - Comic Book Plus', '')

            results.append(dict(
                name=name,
                slug=qs['cid'][0],
            ))

        return results
