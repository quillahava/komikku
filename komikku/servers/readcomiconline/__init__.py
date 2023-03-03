# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import logging
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT_MOBILE
from komikku.servers.utils import get_buffer_mime_type
from komikku.webview import get_page_html

headers = {
    'User-Agent': USER_AGENT_MOBILE,
    'Origin': 'https://readcomiconline.li',
}

logger = logging.getLogger('komikku.servers.readcomiconline')


class Readcomiconline(Server):
    id = 'readcomiconline'
    name = 'Read Comic Online'
    lang = 'en'
    is_nsfw = True

    base_url = 'https://readcomiconline.li'
    latest_updates_url = base_url + '/ComicList/LatestUpdate'
    most_populars_url = base_url + '/ComicList/MostPopular'
    search_url = base_url + '/Search/SearchSuggest'
    manga_url = base_url + '/Comic/{0}'
    chapter_url = base_url + '/Comic/{0}/{1}?readType=1'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT_MOBILE})

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

        soup = BeautifulSoup(r.content, 'html.parser')

        info_elements = soup.select_one('div.col.info')

        data['name'] = soup.select('.heading h3')[0].text.strip()
        cover_path = soup.select_one('div.col.cover img').get('src')
        if cover_path.startswith('http'):
            data['cover'] = cover_path
        else:
            data['cover'] = '{0}{1}'.format(self.base_url, cover_path)

        for p_element in info_elements.find_all('p'):
            if not p_element.span:
                continue

            span_element = p_element.span.extract()
            label = span_element.text.strip()

            if label.startswith('Genres'):
                data['genres'] = [a_element.text.strip() for a_element in p_element.find_all('a')]

            elif label.startswith(('Writer', 'Artist')):
                for a_element in p_element.find_all('a'):
                    value = a_element.text.strip()
                    if value not in data['authors']:
                        data['authors'].append(value)

            elif label.startswith('Status'):
                value = p_element.text.strip()
                if 'Completed' in value:
                    data['status'] = 'complete'
                elif 'Ongoing' in value:
                    data['status'] = 'ongoing'

        data['synopsis'] = soup.select_one('div.main > div > div:nth-child(4) > div:nth-child(3)').text.strip()

        # Chapters (Issues)
        for li_element in reversed(soup.find('ul', class_='list').find_all('li')):
            data['chapters'].append(dict(
                slug=li_element.a.get('href').split('?')[0].split('/')[-1],
                title=li_element.a.text.strip(),
                date=None,  # Not available in mobile version
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns comic chapter data

        Currently, only pages are expected.
        """
        # Code to wait until all images URLs are inserted in DOM
        js = """
            let count = 0;
            const checkReady = setInterval(() => {
                count += 1;
                if (count > 100) {
                    // Abort after 100 iterations (10s)
                    clearInterval(checkReady);
                    document.title = 'abort';
                    return;
                }
                if (document.querySelectorAll('#divImage img[src^="http"]').length === document.querySelectorAll('#divImage img').length) {
                    clearInterval(checkReady);
                    document.title = 'ready';
                }
            }, 100);
        """
        html = get_page_html(self.chapter_url.format(manga_slug, chapter_slug), user_agent=USER_AGENT_MOBILE, wait_js_code=js)
        soup = BeautifulSoup(html, 'html.parser')

        data = dict(
            pages=[],
        )
        for index, img_element in enumerate(soup.select('#divImage img')):
            data['pages'].append(dict(
                image=img_element.get('src'),
                slug=None,
                index=index + 1,
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
            name=f"{page['index']}.{mime_type.split('/')[1]}",
        )

    def get_manga_url(self, slug, url):
        """
        Returns comic absolute URL
        """
        return self.manga_url.format(slug)

    def get_manga_list(self, orderby):
        results = []

        if orderby == 'populars':
            r = self.session.get(self.most_populars_url)
        else:
            r = self.session.get(self.latest_updates_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'html.parser')

        for element in soup.find('div', class_='item-list').find_all(class_='info'):
            a_element = element.p.a
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
            ))

        return results

    def get_latest_updates(self):
        """
        Returns latest updates
        """
        return self.get_manga_list(orderby='latest')

    def get_most_populars(self):
        """
        Returns most popular comics
        """
        return self.get_manga_list(orderby='populars')

    def search(self, term):
        results = []
        term = term.lower()

        r = self.session.post(
            self.search_url,
            data=dict(
                type='Comic',
                keyword=term
            ),
            headers={
                'x-requested-with': 'XMLHttpRequest',
                'referer': self.base_url
            }
        )
        if r.status_code != 200:
            return None
        if not r.text:
            # No results
            return results

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'html.parser')

        for a_element in soup:
            if not a_element.get('href'):
                continue

            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
            ))

        return results
