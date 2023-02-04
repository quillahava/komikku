# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from functools import wraps
import gi
import logging
import os
import requests
import time

gi.require_version('WebKit2', '5.0')

from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import WebKit2

from komikku.servers import USER_AGENT
from komikku.servers.exceptions import CfBypassError
from komikku.utils import get_cache_dir

CF_RELOAD_MAX = 20
logger = logging.getLogger('komikku.servers.headless_browser')


class HeadlessBrowser(Gtk.Window):
    lock = False

    def __init__(self, *args, **kwargs):
        self.__handlers_ids = []
        self.debug = kwargs.pop('debug', False)

        super().__init__(*args, **kwargs)

        self.scrolledwindow = Gtk.ScrolledWindow()
        self.scrolledwindow.get_hscrollbar().hide()
        self.scrolledwindow.get_vscrollbar().hide()

        self.viewport = Gtk.Viewport()
        self.scrolledwindow.set_child(self.viewport)
        self.set_child(self.scrolledwindow)

        self.webview = WebKit2.WebView()
        self.viewport.set_child(self.webview)

        self.settings = WebKit2.Settings()
        self.settings.set_enable_javascript(True)
        self.settings.set_enable_page_cache(False)
        self.settings.set_enable_frame_flattening(True)
        self.settings.set_enable_accelerated_2d_canvas(True)
        self.settings.props.enable_developer_extras = self.debug

        data_manager = WebKit2.WebsiteDataManager()
        data_manager.set_itp_enabled(False)

        self.web_context = self.webview.get_context()
        self.web_context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
        self.web_context.set_tls_errors_policy(WebKit2.TLSErrorsPolicy.IGNORE)
        self.web_context.get_cookie_manager().set_persistent_storage(
            os.path.join(get_cache_dir(), 'WebKitPersistentStorage.sqlite'),
            WebKit2.CookiePersistentStorage.SQLITE
        )
        self.web_context.get_cookie_manager().set_accept_policy(WebKit2.CookieAcceptPolicy.ALWAYS)

        if not self.debug:
            # Make window almost invisible
            self.set_decorated(False)
            self.set_default_size(1, 1)

    def close(self, blank=True):
        logger.debug('WebKit2 | Closed')

        self.disconnect_all_signals()

        if blank:
            GLib.idle_add(self.webview.load_uri, 'about:blank')
        self.hide()

        self.lock = False

    def connect_signal(self, *args):
        handler_id = self.webview.connect(*args)
        self.__handlers_ids.append(handler_id)

    def disconnect_all_signals(self):
        for handler_id in self.__handlers_ids:
            self.webview.disconnect(handler_id)

        self.__handlers_ids = []

    def open(self, uri, user_agent=None, settings=None):
        if self.lock:
            return False

        self.settings.set_user_agent(user_agent or USER_AGENT)
        self.settings.set_auto_load_images(settings.get('auto_load_images', False) if settings else False)

        self.lock = True

        logger.debug('WebKit2 | Load page %s', uri)

        def do_load():
            self.show()

            if not self.debug:
                # Make window almost invisible (part 2)
                self.get_surface().lower()
                self.minimize()

            self.webview.load_uri(uri)

        GLib.idle_add(do_load)

        return True


headless_browser = HeadlessBrowser(debug=True)


def bypass_cf(func):
    """Allows to bypass CF challenge using headless browser"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        server = args[0]

        if not server.has_cf:
            logger.debug('The class attribute `has_cf` must be True to use the @bypass_cf decorator')
            return func(*args, **kwargs)

        if server.session is None:
            # Try loading a previous session
            server.load_session()

        if server.session:
            # Locate cf cookie
            bypassed = False
            for cookie in server.session.cookies:
                if cookie.name == 'cf_clearance':
                    # CF cookie is there
                    bypassed = True
                    break

            if bypassed:
                # Check session validity
                r = server.session_get(server.base_url)
                if r.status_code == 200:
                    return func(*args, **kwargs)

        cf_reload_count = -1
        done = False
        error = None

        # Gnome Web user agent
        user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15'

        def load_page():
            if not headless_browser.open(server.base_url, user_agent=user_agent):
                return True

            headless_browser.connect_signal('load-changed', on_load_changed)
            headless_browser.connect_signal('load-failed', on_load_failed)
            headless_browser.connect_signal('notify::title', on_title_changed)

        def on_load_changed(webview, event):
            nonlocal cf_reload_count
            nonlocal error

            if event != WebKit2.LoadEvent.FINISHED:
                return

            cf_reload_count += 1
            if cf_reload_count > CF_RELOAD_MAX:
                error = 'Max CF reload exceeded'
                headless_browser.close()
                return

            # Detect end of CF challenge via JavaScript
            js = """
                const checkCF = setInterval(() => {
                    if (!document.getElementById('challenge-running')) {
                        clearInterval(checkCF);
                        document.title = 'ready';
                    }
                }, 100);
            """
            headless_browser.webview.run_javascript(js, None, None)

        def on_load_failed(_webview, _event, _uri, gerror):
            nonlocal error

            error = f'Failed to load homepage: {server.base_url}'

            headless_browser.close()

        def on_title_changed(webview, title):
            if headless_browser.webview.props.title != 'ready':
                return

            cookie_manager = headless_browser.web_context.get_cookie_manager()
            cookie_manager.get_cookies(server.base_url, None, on_get_cookies_finish, None)

        def on_get_cookies_finish(cookie_manager, result, user_data):
            nonlocal done

            server.session = requests.Session()
            server.session.headers.update({'User-Agent': user_agent})

            # Copy libsoup cookies in session cookies jar
            for cookie in cookie_manager.get_cookies_finish(result):
                rcookie = requests.cookies.create_cookie(
                    name=cookie.get_name(),
                    value=cookie.get_value(),
                    domain=cookie.get_domain(),
                    path=cookie.get_path(),
                    expires=cookie.get_expires().to_unix() if cookie.get_expires() else None,
                    rest={'HttpOnly': cookie.get_http_only()},
                    secure=cookie.get_secure(),
                )
                server.session.cookies.set_cookie(rcookie)

            server.save_session()

            done = True
            headless_browser.close()

        GLib.timeout_add(100, load_page)

        while not done and error is None:
            time.sleep(.1)

        if error:
            logger.warning(error)
            raise CfBypassError

        return func(*args, **kwargs)

    return wrapper


def bypass_cf_invisible_challenge(func):
    """Allows to bypass CF invisible challenge using headless browser"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        """Decorator Wrapper function"""

        server = args[0]
        if server.session or not server.has_cf_invisible_challenge:
            return func(*args, **kwargs)

        done = False
        error = None

        def load_page():
            if not headless_browser.open(server.base_url, user_agent=USER_AGENT):
                return True

            headless_browser.connect_signal('load-changed', on_load_changed)
            headless_browser.connect_signal('load-failed', on_load_failed)

        def on_load_changed(webview, event):
            if event != WebKit2.LoadEvent.FINISHED:
                return

            cookie_manager = headless_browser.web_context.get_cookie_manager()
            cookie_manager.get_cookies(server.base_url, None, on_get_cookies_finish, None)

        def on_load_failed(_webview, _event, _uri, gerror):
            nonlocal error

            error = f'Failed to load homepage: {server.base_url}'
            headless_browser.close()

        def on_get_cookies_finish(cookie_manager, result, user_data):
            nonlocal done

            server.session = requests.Session()
            server.session.headers.update({'User-Agent': USER_AGENT})

            for cookie in cookie_manager.get_cookies_finish(result):
                rcookie = requests.cookies.create_cookie(
                    name=cookie.get_name(),
                    value=cookie.get_value(),
                    domain=cookie.get_domain(),
                    path=cookie.get_path(),
                    expires=cookie.get_expires().to_unix() if cookie.get_expires() else None,
                )
                server.session.cookies.set_cookie(rcookie)

            done = True
            headless_browser.close()

        GLib.timeout_add(100, load_page)

        while not done and error is None:
            time.sleep(.1)

        if error:
            logger.warning(error)
            raise CfBypassError

        return func(*args, **kwargs)

    return wrapper


def get_page_html(url, user_agent=None, settings=None, wait_js_code=None):
    error = None
    html = None

    def load_page():
        if not headless_browser.open(url, user_agent=user_agent):
            return True

        headless_browser.connect_signal('load-changed', on_load_changed)
        headless_browser.connect_signal('load-failed', on_load_failed)
        headless_browser.connect_signal('notify::title', on_title_changed)

    def on_get_html_finish(webview, result, user_data=None):
        nonlocal error
        nonlocal html

        js_result = webview.run_javascript_finish(result)
        if js_result:
            js_value = js_result.get_js_value()
            if js_value:
                html = js_value.to_string()

        if html is None:
            error = f'Failed to get chapter page html: {url}'

        headless_browser.close()

    def on_load_changed(_webview, event):
        if event != WebKit2.LoadEvent.FINISHED:
            return

        if wait_js_code:
            # Wait that everything needed has been loaded
            headless_browser.webview.run_javascript(wait_js_code, None, None, None)
        else:
            headless_browser.webview.run_javascript('document.documentElement.outerHTML', None, on_get_html_finish, None)

    def on_load_failed(_webview, _event, _uri, gerror):
        nonlocal error

        error = f'Failed to load chapter page: {url}'

        headless_browser.close()

    def on_title_changed(_webview, _title):
        nonlocal error

        if headless_browser.webview.props.title == 'ready':
            # Everything we need has been loaded, we can retrieve page HTML
            headless_browser.webview.run_javascript('document.documentElement.outerHTML', None, on_get_html_finish, None)
        elif headless_browser.webview.props.title == 'abort':
            error = f'Failed to get chapter page html: {url}'
            headless_browser.close()

    GLib.timeout_add(100, load_page)

    while html is None and error is None:
        time.sleep(.1)

    if error:
        logger.warning(error)
        raise requests.exceptions.RequestException()

    return html
