# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from functools import wraps
from gettext import gettext as _
import gi
import inspect
import logging
import os
import platform
import requests
import time

try:
    gi.require_version('WebKit', '6.0')
    from gi.repository import WebKit
    IS_WEBKITGTK6 = True
except ValueError:
    gi.require_version('WebKit2', '5.0')
    from gi.repository import WebKit2 as WebKit
    IS_WEBKITGTK6 = False

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from komikku.servers.exceptions import CfBypassError
from komikku.utils import get_cache_dir

CF_RELOAD_MAX = 5
DEBUG = False
USER_AGENT = f'Mozilla/5.0 (X11; Linux {platform.machine()}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15'

logger = logging.getLogger('komikku.webview')


class Webview(Gtk.ScrolledWindow):
    __gsignals__ = {
        'exited': (GObject.SIGNAL_RUN_FIRST, None, ()),
    }

    lock = False

    def __init__(self, window):
        self.__handlers_ids = []
        self.window = window

        self.title_label = self.window.webview_title_label
        self.subtitle_label = self.window.webview_subtitle_label

        Gtk.ScrolledWindow.__init__(self)

        self.get_hscrollbar().set_visible(False)
        self.get_vscrollbar().set_visible(False)

        self.webkit_webview = WebKit.WebView()
        self.set_child(self.webkit_webview)

        self.webkit_webview.get_context().set_cache_model(WebKit.CacheModel.DOCUMENT_VIEWER)
        if IS_WEBKITGTK6:
            self.session_or_context = self.webkit_webview.get_network_session()
        else:
            self.session_or_context = self.webkit_webview.get_context()
        self.session_or_context.set_tls_errors_policy(WebKit.TLSErrorsPolicy.IGNORE)
        self.session_or_context.get_cookie_manager().set_persistent_storage(
            os.path.join(get_cache_dir(), 'WebKitPersistentStorage.sqlite'),
            WebKit.CookiePersistentStorage.SQLITE
        )
        self.session_or_context.get_cookie_manager().set_accept_policy(WebKit.CookieAcceptPolicy.ALWAYS)

        self.window.stack.add_named(self, 'webview')

    def close(self, blank=True):
        self.disconnect_all_signals()

        if blank:
            GLib.idle_add(self.webkit_webview.load_uri, 'about:blank')

        self.lock = False
        logger.debug('Page closed')

    def connect_signal(self, *args):
        handler_id = self.webkit_webview.connect(*args)
        self.__handlers_ids.append(handler_id)

    def disconnect_all_signals(self):
        for handler_id in self.__handlers_ids:
            self.webkit_webview.disconnect(handler_id)

        self.__handlers_ids = []

    def navigate_back(self, source):
        if source is None and self.window.page != 'webview':
            return

        if source:
            self.emit('exited')

        getattr(self.window, self.window.previous_page).show(reset=False)

    def open(self, uri, user_agent=None, settings=None):
        if self.lock:
            return False

        self.webkit_webview.get_settings().set_enable_developer_extras(DEBUG)
        self.webkit_webview.get_settings().set_user_agent(user_agent or USER_AGENT)
        self.webkit_webview.get_settings().set_auto_load_images(True)

        self.lock = True

        logger.debug('Load page %s', uri)

        def do_load():
            self.webkit_webview.load_uri(uri)

        GLib.idle_add(do_load)

        return True

    def show(self, transition=True, reset=False):
        self.window.left_button.set_tooltip_text(_('Back'))
        self.window.left_button.set_icon_name('go-previous-symbolic')
        self.window.left_extra_button_stack.set_visible(False)

        self.window.right_button_stack.set_visible(False)

        self.window.menu_button.set_visible(False)

        self.window.show_page('webview', transition=transition)


def bypass_cf(func):
    """Allows to bypass CF challenge using headless browser"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        bound_args = inspect.signature(func).bind(*args, **kwargs)
        args_dict = dict(bound_args.arguments)

        server = args_dict['self']
        url = server.bypass_cf_url or server.base_url

        if not server.has_cf:
            return func(*args, **kwargs)

        if server.session is None:
            # Try loading a previous session
            server.load_session()

        if server.session:
            logger.debug(f'{server.id}: Previous session found')
            # Locate CF cookie
            bypassed = False
            for cookie in server.session.cookies:
                if cookie.name == 'cf_clearance':
                    # CF cookie is there
                    bypassed = True
                    break

            if bypassed:
                logger.debug(f'{server.id}: Session has CF cookie. Checking...')
                # Check session validity
                r = server.session_get(url)
                if r.status_code == 200:
                    logger.debug(f'{server.id}: Session OK')
                    return func(*args, **kwargs)
                else:
                    logger.debug(f'{server.id}: Session KO')
            else:
                logger.debug(f'{server.id}: Session has no CF cookie. Loading page in webview...')

        cf_reload_count = -1
        done = False
        error = None
        webview = Gio.Application.get_default().window.webview

        # Gnome Web user agent
        cpu_arch = platform.machine()
        user_agent = f'Mozilla/5.0 (X11; Linux {cpu_arch}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15'

        def load_page():
            if not webview.open(url, user_agent=user_agent):
                return True

            webview.connect_signal('load-changed', on_load_changed)
            webview.connect_signal('load-failed', on_load_failed)
            webview.connect_signal('notify::title', on_title_changed)

        def on_load_changed(_webkit_webview, event):
            nonlocal cf_reload_count
            nonlocal error

            if event != WebKit.LoadEvent.REDIRECTED and '__cf_chl_tk' in webview.webkit_webview.get_uri():
                # Challenge has been passed

                # Disable images auto-load
                webview.webkit_webview.get_settings().set_auto_load_images(False)

                # Exit from webview
                webview.navigate_back(None)

            if event != WebKit.LoadEvent.FINISHED:
                return

            cf_reload_count += 1
            if cf_reload_count > CF_RELOAD_MAX:
                error = 'Max CF reload exceeded'
                webview.close()
                return

            # Detect end of CF challenge via JavaScript
            js = """
                let checkCF = setInterval(() => {
                    if (!document.getElementById('challenge-running')) {
                        document.title = 'ready';
                        clearInterval(checkCF);
                    }
                    else if (document.querySelector('input.pow-button')) {
                        // button
                        document.title = 'captcha 1';
                    }
                    else if (document.querySelector('iframe[id^="cf-chl-widget"]')) {
                        // checkbox in an iframe
                        document.title = 'captcha 2';
                    }
                }, 100);
            """
            webview.webkit_webview.run_javascript(js, None, None)

        def on_load_failed(_webkit_webview, _event, uri, _gerror):
            nonlocal error

            error = f'CF challenge bypass failure: {uri}'

            webview.close()

        def on_title_changed(_webkit_webview, title):
            if webview.webkit_webview.props.title.startswith('captcha'):
                logger.debug(f'{server.id}: Captcha `{webview.webkit_webview.props.title}` detected')
                # Show webview, user must complete a CAPTCHA
                webview.title_label.set_text(_('Please complete CAPTCHA'))
                webview.subtitle_label.set_text(server.name)
                webview.show()

            if webview.webkit_webview.props.title != 'ready':
                return

            logger.debug(f'{server.id}: Page loaded, getting cookies...')
            cookie_manager = webview.session_or_context.get_cookie_manager()
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

            logger.debug(f'{server.id}: Webview cookies successully copied in requests session')
            server.save_session()

            done = True
            webview.close()

        def on_webview_exited(_webkit_webview):
            nonlocal error

            error = 'CF challenge bypass aborted'

            webview.close()

        webview.connect('exited', on_webview_exited)
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
    webview = Gio.Application.get_default().window.webview

    def load_page():
        if not webview.open(url, user_agent=user_agent):
            return True

        webview.connect_signal('load-changed', on_load_changed)
        webview.connect_signal('load-failed', on_load_failed)
        webview.connect_signal('notify::title', on_title_changed)

        if DEBUG:
            webview.show()

    def on_get_html_finish(_webkit_webview, result, user_data=None):
        nonlocal error
        nonlocal html

        js_result = webview.webkit_webview.run_javascript_finish(result)
        if js_result:
            js_value = js_result.get_js_value()
            if js_value:
                html = js_value.to_string()

        if html is None:
            error = f'Failed to get chapter page html: {url}'

        webview.close()

    def on_load_changed(_webkit_webview, event):
        if event != WebKit.LoadEvent.FINISHED:
            return

        if wait_js_code:
            # Wait that everything needed has been loaded
            webview.webkit_webview.run_javascript(wait_js_code, None, None, None)
        else:
            webview.webkit_webview.run_javascript('document.documentElement.outerHTML', None, on_get_html_finish, None)

    def on_load_failed(_webkit_webview, _event, _uri, gerror):
        nonlocal error

        error = f'Failed to load chapter page: {url}'

        webview.close()

    def on_title_changed(_webkit_webview, _title):
        nonlocal error

        if webview.webkit_webview.props.title == 'ready':
            # Everything we need has been loaded, we can retrieve page HTML
            webview.webkit_webview.run_javascript('document.documentElement.outerHTML', None, on_get_html_finish, None)
        elif webview.webkit_webview.props.title == 'abort':
            error = f'Failed to get chapter page html: {url}'
            webview.close()

    GLib.timeout_add(100, load_page)

    while html is None and error is None:
        time.sleep(.1)

    if error:
        logger.warning(error)
        raise requests.exceptions.RequestException()

    return html
