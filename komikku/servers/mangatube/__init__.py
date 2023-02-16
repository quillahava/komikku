# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
from gettext import gettext as _
import json
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import get_soup_element_inner_text


class Mangatube(Server):
    id = 'mangatube'
    name = 'Manga Tube'
    lang = 'de'
    is_nsfw = True

    base_url = 'https://manga-tube.me'
    api_url = base_url + '/ajax'
    manga_url = base_url + '/series/{0}'
    chapter_url = base_url + '/series/{0}/read/{1}/1'
    image_url = 'https://a.mtcdn.org/m/{0}/{1}/{2}'

    filters = [
        {
            'key': 'type',
            'type': 'select',
            'name': _('Type'),
            'description': _('Type of Serie'),
            'value_type': 'single',
            'default': None,
            'options': [
                {'key': '0', 'name': _('Manga')},
                {'key': '1', 'name': _('Manhwa')},
                {'key': '2', 'name': _('Manhua')},
                {'key': '3', 'name': _('Webtoon')},
                {'key': '4', 'name': _('Comic')},
                {'key': '5', 'name': _('One Shot')},
                {'key': '6', 'name': _('Light Novel')},
            ]
        },
        {
            'key': 'mature',
            'type': 'select',
            'name': _('Age Rating'),
            'description': _('Maturity'),
            'value_type': 'single',
            'default': None,
            'options': [
                {'key': '0', 'name': _('Without')},
                {'key': '1', 'name': _('16+')},
                {'key': '2', 'name': _('18+')},
            ]
        },
    ]

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Manga slug is missing in initial data'

        _manga_id, manga_slug = initial_data['slug'].split('-', 1)
        r = self.session_get(self.manga_url.format(manga_slug), headers={
            'Referer': self.base_url,
        })
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
            cover=None,
        ))

        info_element = soup.find(class_='series-detailed')

        data['name'] = soup.find('h1').text.strip()
        data['cover'] = info_element.find('img', class_='img-responsive').get('data-original')

        # Details
        for li_element in info_element.find('ul', class_='series-details').find_all('li'):
            if not li_element.b:
                continue

            b_element = li_element.b.extract()
            label = b_element.text.strip()
            if label.startswith(('Autor', 'Artist')):
                value = li_element.a.text.strip()
                if value not in data['authors']:
                    data['authors'].append(value)

            elif label.startswith('Status (Scanlation)'):
                value = get_soup_element_inner_text(li_element)
                if value == 'laufend':
                    data['status'] = 'ongoing'
                elif value == 'abgeschlossen':
                    data['status'] = 'complete'

            elif label.startswith('Genre'):
                value = get_soup_element_inner_text(li_element)
                data['genres'] = [genre.strip() for genre in value.split()]

        # Synopsis
        synopsis_element = soup.find(class_='series-footer')
        synopsis_element.h4.extract()
        for name in ('div', 'hr', 'br'):
            for element in synopsis_element.find_all(name):
                element.extract()
        data['synopsis'] = get_soup_element_inner_text(synopsis_element)

        # Chapters
        for ul_element in soup.find_all('ul', class_='chapter-list'):
            for li_element in ul_element.find_all('li'):
                # Use last <a> to retrieve title and slug
                a_elements = li_element.find_all('a', recursive=False)
                a_element = a_elements[-1]

                # Remove buttons (new, ...)
                for btn_element in a_element.find_all(class_='btn'):
                    btn_element.extract()

                # Date
                date = li_element.find(class_='chapter-date').text  # Mo, 12.12.2022
                date = date.split(',')[-1].strip()

                data['chapters'].append(dict(
                    slug=a_element.get('href').split('/')[-2],
                    title=' - '.join(a_element.text.strip().split('\n')),
                    date=convert_date_string(date, format='%Y.%m.%d'),
                ))

        data['chapters'].reverse()

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        _manga_id, manga_slug = manga_slug.split('-', 1)
        r = self.session_get(self.chapter_url.format(manga_slug, chapter_slug), headers={
            'Referer': self.manga_url.format(manga_slug),
        })
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        # List of pages is available in JavaScript variable 'pages'
        # Walk in all scripts to find it
        pages = None
        for script_element in soup.find_all('script'):
            script = script_element.string
            if script is None:
                continue

            for line in script.split('\n'):
                line = line.strip()
                if line.startswith('var pages'):
                    pages = line.replace('var pages = ', '')[:-1]
                    break
            if pages is not None:
                pages = json.loads(pages)
                break

        if pages is None:
            return None

        data = dict(
            pages=[],
        )
        for page in pages:
            data['pages'].append(dict(
                slug=page['file_name'],
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(self.image_url.format(manga_slug, chapter_slug, page['slug']), headers={
            'Referer': self.chapter_url.format(manga_slug.split('-', 1)[0], chapter_slug),
        })
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=page['slug'],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        _manga_id, manga_slug = slug.split('-', 1)
        return self.manga_url.format(manga_slug)

    def get_latest_updates(self, **kwargs):
        r = self.session_get(self.base_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'html.parser')

        results = []
        for element in soup.select('.series-update .series-update-wraper'):
            a_element = element.select_one('.series-name')
            results.append(dict(
                slug='0-' + a_element.get('href').split('/')[-1],
                name=a_element.text.strip(),
                cover=element.select_one('.cover a img').get('data-original'),
            ))

        return results

    def get_most_populars(self, **kwargs):
        return self.search(populars=True)

    def search(self, term=None, populars=False, type=None, mature=None):
        if not populars:
            payload = {
                'action': 'advanced_search',
                'parameter[q]': term,
                'parameter[min_rating]': 0,
                'parameter[max_rating]': 5,
                'parameter[page]': 1,
            }
            if type is not None:
                payload['parameter[series_type]'] = type
            if mature is not None:
                payload['parameter[mature]'] = mature
            referer = self.base_url + '/series/search/'

        else:
            payload = {
                'action': 'load_series_list_entries',
                'parameter[sortby]': 'popularity',
                'parameter[letter]': '',
                'parameter[order]': 'asc',
                'parameter[page]': 1,
            }
            referer = self.base_url + '/series/?filter=popularity&order=asc'

        r = self.session_post(self.api_url, data=payload, headers={
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': referer,
        })
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type not in ('application/json', 'text/plain'):
            return None

        resp_data = r.json()

        results = []
        if resp_data.get('success'):
            if not populars:
                # success is a dict
                items = resp_data['success'].values()
            else:
                # success is a list
                items = resp_data['success']

            for item in items:
                results.append(dict(
                    slug='{0}-{1}'.format(item['manga_id'], item['manga_slug']),
                    name=item['manga_title'],
                ))

        return results
