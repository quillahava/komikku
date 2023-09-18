# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import json
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.multi.heancms import Heancms
from komikku.servers.multi.genkan import GenkanInitial
from komikku.servers.multi.madara import Madara
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Reaperscans(Madara):
    id = 'reaperscans'
    name = 'Reaper Scans'
    lang = 'en'

    series_name = 'series'

    base_url = 'https://reaperscans.com'


class Reaperscans_ar(Madara):
    id = 'reaperscans_ar'
    name = 'ريبر العربي'
    lang = 'ar'

    series_name = 'series'
    date_format = '%Y, %d %B'

    base_url = 'https://reaperscansar.com'
    chapters_url = base_url + '/series/{0}/ajax/chapters/'


class Reaperscans_fr(Madara):
    id = 'reaperscans_fr'
    name = 'ReaperScansFR (GS)'
    lang = 'fr'

    has_cf = True

    series_name = 'serie'
    date_format = '%d/%m/%Y'

    base_url = 'https://reaperscans.fr'


class Reaperscans_id(Madara):
    id = 'reaperscans_id'
    name = 'Reaper Scans'
    lang = 'id'

    series_name = 'series'

    base_url = 'https://reaperscans.id'


class Reaperscans_pt(Server):
    id = 'reaperscans_pt'
    name = 'Reaper Scans'
    lang = 'pt'
    status = 'disabled'  # Switch to HeanCMS (2023-??), a new server has been added with correct language (pt-BR)

    api_base_url = 'https://api.reaperscans.net'
    api_search_url = api_base_url + '/series/search'
    api_most_populars_url = api_base_url + '/series/querysearch'
    api_chapter_url = api_base_url + '/series/chapter/{}'

    base_url = 'https://reaperscans.net'
    manga_url = base_url + '/series/{0}'
    chapter_url = base_url + '/series/{0}/{1}'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],  # Not available
            genres=[],
            status=None,    # Not available
            cover=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
        ))

        data['name'] = soup.find('h1').text.strip()
        data['cover'] = soup.find('img', class_='rounded-thumb').get('src')

        # Details
        data['genres'] = [span.text.strip() for span in soup.find('div', class_='tags-container').find_all('span', class_='tag')]
        data['status'] = 'ongoing'

        container_element = soup.find('div', class_='useful-container')
        for author in container_element.select_one('p:-soup-contains("Autor") strong').text.strip().split(','):
            data['authors'].append(author.strip())

        # Synopsis
        data['synopsis'] = soup.find('div', class_='description-container').text.strip()

        # Chapters
        for a_element in reversed(soup.select('#simple-tabpanel-0 ul > a')):
            data['chapters'].append(dict(
                slug=a_element.get('href').split('/')[-1],
                title=a_element.select_one('.MuiTypography-body1').text.strip(),
                date=convert_date_string(a_element.select_one('.MuiTypography-body2').text.strip(), format='%d/%m/%Y'),
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content + API

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(manga_slug, chapter_slug))
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        id_ = None
        for script_element in soup.find_all('script'):
            if script_element.get('id') != '__NEXT_DATA__':
                continue
            data = json.loads(script_element.string)
            id_ = data['props']['pageProps']['data']['id']
            break

        if id_ is None:
            return None

        r = self.session_get(self.api_chapter_url.format(id_))
        if r.status_code != 200:
            return None

        data = dict(
            pages=[],
        )
        for image in r.json()['content']['images']:
            data['pages'].append(dict(
                slug=None,
                image=image,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(self.api_base_url + '/' + page['image'])
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
        return self.search('', orderby='latest')

    def get_most_populars(self):
        return self.search('', orderby='populars')

    def search(self, term, orderby=None):
        if orderby:
            r = self.session_post(
                self.api_most_populars_url,
                params=dict(
                    order='desc',
                    order_by='total_views' if orderby == 'populars' else 'recently_added',
                    series_type='Comic',
                ),
                headers={
                    'content-type': 'application/json',
                }
            )
        else:
            r = self.session_post(
                self.api_search_url,
                params=dict(
                    term=term,
                ),
                headers={
                    'content-type': 'application/json',
                }
            )
        if r.status_code != 200:
            return None

        items = r.json()
        if orderby:
            items = items['data']

        results = []
        for item in items:
            if item['series_type'] not in ('Comic',):
                continue

            results.append(dict(
                slug=item['series_slug'],
                name=item['title'],
            ))

        return results


class Reaperscans_pt_br(Heancms):
    id = 'reaperscans_pt_br'
    name = 'Reaper Scans'
    lang = 'pt_BR'

    base_url = 'https://reaperbr.online'
    api_url = 'https://api.reaperscans.net'

    cover_css_path = 'div div div.container.px-5.text-gray-50 div.grid.grid-cols-12.pt-3.gap-x-3 div.col-span-12.relative.flex.justify-center.w-full div.flex.flex-col.items-center.justify-center.gap-y-2.w-full img'
    authors_css_path = 'div div.container.px-5.text-gray-50 div.grid.grid-cols-12.pt-3.gap-x-3 div.col-span-12.flex.flex-col.gap-y-3 div div.flex.flex-col.gap-y-2 p:nth-child(3) strong'
    synopsis_css_path = 'div div.container.px-5.text-gray-50 div.grid.grid-cols-12.pt-3.gap-x-3 div.col-span-12.flex.flex-col.gap-y-3 div.bg-gray-800.text-gray-50.rounded-xl.p-5'


class Reaperscans_tr(Madara):
    id = 'reaperscans_tr'
    name = 'Reaper Scans'
    lang = 'tr'

    series_name = 'seri'

    base_url = 'https://reaperscanstr.com'


class Reaperscans__old(GenkanInitial):
    id = 'reaperscans__old'
    name = 'Reaper Scans'
    lang = 'en'
    status = 'disabled'

    # Use Cloudflare
    # Search is partially broken -> inherit from GenkanInitial instead of Genkan class

    base_url = 'https://reaperscans.com'
    search_url = base_url + '/comics'
    most_populars_url = base_url + '/home'
    manga_url = base_url + '/comics/{0}'
    chapter_url = base_url + '/comics/{0}/{1}'
    image_url = base_url + '{0}'
