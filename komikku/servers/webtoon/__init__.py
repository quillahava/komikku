# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _

from bs4 import BeautifulSoup
from functools import wraps
import requests
from urllib.parse import urlsplit

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers import USER_AGENT_MOBILE
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import get_soup_element_inner_text

LANGUAGES_CODES = dict(
    en='en',
    es='es',
    fr='fr',
    id='id',
    th='th',
    zh_Hant='zh-hant',  # diff
)

SERVER_NAME = 'WEBTOON'


def init_session(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        server = args[0]
        if not server._session_initialized:
            server.session_get(server.base_url + '/{0}/'.format(LANGUAGES_CODES[server.lang]))
            server._session_initialized = True

        return func(*args, **kwargs)

    return wrapper


class Webtoon(Server):
    id = 'webtoon'
    name = SERVER_NAME
    lang = 'en'

    base_url = 'https://www.webtoons.com'
    search_url = base_url + '/{0}/search'
    most_populars_url = base_url + '/{0}/top'
    manga_url = base_url + '{0}'
    chapters_url = 'https://m.webtoons.com{0}'
    chapter_url = base_url + '{0}'

    filters = [
        {
            'key': 'type',
            'type': 'select',
            'name': _('Type'),
            'description': _('Filter by type'),
            'value_type': 'single',
            'default': 'all',
            'options': [
                {'key': 'all', 'name': _('All')},
                {'key': 'webtoon', 'name': _('Originals')},
                {'key': 'challenge', 'name': _('Canvas')},
            ],
        },
    ]

    def __init__(self):
        self._session_initialized = False
        if self.session is None:
            self.session = requests.Session()

    @classmethod
    def get_manga_initial_data_from_url(cls, url):
        return dict(url=url.replace(cls.base_url, ''), slug=url.split('=')[-1])

    @init_session
    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's url (provided by search)
        """
        assert 'url' in initial_data, 'Manga url is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['url']), headers={'user-agent': USER_AGENT})
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        # Get true URL after redirects
        split_url = urlsplit(r.url)
        url = '{0}?{1}'.format(split_url.path, split_url.query)

        soup = BeautifulSoup(r.text, 'html.parser')

        data = initial_data.copy()
        data.update(dict(
            url=url,
            authors=[],
            scanlators=[],
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        data['name'] = get_soup_element_inner_text(soup.find(class_='subj'))

        # Details
        info_element = soup.find('div', class_='info')
        for element in info_element.find_all(class_='genre'):
            data['genres'].append(get_soup_element_inner_text(element))

        if 'canvas' in data['url']:
            # Canvas/Challenge
            detail_element = soup.find('div', class_='detail')

            data['cover'] = soup.find('div', class_='detail_header').img.get('src')

            for element in info_element.find_all(class_='author'):
                data['authors'].append(get_soup_element_inner_text(element))
        else:
            # Original/Webtoon
            detail_element = soup.find('div', class_='detail_body')

            data['cover'] = detail_element.get('style').split(' ')[1][4:-1].split('?')[0] + '?type=q90'

            try:
                for element in soup.find('div', class_='_authorInnerContent').find_all('h3'):
                    data['authors'].append(element.text.strip())
            except Exception:
                for element in info_element.find_all(class_='author'):
                    data['authors'].append(get_soup_element_inner_text(element))

            status_class = ''.join(detail_element.find('p', class_='day_info').span.get('class'))
            if 'completed' in status_class:
                data['status'] = 'complete'
            else:
                data['status'] = 'ongoing'

        data['synopsis'] = detail_element.find('p', class_='summary').text.strip()

        # Chapters
        data['chapters'] = self.get_manga_chapters_data(data['url'])

        return data

    @init_session
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(chapter_url), headers={'user-agent': USER_AGENT})
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        imgs = soup.find('div', id='_imageList').find_all('img')

        data = dict(
            pages=[],
        )
        for index, img in enumerate(imgs):
            data['pages'].append(dict(
                index=index + 1,
                slug=None,  # slug can't be used to forge image URL
                image=img.get('data-url').strip(),
            ))

        return data

    def get_manga_chapters_data(self, url):
        """
        Returns manga chapters data by scraping content of manga Mobile HTML page
        """
        # Use a Mobile user agent
        r = self.session_get(self.chapters_url.format(url), headers={'user-agent': USER_AGENT_MOBILE})
        if r.status_code != 200:
            return []

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return []

        soup = BeautifulSoup(r.text, 'html.parser')

        li_elements = soup.find('ul', id='_episodeList').find_all('li', recursive=False)

        data = []
        for li_element in reversed(li_elements):
            if li_element.get('data-episode-no') is None:
                continue

            date_element = li_element.find('span', class_='date')
            if date_element.span:
                date_element.span.decompose()

            # Small difference here compared to other servers
            # the slug can't be used to forge chapter URL, we must store the full url
            url_split = urlsplit(li_element.a.get('href'))

            data.append(dict(
                slug=url_split.path.split('/')[-2],
                title=li_element.find('p', class_='sub_title').find('span', class_='ellipsis').text.strip(),
                date=convert_date_string(date_element.text.strip(), format='%b %d, %Y'),
                url='{0}?{1}'.format(url_split.path, url_split.query),
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(page['image'], headers={'referer': self.base_url, 'user-agent': USER_AGENT})
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name='{0:03d}.{1}'.format(page['index'], mime_type.split('/')[-1]),
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(url)

    @init_session
    def get_most_populars(self):
        """
        Returns TOP 10 manga
        """
        headers = {'user-agent': USER_AGENT}
        if self.lang in LANGUAGES_CODES:
            r = self.session_get(self.most_populars_url.format(LANGUAGES_CODES[self.lang]), headers=headers)
        else:
            r = self.session_get(self.most_populars_url, headers=headers)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        results = []
        for li_element in soup.find('ul', class_='lst_type1').find_all('li'):
            if not li_element.a:
                continue

            split_url = urlsplit(li_element.a.get('href'))
            url = '{0}?{1}'.format(split_url.path, split_url.query)
            slug = split_url.query.split('=')[-1]

            results.append(dict(
                slug=slug,
                url=url,
                name=li_element.a.find('p', class_='subj').text.strip(),
            ))

        return results

    def is_long_strip(self, _manga_data):
        return True

    @init_session
    def search(self, term, type='all'):
        # @init_session is really useful here to ensure that needed cookies are there
        results = None

        if type == 'all' or type == 'webtoon':
            webtoon_results = self.search_by_type(term, 'WEBTOON')
            if webtoon_results is not None:
                results = webtoon_results

        if type == 'all' or type == 'challenge':
            challenge_results = self.search_by_type(term, 'CHALLENGE')
            if challenge_results is not None:
                if results is None:
                    results = challenge_results
                else:
                    results += challenge_results

        return results

    def search_by_type(self, term, type):
        assert type in ('CHALLENGE', 'WEBTOON', ), 'Invalid type'

        r = self.session_get(
            self.search_url.format(LANGUAGES_CODES[self.lang]),
            params=dict(
                keyword=term,
                searchType=type,
            ),
            headers={'user-agent': USER_AGENT}
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        if type == 'CHALLENGE':
            a_elements = soup.find_all('a', class_='challenge_item')
        elif type == 'WEBTOON':
            a_elements = soup.find_all('a', class_='card_item')

        results = []
        for a_element in a_elements:
            # Small difference here compared to other servers
            # the slug can't be used to forge manga URL, we must store the full url (relative)
            results.append(dict(
                slug=a_element.get('href').split('=')[-1],
                url=a_element.get('href').replace(self.base_url, ''),
                name=a_element.find('p', class_='subj').text.strip(),
            ))

        return results


class Dongmanmanhua(Webtoon):
    id = 'dongmanmanhua:webtoon'
    name = 'Dongman Manhua'
    lang = 'zh_Hans'

    base_url = 'https://www.dongmanmanhua.cn'
    search_url = base_url + '/{0}/search'
    most_populars_url = base_url + '/top'
    manga_url = base_url + '{0}'
    chapters_url = 'https://m.dongmanmanhua.cn/{0}'
    chapter_url = base_url + '{0}'


class Webtoon_es(Webtoon):
    id = 'webtoon_es'
    name = SERVER_NAME
    lang = 'es'


class Webtoon_fr(Webtoon):
    id = 'webtoon_fr'
    name = SERVER_NAME
    lang = 'fr'


class Webtoon_id(Webtoon):
    id = 'webtoon_id'
    name = SERVER_NAME
    lang = 'id'


class Webtoon_th(Webtoon):
    id = 'webtoon_th'
    name = SERVER_NAME
    lang = 'th'


class Webtoon_zh_hant(Webtoon):
    id = 'webtoon_zh_hant'
    name = SERVER_NAME
    lang = 'zh_Hant'
