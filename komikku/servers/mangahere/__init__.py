# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import json
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.webview import eval_js


class Mangahere(Server):
    id = 'mangahere'
    name = 'MangaHere'
    lang = 'en'

    base_url = 'https://www.mangahere.cc'
    search_url = base_url + '/search'
    latest_updates_url = base_url + '/latest/'
    most_populars_url = base_url + '/ranking/'
    manga_url = base_url + '/manga/{0}/'
    chapter_url = base_url + '/manga/{0}/{1}/'
    page_url = base_url + '/manga/{0}/{1}/{2}.html'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = {
                'User-Agent': USER_AGENT,
            }

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        if r.url.startswith(self.search_url):
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
            cover=None,
        ))

        data['name'] = soup.select_one('.detail-info-right-title-font').text.strip()
        data['cover'] = soup.select_one('.detail-info-cover-img').get('src')

        # Details
        status = soup.select_one('.detail-info-right-title-tip').text.strip().lower()
        data['status'] = 'ongoing' if status == 'ongoing' else 'complete'
        for a_element in soup.select('.detail-info-right-say a'):
            data['authors'].append(a_element.text.strip())
        for a_element in soup.select('.detail-info-right-tag-list a'):
            data['genres'].append(a_element.text.strip())

        # Synopsis
        data['synopsis'] = soup.select_one('.detail-info-right-content').text.strip()

        # Chapters
        for a_element in reversed(soup.select('.detail-main-list > li > a')):
            data['chapters'].append(dict(
                slug='/'.join(a_element.get('href').split('/')[3:-1]),  # cXXX or vYY/cXXX
                title=a_element.get('title').replace(data['name'], '').strip(),
                date=convert_date_string(a_element.select_one('.title2').text.strip(), format='%b %d,%Y'),
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

        soup = BeautifulSoup(r.text, 'html.parser')

        for script_element in soup.find_all('script'):
            script = script_element.string
            if script is None:
                continue

            if script.strip().startswith('eval(function(p,a,c,k,e,d)'):
                js_code = 'pasglop = ' + script.strip()[5:-1] + '; pasglop'

            elif 'var chapterid' in script:
                # Get chapter ID, required with page by page reader
                for line in script.split(';'):
                    if not line.strip().startswith('var imagecount'):
                        continue

                    nb_pages = int(line.strip().split('=')[-1].strip())
                    break

        data = dict(
            pages=[],
        )

        if len(soup.select('.reader-main > div')) == 0:
            # Webtoon reader
            res = eval_js(js_code)
            # We obtain something like this
            # var newImgs=['url1','url2',...];blabla...;
            pages_urls = json.loads(res[12:].split(';')[0].replace("'", '"'))

            for url in pages_urls:
                data['pages'].append(dict(
                    image=f'https:{url}',
                ))
        else:
            # Page by page reader
            for index in range(1, nb_pages + 1):
                data['pages'].append(dict(
                    index=index,
                ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        if page.get('index'):
            index = page['index']
            r = self.session_get(self.page_url.format(manga_slug, chapter_slug, index))
            if r.status_code != 200:
                return None

            mime_type = get_buffer_mime_type(r.content)
            if mime_type != 'text/html':
                return None

            soup = BeautifulSoup(r.text, 'html.parser')

            # We need a secret key and the chapter ID
            for script_element in soup.find_all('script'):
                script = script_element.string
                if script is None:
                    continue

                if script.strip().startswith('eval(function(p,a,c,k,e,d)'):
                    js_code = 'pasglop = ' + script.strip()[5:-1] + '; pasglop'

                elif 'var chapterid' in script:
                    # Get chapter ID
                    for line in script.split(';'):
                        if line.strip().startswith('var chapterid'):
                            cid = line.strip().split('=')[-1].strip()
                            break

            res = eval_js(js_code)
            # We obtain something like this
            # var guidkey=''+'3'+'a'+'e'+'d'+'6'+'a'+'a'+'6'+'1'+'0'+'4'+'e'+'7'+'2'+'3'+'e';blabla...;
            key = res[13:].split(';')[0][:-1].replace("'+'", '')

            r = self.session_get(
                self.chapter_url.format(manga_slug, chapter_slug) + f'chapterfun.ashx?cid={cid}&page={index}&key={key}',
                headers={
                    'Referer': self.page_url.format(manga_slug, chapter_slug, index),
                    'X-Requested-With': 'XMLHttpRequest',
                }
            )

            js_code = 'pasglop = ' + r.text[5:-2] + '; pasglop'
            res = eval_js(js_code)
            # We obtain something like this
            # function dm5imagefun(){var pix="//the_base_url";var pvalue=["path_image","path_next_image"];blabla...;
            base_url = res[23:-1].split(';')[0][9:-1]
            images = json.loads(res.split(';')[1][11:])

            url = f'https:{base_url}{images[0]}'
        else:
            url = page['image']

        r = self.session_get(url, headers={'Referer': self.base_url})
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=url.split('/')[-1].split('_')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_latest_updates(self):
        """
        Returns Latest Upadtes
        """
        return self.search(None, orderby='latest')

    def get_most_populars(self):
        """
        Returns Most Popular
        """
        return self.search(None, orderby='populars')

    def search(self, term, orderby=None):
        if term:
            r = self.session_get(self.search_url, params=dict(title=term))
        elif orderby == 'latest':
            r = self.session_get(self.latest_updates_url)
        elif orderby == 'populars':
            r = self.session_get(self.most_populars_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for li_element in soup.select('.line-list > div> ul > li'):
            results.append(dict(
                slug=li_element.a.get('href').split('/')[-2],
                name=li_element.a.get('title').strip(),
                cover=li_element.a.img.get('src'),
            ))

        return results
