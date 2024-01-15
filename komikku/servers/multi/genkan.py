# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

# Genkan CMS

# Supported servers
# Edelgarde Scans [EN] (disabled)
# Hatigarm Scans [EN] (disabled)
# Hunlight Scans [EN] (disabled)
# Leviatan Scans [EN/ES] (disabled)
# One Shot Scans [EN] (disabled)
# Reaper Scans [EN] (disabled)
# The Nonames Scans [EN] (disabled)

from bs4 import BeautifulSoup
import json
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import convert_date_string
from komikku.servers.utils import get_buffer_mime_type


class Genkan(Server):
    base_url: str
    search_url: str
    most_populars_url: str
    manga_url: str
    chapter_url: str
    image_url: str

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
            scanlators=[self.name, ],
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        data['name'] = soup.find_all('h5')[0].text.strip()
        cover_url = soup.find('div', class_='media-comic-card').a.get('style').split('(')[-1][:-1]
        if cover_url.startswith('http'):
            data['cover'] = cover_url
        else:
            data['cover'] = self.image_url.format(cover_url)

        # Details
        data['synopsis'] = soup.find('div', class_='col-lg-9').contents[2].strip()

        # Chapters
        elements = soup.find('div', class_='list list-row row').find_all('div', class_='list-item')
        for element in reversed(elements):
            a_elements = element.find_all('a')

            slug = '/'.join(a_elements[0].get('href').split('/')[-2:])
            title = '#{0} - {1}'.format(element.span.text.strip(), a_elements[0].text.strip())
            date = a_elements[1].text.strip()

            data['chapters'].append(dict(
                slug=slug,
                date=convert_date_string(date),
                title=title,
            ))

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data by scraping chapter HTML page content

        Currently, only pages are expected.
        """
        r = self.session_get(self.chapter_url.format(manga_slug, chapter_slug))
        if r is None:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if r.status_code != 200 or mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )
        for script_element in soup.find_all('script'):
            script = script_element.string
            if script is None or not script.strip().startswith('window.disqusName'):
                continue

            for line in script.split(';'):
                line = line.strip()
                if not line.startswith('window.chapterPages'):
                    continue

                images = json.loads(line.split('=')[1].strip())
                for image in images:
                    data['pages'].append(dict(
                        slug=None,
                        image=image,
                    ))
                break
            break

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        if page['image'].startswith('http'):
            image_url = page['image']
        else:
            image_url = self.image_url.format(page['image'])

        r = self.session_get(image_url, headers={'Referer': self.chapter_url.format(manga_slug, chapter_slug)})
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
        Returns new and/or recommended manga
        """
        r = self.session_get(self.most_populars_url)

        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')

            results = []
            for a_element in soup.find_all('a', class_='list-title ajax'):
                result = dict(
                    slug=a_element.get('href').split('/')[-1],
                    name=a_element.text.strip(),
                )
                if result not in results:
                    results.append(result)

            return results

        return None

    def search(self, term):
        r = self.session_get(self.search_url.format(term))

        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')

            results = []
            for a_element in soup.find_all('a', class_='list-title ajax'):
                results.append(dict(
                    slug=a_element.get('href').split('/')[-1],
                    name=a_element.text.strip(),
                ))

            return results

        return None


class GenkanInitial(Genkan):
    """
    The initial version of the CMS doesn't provide search
    """

    def search(self, term):
        r = self.session_get(self.search_url)

        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')

            results = []
            for a_element in soup.find_all('a', class_='list-title ajax'):
                name = a_element.text.strip()
                if term.lower() not in name.lower():
                    continue

                results.append(dict(
                    slug=a_element.get('href').split('/')[-1],
                    name=name,
                ))

            return results

        return None
