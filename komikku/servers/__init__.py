# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import dateparser
import datetime
from functools import cached_property
from functools import lru_cache
from functools import wraps
import gi
import importlib
import inspect
import io
import magic
from operator import itemgetter
import os
import pickle
from PIL import Image
import pkgutil
import requests
from requests.adapters import TimeoutSauce
import struct

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.0')

from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import WebKit2

from komikku.utils import get_cache_dir
from komikku.utils import KeyringHelper

# https://www.localeplanet.com/icu/
LANGUAGES = dict(
    id='Bahasa Indonesia',
    cs='Čeština',
    de='Deutsch',
    en='English',
    es='Español',
    fr='Français',
    it='Italiano',
    nl='Nederlands',
    nb='Norsk Bokmål',
    pl='Polski',
    pt='Português',
    pt_BR='Português (Brasil)',
    ru='Русский',
    vi='Tiếng Việt',
    ja='日本語',
    ko='한국어',
    th='ไทย',
    zh_Hans='中文 (简体)',
    zh_Hant='中文 (繁體)',
)

REQUESTS_TIMEOUT = 5

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.135 Safari/537.36'
USER_AGENT_MOBILE = 'Mozilla/5.0 (Linux; U; Android 4.1.1; en-gb; Build/KLP) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Safari/534.30'

VERSION = 1


class CustomTimeout(TimeoutSauce):
    def __init__(self, *args, **kwargs):
        if kwargs['connect'] is None:
            kwargs['connect'] = REQUESTS_TIMEOUT
        if kwargs['read'] is None:
            kwargs['read'] = REQUESTS_TIMEOUT * 3
        super().__init__(*args, **kwargs)


# Set requests timeout globally, instead of specifying ``timeout=..`` kwarg on each call
requests.adapters.TimeoutSauce = CustomTimeout


class HeadlessBrowser(Gtk.Window):
    load_failed_event = None
    lock = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.scrolledwindow = Gtk.ScrolledWindow()
        self.scrolledwindow.get_hscrollbar().hide()
        self.scrolledwindow.get_vscrollbar().hide()

        self.viewport = Gtk.Viewport()
        self.scrolledwindow.add(self.viewport)
        self.add(self.scrolledwindow)

        self.webview = WebKit2.WebView()
        self.viewport.add(self.webview)

        self.webview.get_settings().set_user_agent(USER_AGENT)

        self.web_context = self.webview.get_context()
        self.web_context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
        self.web_context.set_tls_errors_policy(WebKit2.TLSErrorsPolicy.IGNORE)

        # Make window almost invisible
        self.set_decorated(False)
        self.set_focus_on_map(False)
        self.set_keep_below(True)
        self.resize(1, 1)

        self.webview.connect('load-failed', self.on_load_failed)

    def hide_and_blank(self):
        self.lock = False

        GLib.idle_add(self.webview.load_uri, 'about:blank')
        self.hide()

    def load(self, uri):
        if self.lock:
            return False

        self.lock = True
        self.load_failed_event = None

        self.show_all()

        GLib.idle_add(self.webview.load_uri, uri)

        return True

    def on_load_failed(self, _webview, event, uri, error):
        self.load_failed_event = event
        self.hide_and_blank()


headless_browser = HeadlessBrowser()


class Server:
    id = NotImplemented
    name = NotImplemented
    lang = NotImplemented

    has_login = False
    headers = None
    is_nsfw = False
    logged_in = False
    long_strip_genres = []
    manga_title_css_selector = None  # Used to extract manga title in a manga URL
    session_expiration_cookies = []  # Session cookies for which validity (not expired) must be checked
    status = 'enabled'
    sync = False

    base_url = None

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

    def login(self, username, password):
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
        dir = os.path.join(get_cache_dir(), 'sessions')
        if not os.path.exists(dir):
            os.mkdir(dir)

        return dir

    def clear_session(self, all=False):
        main_id = get_server_main_id_by_id(self.id)

        # Remove session from disk
        file_path = os.path.join(self.sessions_dir, '{0}.pickle'.format(main_id))
        if os.path.exists(file_path):
            os.unlink(file_path)

        if all:
            for id in Server.__sessions:
                if id.startswith(main_id):
                    del Server.__sessions[id]
        elif self.id in Server.__sessions:
            del Server.__sessions[self.id]

    def get_manga_cover_image(self, url):
        """
        Returns manga cover (image) content
        """
        if url is None:
            return None

        r = self.session_get(url, headers={'referer': self.base_url})
        if r is None:
            return None

        if r.status_code != 200:
            return None

        buffer = r.content
        mime_type = get_buffer_mime_type(buffer)

        if not mime_type.startswith('image'):
            return None

        if mime_type == 'image/webp':
            buffer = convert_image(buffer, ret_type='bytes')

        return buffer

    def load_session(self):
        """ Load session from disk """

        file_path = os.path.join(self.sessions_dir, '{0}.pickle'.format(get_server_main_id_by_id(self.id)))
        if not os.path.exists(file_path):
            return False

        with open(file_path, 'rb') as f:
            session = pickle.load(f)

        # Check session validity
        if self.session_expiration_cookies:
            # One or more cookies for which the expiration date must be checked are defined
            # If one of them has expired, session must be cleared
            for cookie in session.cookies:
                if cookie.name not in self.session_expiration_cookies:
                    continue

                if cookie.is_expired():
                    self.clear_session(all=True)
                    return False

        self.session = session

        return True

    def save_session(self):
        """ Save session to disk """

        file_path = os.path.join(self.sessions_dir, '{0}.pickle'.format(get_server_main_id_by_id(self.id)))
        with open(file_path, 'wb') as f:
            pickle.dump(self.session, f)

    def session_get(self, *args, **kwargs):
        try:
            r = self.session.get(*args, **kwargs)
        except Exception:
            raise

        return r

    def session_patch(self, *args, **kwargs):
        try:
            r = self.session.patch(*args, **kwargs)
        except Exception:
            raise

        return r

    def session_post(self, *args, **kwargs):
        try:
            r = self.session.post(*args, **kwargs)
        except Exception:
            raise

        return r

    def update_chapter_read_progress(self, data, manga_slug, manga_name, chapter_slug, chapter_url):
        return False


def convert_date_string(date, format=None):
    if format is not None:
        try:
            d = datetime.datetime.strptime(date, format)
        except Exception:
            d = dateparser.parse(date)
    else:
        d = dateparser.parse(date)

    return d.date()


# https://github.com/italomaia/mangarock.py/blob/master/mangarock/mri_to_webp.py
def convert_mri_data_to_webp_buffer(data):
    size_list = [0] * 4
    size = len(data)
    header_size = size + 7

    # little endian byte representation
    # zeros to the right don't change the value
    for i, byte in enumerate(struct.pack('<I', header_size)):
        size_list[i] = byte

    buffer = [
        82,  # R
        73,  # I
        70,  # F
        70,  # F
        size_list[0],
        size_list[1],
        size_list[2],
        size_list[3],
        87,  # W
        69,  # E
        66,  # B
        80,  # P
        86,  # V
        80,  # P
        56,  # 8
    ]

    for bit in data:
        buffer.append(101 ^ bit)

    return bytes(buffer)


def convert_image(image, format='jpeg', ret_type='image'):
    """Convert an image to a specific format

    :param image: PIL.Image.Image or bytes object
    :param format: convertion format: jpeg, png, webp,...
    :param ret_type: image (PIL.Image.Image) or bytes (bytes object)
    """
    if not isinstance(image, Image.Image):
        image = Image.open(io.BytesIO(image))

    io_buffer = io.BytesIO()
    image.convert('RGB').save(io_buffer, format)
    if ret_type == 'bytes':
        return io_buffer.getbuffer()
    io_buffer.seek(0)
    return Image.open(io_buffer)


def do_login(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        server = args[0]
        if not server.logged_in:
            server.do_login()

        return func(*args, **kwargs)

    return wrapper


def get_allowed_servers_list(settings):
    servers_settings = settings.servers_settings
    servers_languages = settings.servers_languages

    servers = []
    for server_data in get_servers_list():
        if servers_languages and server_data['lang'] not in servers_languages:
            continue

        server_settings = servers_settings.get(get_server_main_id_by_id(server_data['id']))
        if server_settings is not None and (not server_settings['enabled'] or server_settings['langs'].get(server_data['lang']) is False):
            continue

        if settings.nsfw_content is False and server_data['is_nsfw']:
            continue

        servers.append(server_data)

    return servers


def get_buffer_mime_type(buffer):
    try:
        if hasattr(magic, 'detect_from_content'):
            # Using file-magic module: https://github.com/file/file
            return magic.detect_from_content(buffer[:128]).mime_type
        else:
            # Using python-magic module: https://github.com/ahupp/python-magic
            return magic.from_buffer(buffer[:128], mime=True)
    except Exception:
        return ''


def get_file_mime_type(path):
    try:
        if hasattr(magic, 'detect_from_filename'):
            # Using file-magic module: https://github.com/file/file
            return magic.detect_from_filename(path).mime_type
        else:
            # Using python-magic module: https://github.com/ahupp/python-magic
            return magic.from_file(path, mime=True)
    except Exception:
        return ''


def get_server_class_name_by_id(id):
    return id.split(':')[0].capitalize()


def get_server_dir_name_by_id(id):
    return id.split(':')[0]


def get_server_main_id_by_id(id):
    return id.split(':')[0].split('_')[0]


def get_server_module_name_by_id(id):
    return id.split(':')[-1].split('_')[0]


@lru_cache(maxsize=None)
def get_servers_list(include_disabled=False, order_by=('lang', 'name')):
    import komikku.servers

    def iter_namespace(ns_pkg):
        # Specifying the second argument (prefix) to iter_modules makes the
        # returned name an absolute name instead of a relative one. This allows
        # import_module to work without having to do additional modification to
        # the name.
        return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + '.')

    servers = []
    for _finder, name, _ispkg in iter_namespace(komikku.servers):
        module = importlib.import_module(name)
        for _name, obj in dict(inspect.getmembers(module)).items():
            if not hasattr(obj, 'id') or not hasattr(obj, 'name') or not hasattr(obj, 'lang'):
                continue
            if NotImplemented in (obj.id, obj.name, obj.lang):
                continue

            if not include_disabled and obj.status == 'disabled':
                continue

            if inspect.isclass(obj) and obj.__module__.startswith('komikku.servers.'):
                logo_path = os.path.join(os.path.dirname(os.path.abspath(module.__file__)), get_server_main_id_by_id(obj.id) + '.ico')

                servers.append(dict(
                    id=obj.id,
                    name=obj.name,
                    lang=obj.lang,
                    has_login=obj.has_login,
                    is_nsfw=obj.is_nsfw,
                    class_name=get_server_class_name_by_id(obj.id),
                    logo_path=logo_path if os.path.exists(logo_path) else None,
                    module=module,
                ))

    return sorted(servers, key=itemgetter(*order_by))


def search_duckduckgo(site, term):
    session = requests.Session()
    session.headers.update({'user-agent': USER_AGENT})

    params = dict(
        kd=-1,
        q=f'site:{site} {term}',
    )

    try:
        r = session.get('https://duckduckgo.com/lite', params=params)
    except Exception:
        raise

    soup = BeautifulSoup(r.content, 'html.parser')

    results = []
    for a_element in soup.find_all('a', class_='result-link'):
        results.append(dict(
            name=a_element.text.strip(),
            url=a_element.get('href'),
        ))

    return results


# https://github.com/Harkame/JapScanDownloader
def unscramble_image(image):
    """Unscramble an image

    :param image: PIL.Image.Image or bytes object
    """
    if not isinstance(image, Image.Image):
        image = Image.open(io.BytesIO(image))

    temp = Image.new('RGB', image.size)
    output_image = Image.new('RGB', image.size)

    for x in range(0, image.width, 200):
        col1 = image.crop((x, 0, x + 100, image.height))

        if x + 200 <= image.width:
            col2 = image.crop((x + 100, 0, x + 200, image.height))
            temp.paste(col1, (x + 100, 0))
            temp.paste(col2, (x, 0))
        else:
            col2 = image.crop((x + 100, 0, image.width, image.height))
            temp.paste(col1, (x, 0))
            temp.paste(col2, (x + 100, 0))

    for y in range(0, temp.height, 200):
        row1 = temp.crop((0, y, temp.width, y + 100))

        if y + 200 <= temp.height:
            row2 = temp.crop((0, y + 100, temp.width, y + 200))
            output_image.paste(row1, (0, y + 100))
            output_image.paste(row2, (0, y))
        else:
            row2 = temp.crop((0, y + 100, temp.width, temp.height))
            output_image.paste(row1, (0, y))
            output_image.paste(row2, (0, y + 100))

    return output_image
