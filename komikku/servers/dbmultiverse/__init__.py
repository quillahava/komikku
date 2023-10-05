# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import requests

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type

SERVER_NAME = 'Dragon Ball Multiverse'


class Dbmultiverse(Server):
    id = 'dbmultiverse'
    name = SERVER_NAME
    lang = 'en'
    true_search = False

    base_url = 'https://www.dragonball-multiverse.com'
    manga_url = base_url + '/en/chapters.html?comic=page'
    page_url = base_url + '/en/page-{0}.html'
    cover_url = base_url + '/image.php?comic=page&num=0&lg=en&ext=jpg&small=1&pw=8f3722a594856af867d55c57f31ee103'

    synopsis = "Dragon Ball Multiverse (DBM) is a free online comic, made by a whole team of fans. It's our personal sequel to DBZ."

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({'user-agent': USER_AGENT})

    def get_manga_data(self, initial_data):
        """
        Returns manga data by scraping manga HTML page content
        """
        r = self.session_get(self.manga_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = initial_data.copy()
        data.update(dict(
            authors=['Gogeta Jr', 'Asura', 'Salagir'],
            scanlators=[],
            genres=['Shounen', ],
            status='ongoing',
            synopsis=self.synopsis,
            chapters=[],
            server_id=self.id,
            cover=self.cover_url,
        ))

        # Chapters
        for div_element in soup.find_all('div', class_='chapter'):
            slug = div_element.get('ch')
            if not slug:
                continue

            p_element = div_element.p

            chapter_data = dict(
                slug=slug,
                date=None,
                title=div_element.h4.text.strip(),
                pages=[],
            )

            for a_element in p_element.find_all('a'):
                chapter_data['pages'].append(dict(
                    slug=a_element.get('href')[:-5].split('-')[-1],
                    image=None,
                ))

            data['chapters'].append(chapter_data)

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga data by scraping manga HTML page content
        """
        r = self.session_get(self.manga_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        data = dict(
            pages=[],
        )
        for a_element in soup.find('div', class_='chapter', ch=chapter_slug).p.find_all('a'):
            data['pages'].append(dict(
                slug=a_element.get('href')[:-5].split('-')[-1],
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(self.page_url.format(page['slug']))
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')

        if img_element := soup.find('img', id='balloonsimg'):
            url = img_element.get('src')
            if not url:
                url = img_element.get('style').split(';')[0].split(':')[1][4:-1]
        elif div_element := soup.find('div', id='balloonsimg'):
            url = div_element.get('style').split('(')[1].split(')')[0]
        elif celebrate_element := soup.find('div', class_='cadrelect'):
            # Special page to celebrate 1000/2000/... pages
            # return first contribution image
            url = celebrate_element.find('img').get('src')
        else:
            return None

        r = self.session_get(self.base_url + url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name='{0}.png'.format(page['slug']),
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url

    def get_most_populars(self):
        return [dict(
            slug='dbm_{0}'.format(self.lang),
            name='Dragon Ball Multiverse (DBM)',
        )]

    def search(self, term=None):
        # This server does not have a true search
        # but a search method is needed for `Global Search` in `Explorer`
        # In order not to be offered in `Explorer`, class attribute `true_search` must be set to False

        results = []
        for item in self.get_most_populars():
            if term and term.lower() in item['name'].lower():
                results.append(item)

        return results


class Dbmultiverse_de(Dbmultiverse):
    id = 'dbmultiverse_de'
    name = SERVER_NAME
    lang = 'de'

    base_url = 'https://www.dragonball-multiverse.com'
    manga_url = base_url + '/de/chapters.html?comic=page'
    page_url = base_url + '/de/page-{0}.html'

    synopsis = "Dragon Ball Multiverse ist ein kostenloser Online-Comic, gezeichnet von Fans, u. a. Gogeta Jr, Asura und Salagir. Es knüpft direkt an DBZ an als eine Art Fortsetzung. Veröffentlichung dreimal pro Woche: Mittwoch, Freitag und Sonntag um 20.00 MEZ."


class Dbmultiverse_es(Dbmultiverse):
    id = 'dbmultiverse_es'
    name = SERVER_NAME
    lang = 'es'

    base_url = 'https://www.dragonball-multiverse.com'
    manga_url = base_url + '/es/chapters.html?comic=page'
    page_url = base_url + '/es/page-{0}.html'

    synopsis = "Dragon Ball Multiverse (DBM) es un cómic online gratuito, realizado por un gran equipo de fans. Es nuestra propia continuación de DBZ."


class Dbmultiverse_fr(Dbmultiverse):
    id = 'dbmultiverse_fr'
    name = SERVER_NAME
    lang = 'fr'

    base_url = 'https://www.dragonball-multiverse.com'
    manga_url = base_url + '/fr/chapters.html?comic=page'
    page_url = base_url + '/fr/page-{0}.html'

    synopsis = "Dragon Ball Multiverse (DBM) est une BD en ligne gratuite, faite par toute une équipe de fans. C'est notre suite personnelle à DBZ."


class Dbmultiverse_it(Dbmultiverse):
    id = 'dbmultiverse_it'
    name = SERVER_NAME
    lang = 'it'

    base_url = 'https://www.dragonball-multiverse.com'
    manga_url = base_url + '/it/chapters.html?comic=page'
    page_url = base_url + '/it/page-{0}.html'

    synopsis = "Dragon Ball Multiverse (abbreviato in DBM) è un Fumetto gratuito pubblicato online e rappresenta un possibile seguito di DBZ. I creatori sono due fan: Gogeta Jr e Salagir."


class Dbmultiverse_pt(Dbmultiverse):
    id = 'dbmultiverse_pt'
    name = SERVER_NAME
    lang = 'pt'

    base_url = 'https://www.dragonball-multiverse.com'
    manga_url = base_url + '/pt/chapters.html?comic=page'
    page_url = base_url + '/pt/page-{0}.html'

    synopsis = "Dragon Ball Multiverse (DBM) é uma BD online grátis, feita por dois fãs Gogeta Jr e Salagir. É a sequela do DBZ."


class Dbmultiverse_ru(Dbmultiverse):
    id = 'dbmultiverse_ru'
    name = SERVER_NAME
    lang = 'ru'

    base_url = 'https://www.dragonball-multiverse.com'
    manga_url = base_url + '/ru_RU/chapters.html?comic=page'
    page_url = base_url + '/ru_RU/page-{0}.html'

    synopsis = "Dragon Ball Multiverse (DBM) это бесплатный онлайн комикс (манга), сделана двумя фанатами, Gogeta Jr и Salagir. Это продолжение DBZ."
