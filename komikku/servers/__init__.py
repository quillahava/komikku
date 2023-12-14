# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from abc import ABC
from abc import abstractmethod
from bs4 import BeautifulSoup
from functools import cached_property
import inspect
import logging
import os
import pickle
import requests
from requests.adapters import TimeoutSauce

from komikku.models.keyring import KeyringHelper
from komikku.servers.loader import server_finder
from komikku.servers.utils import convert_image
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import get_server_main_id_by_id
from komikku.utils import expand_and_resize_cover
from komikku.utils import get_cache_dir

# https://www.localeplanet.com/icu/
LANGUAGES = dict(
    ar='العربية',
    id='Bahasa Indonesia',
    cs='Čeština',
    de='Deutsch',
    en='English',
    eo='Espéranto',
    es='Español',
    es_419='Español (Latinoamérica)',
    fr='Français',
    it='Italiano',
    nl='Nederlands',
    nb='Norsk Bokmål',
    pl='Polski',
    pt='Português',
    pt_BR='Português (Brasil)',
    ru='Русский',
    uk='Українська',
    vi='Tiếng Việt',
    tr='Türkçe',
    ja='日本語',
    ko='한국어',
    th='ไทย',
    zh_Hans='中文 (简体)',
    zh_Hant='中文 (繁體)',
)

REQUESTS_TIMEOUT = 5

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0'
USER_AGENT_MOBILE = 'Mozilla/5.0 (Linux; U; Android 4.1.1; en-gb; Build/KLP) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Safari/534.30'

VERSION = 1

logger = logging.getLogger('komikku.servers')
server_finder.install()


class CustomTimeout(TimeoutSauce):
    def __init__(self, *args, **kwargs):
        if kwargs['connect'] is None:
            kwargs['connect'] = REQUESTS_TIMEOUT
        if kwargs['read'] is None:
            kwargs['read'] = REQUESTS_TIMEOUT * 3
        super().__init__(*args, **kwargs)


# Set requests timeout globally, instead of specifying ``timeout=..`` kwarg on each call
requests.adapters.TimeoutSauce = CustomTimeout


class Server(ABC):
    id: str
    name: str
    lang: str

    base_url = None

    bypass_cf_url = None
    has_cf = False
    has_login = False
    headers = None
    is_nsfw = False
    is_nsfw_only = False
    long_strip_genres = []
    manga_title_css_selector = None  # Used to extract manga title in a manga URL
    true_search = True  # If False, hide search in Explorer search page (XKCD, DBM, pepper&carotte…)
    status = 'enabled'
    sync = False

    logged_in = False

    __sessions = {}  # to cache all existing sessions

    @classmethod
    def get_manga_initial_data_from_url(cls, url):
        if cls.manga_title_css_selector:
            c = cls()
            r = c.session_get(url)
            if r.status_code != 200:
                return None

            soup = BeautifulSoup(r.content, 'html.parser')

            title_element = soup.select_one(cls.manga_title_css_selector)
            if not title_element:
                return None

            results = c.search(title_element.text.strip())
            if not results:
                return None

            slug = results[0]['slug']
        else:
            slug = url.split('?')[0].split('/')[-1]

        return dict(slug=slug)

    def do_login(self, username=None, password=None):
        if username and password:
            # Username and password are provided only when user defines the credentials in the settings
            self.clear_session()
        elif credential := KeyringHelper().get(get_server_main_id_by_id(self.id)):
            if self.base_url is None:
                self.base_url = credential.address

        if self.session is None:
            if self.load_session():
                self.logged_in = True
            else:
                self.session = requests.Session()
                if self.headers:
                    self.session.headers = self.headers

                if username is None and password is None:
                    if credential:
                        self.logged_in = self.login(credential.username, credential.password)
                else:
                    self.logged_in = self.login(username, password)
        else:
            self.logged_in = True

    def login(self, _username, _password):
        return False

    @cached_property
    def logo_path(self):
        module_path = os.path.dirname(os.path.abspath(inspect.getfile(self.__class__)))

        path = os.path.join(module_path, get_server_main_id_by_id(self.id) + '.ico')
        if not os.path.exists(path):
            return None

        return path

    @property
    def session(self):
        return Server.__sessions.get(self.id)

    @session.setter
    def session(self, value):
        Server.__sessions[self.id] = value

    @property
    def sessions_dir(self):
        dir_path = os.path.join(get_cache_dir(), 'sessions')
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)

        return dir_path

    def clear_session(self, all=False):
        main_id = get_server_main_id_by_id(self.id)

        # Remove session from disk
        file_path = os.path.join(self.sessions_dir, '{0}.pickle'.format(main_id))
        if os.path.exists(file_path):
            os.unlink(file_path)

        if all:
            for id_ in Server.__sessions.copy():
                if id_.startswith(main_id):
                    del Server.__sessions[id_]
        elif self.id in Server.__sessions:
            del Server.__sessions[self.id]

    def get_manga_cover_image(self, url, etag=None):
        """
        Get a manga cover

        :param str url: The cover image URL
        :param etag: The current cover image ETag
        :type etag: str or None
        :return: The cover image content + the cover image ETag if exists
        :rtype: tuple
        """
        if url is None:
            return None, None

        headers = {
            'Referer': self.base_url,
        }
        if etag:
            headers['If-None-Match'] = etag

        r = self.session.get(url, headers=headers)
        if r.status_code != 200:
            return None, None

        buffer = r.content
        mime_type = get_buffer_mime_type(buffer)
        if not mime_type.startswith('image'):
            return None, None

        if mime_type == 'image/webp':
            buffer = convert_image(buffer, ret_type='bytes')

        return expand_and_resize_cover(buffer), r.headers.get('ETag')

    @abstractmethod
    def get_manga_data(self, initial_data):
        """This method must return a dictionary.

        Data are usually obtained:
        - by scrapping an HTML page
        - or by parsing the response of a request to an API.

        In most cases, the URL of the HTML page or the URL of the API endpoint
        are forged using a slug provided by method `search` and available in `initial_data` argument.

        By convention, returned dict must contain the following keys:
        - name: Name of the manga
        - authors: List of authors (str) [optional]
        - scanlators: List of scanlators (str) [optional]
        - genres: List of genres (str) [optional]
        - status: Status of the manga (See database.Manga.STATUSES) [optional]
        - synopsis: Synopsis of the manga [optional]
        - chapters: List of chapters (See description below)
        - server_id: The server ID
        - cover: Absolute URL of the cover

        By convention, a chapter is a dictionary which must contain the following keys:
        - slug: A slug (str) allowing to forge HTML page URL of the chapter
                (usually in conjunction with the manga slug)
        - url: URL of chapter HTML page if `slug` is not usable
        - title: Title of the chapter
        - date: Publish date of the chapter [optional]
        - scanlators: List of scanlators (str) [optional]
        """
        pass

    @abstractmethod
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """This method must return a list of pages.

        Data are usually obtained:
        - by scrapping an HTML page
        - or by parsing the response of a request to an API.

        The URL of the HTML page or the URL of the API endpoint are forged using 4 provided arguments.

        By convention, each page is a dictionary which must contain one of the 3 keys `slug`, `image` or `url`:
        - slug : A slug (str) allowing to forge image URL of the page
                 (usually in conjunction with the manga slug and the chapter slug)
        - image: Absolute or relative URL of the page image
        - url: URL of the HTML page to scrape to get the URL of the page image

        It's of course possible to add any other information if necessary
        (an index for example to compute a better image filename).

        The page data are passed to `get_manga_chapter_page_image` method.
        """
        pass

    @abstractmethod
    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """This method must return a dictionary with the following keys:

        - buffer: Image buffer
        - mime_type: Image MIME type
        - name: Filename of the image

        Depending on the server, we have:
        - the slug or the URL of the image
        - or the URL of the HTML page containing the image.

        In the first case, we have the URL (or can forge it) so we can directly retrieve the image with a GET request.

        In the second case, we must first retrieve the URL of the image by scraping the HTML page containing the image.
        """
        pass

    @abstractmethod
    def get_manga_url(self, slug, url):
        """This method must return absolute URL of the manga"""
        pass

    def is_long_strip(self, data):
        """
        Returns True if the manga is a long strip, False otherwise.

        The server shall not modify `data` to form the return value.
        """
        if not self.long_strip_genres:
            return False

        for genre in data['genres']:
            if genre in self.long_strip_genres:
                return True

        return False

    def load_session(self):
        """ Load session from disk """

        file_path = os.path.join(self.sessions_dir, '{0}.pickle'.format(get_server_main_id_by_id(self.id)))
        if not os.path.exists(file_path):
            return False

        with open(file_path, 'rb') as f:
            session = pickle.load(f)

        # Check session validity
        # Expired cookies must be deleted
        clearables = []
        for cookie in session.cookies:
            if cookie.is_expired():
                clearables.append((cookie.domain, cookie.path, cookie.name))

        for domain, path, name in clearables:
            session.cookies.clear(domain, path, name)

        if len(session.cookies) == 0:
            self.clear_session(all=True)
            return False

        self.session = session

        if clearables:
            self.save_session()

        return True

    def save_session(self):
        """ Save session to disk """

        file_path = os.path.join(self.sessions_dir, '{0}.pickle'.format(get_server_main_id_by_id(self.id)))
        with open(file_path, 'wb') as f:
            pickle.dump(self.session, f)

    @abstractmethod
    def search(self, term=None):
        """This method must return a dictionary.

        Data are usually obtained:
        - by scrapping an HTML page
        - or by parsing the response of a request to an API.

        By convention, returned dict must contain the following keys:
        - slug: A slug (str) allowing to forge URL of the HTML page of the manga
        - url: URL of manga HTML page if `slug` is not usable
        - name: Name of the manga
        - cover: Absolute URL of the manga cover [optional but recommanded for future developments]

        It's of course possible to add any other information if necessary.

        The data are passed to `get_manga_data` method.
        """
        pass

    def session_get(self, *args, **kwargs):
        try:
            r = self.session.get(*args, **kwargs)
        except Exception as error:
            logger.debug(error)
            raise

        return r

    def session_patch(self, *args, **kwargs):
        try:
            r = self.session.patch(*args, **kwargs)
        except Exception as error:
            logger.debug(error)
            raise

        return r

    def session_post(self, *args, **kwargs):
        try:
            r = self.session.post(*args, **kwargs)
        except Exception as error:
            logger.debug(error)
            raise

        return r

    def update_chapter_read_progress(self, data, manga_slug, manga_name, chapter_slug, chapter_url):
        return NotImplemented
