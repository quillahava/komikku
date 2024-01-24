# Copyright (C) 2019-2024 Valéry Febvre
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
import tzlocal

gi.require_version('WebKit', '6.0')

from gi.repository import Adw
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import WebKit

from komikku.servers.exceptions import CfBypassError
from komikku.utils import get_cache_dir

CF_RELOAD_MAX = 3
DEBUG = False

logger = logging.getLogger('komikku.webview')


@Gtk.Template.from_resource('/info/febvre/Komikku/ui/webview.ui')
class WebviewPage(Adw.NavigationPage):
    __gtype_name__ = 'WebviewPage'
    __gsignals__ = {
        'exited': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    toolbarview = Gtk.Template.Child('toolbarview')
    title = Gtk.Template.Child('title')

    auto_exited = False
    exited = False
    lock = False
    user_agent = None

    def __init__(self, window):
        Adw.NavigationPage.__init__(self)

        self.__handlers_ids = []
        self.__handlers_webview_ids = []
        self.window = window

        self.connect('hidden', self.on_hidden)

        # User agent: Gnome Web like
        cpu_arch = platform.machine()
        session_type = GLib.getenv('XDG_SESSION_TYPE').capitalize()
        custom_part = f'{session_type}; Linux {cpu_arch}'
        self.user_agent = f'Mozilla/5.0 ({custom_part}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'

        # WebKit WebView
        self.settings = WebKit.Settings.new()
        self.settings.set_enable_developer_extras(DEBUG)
        self.settings.set_enable_write_console_messages_to_stdout(DEBUG)
        self.settings.set_enable_dns_prefetching(True)

        # Enable extra features
        all_feature_list = self.settings.get_all_features()
        if DEBUG:
            experimental_feature_list = self.settings.get_experimental_features()
            development_feature_list = self.settings.get_development_features()
            experimental_features = [
                experimental_feature_list.get(index).get_identifier() for index in range(experimental_feature_list.get_length())
            ]
            development_features = [
                development_feature_list.get(index).get_identifier() for index in range(development_feature_list.get_length())
            ]

            # Categories: Security, Animation, JavaScript, HTML, Other, DOM, Privacy, Media, Network, CSS
            for index in range(all_feature_list.get_length()):
                feature = all_feature_list.get(index)
                if feature.get_identifier() in experimental_features:
                    type = 'Experimental'
                elif feature.get_identifier() in development_features:
                    type = 'Development'
                else:
                    type = 'Stable'
                if feature.get_category() == 'Other' and not feature.get_default_value():
                    print('ID: {0}, Default: {1}, Category: {2}, Details: {3}, type: {4}'.format(
                        feature.get_identifier(),
                        feature.get_default_value(),
                        feature.get_category(),
                        feature.get_details(),
                        type
                    ))

        extra_features_enabled = (
            'AllowDisplayOfInsecureContent',
            'AllowRunningOfInsecureContent',
            'JavaScriptCanAccessClipboard',
        )
        for index in range(all_feature_list.get_length()):
            feature = all_feature_list.get(index)
            if feature.get_identifier() in extra_features_enabled and not feature.get_default_value():
                self.settings.set_feature_enabled(feature, True)

        self.web_context = WebKit.WebContext(time_zone_override=tzlocal.get_localzone_name())
        self.web_context.set_cache_model(WebKit.CacheModel.DOCUMENT_VIEWER)
        self.web_context.set_preferred_languages(['en-US', 'en'])

        self.network_session = WebKit.NetworkSession.new(
            os.path.join(get_cache_dir(), 'webview', 'data'),
            os.path.join(get_cache_dir(), 'webview', 'cache')
        )
        self.network_session.get_website_data_manager().set_favicons_enabled(True)
        self.network_session.set_itp_enabled(False)
        self.network_session.get_cookie_manager().set_accept_policy(WebKit.CookieAcceptPolicy.ALWAYS)
        self.network_session.get_cookie_manager().set_persistent_storage(
            os.path.join(get_cache_dir(), 'webview', 'cookies.sqlite'),
            WebKit.CookiePersistentStorage.SQLITE
        )

        self.webkit_webview = WebKit.WebView(
            web_context=self.web_context,
            network_session=self.network_session,
            settings=self.settings
        )

        self.toolbarview.set_content(self.webkit_webview)
        self.window.navigationview.add(self)

    def close(self, blank=True):
        self.disconnect_all_signals()

        if blank:
            self.webkit_webview.stop_loading()
            GLib.idle_add(self.webkit_webview.load_uri, 'about:blank')

        self.lock = False
        logger.debug('Page closed')

    def connect_signal(self, *args):
        handler_id = self.connect(*args)
        self.__handlers_ids.append(handler_id)

    def connect_webview_signal(self, *args):
        handler_id = self.webkit_webview.connect(*args)
        self.__handlers_webview_ids.append(handler_id)

    def disconnect_all_signals(self):
        for handler_id in self.__handlers_ids:
            self.disconnect(handler_id)

        self.__handlers_ids = []

        for handler_id in self.__handlers_webview_ids:
            self.webkit_webview.disconnect(handler_id)

        self.__handlers_webview_ids = []

    def exit(self):
        if self.window.page != self.props.tag or self.exited:
            return

        self.exited = True
        self.auto_exited = True

        self.window.navigationview.pop()

    def on_hidden(self, _page):
        self.exited = True
        if not self.auto_exited:
            # Emit exited signal only if webview page is left via a user interaction
            self.emit('exited')

    def open(self, uri, user_agent=None):
        if self.lock:
            return False

        self.webkit_webview.get_settings().set_user_agent(user_agent or self.user_agent)
        self.webkit_webview.get_settings().set_auto_load_images(True)

        self.auto_exited = False
        self.exited = False
        self.lock = True

        logger.debug('Load page %s', uri)

        self.webkit_webview.load_uri(uri)

        return True

    def show(self):
        self.window.navigationview.push(self)


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
                if r.ok:
                    logger.debug(f'{server.id}: Session OK')
                    return func(*args, **kwargs)

                logger.debug(f'{server.id}: Session KO ({r.status_code})')
            else:
                logger.debug(f'{server.id}: Session has no CF cookie. Loading page in webview...')

        cf_reload_count = -1
        done = False
        error = None
        loaded = False

        webview = Gio.Application.get_default().window.webview

        def load_page():
            if not webview.open(url):
                logger.debug('Load page: locked => wait')
                return GLib.SOURCE_CONTINUE

        def on_load_changed(_webkit_webview, event):
            nonlocal cf_reload_count
            nonlocal error
            nonlocal loaded

            logger.debug(f'load changed: {event}')

            if event != WebKit.LoadEvent.STARTED:
                loaded = False

            elif event != WebKit.LoadEvent.REDIRECTED and '__cf_chl_tk' in webview.webkit_webview.get_uri():
                # Challenge has been passed and followed by a redirect

                # Disable images auto-load
                webview.webkit_webview.get_settings().set_auto_load_images(False)

                # Exit from webview
                # Webview should not be closed, we need to store cookies first
                webview.exit()

            elif event == WebKit.LoadEvent.FINISHED:
                cf_reload_count += 1
                if cf_reload_count > CF_RELOAD_MAX:
                    error = 'Max CF reload exceeded'
                    webview.close()
                    webview.exit()

        def on_load_failed(_webkit_webview, _event, uri, _gerror):
            nonlocal error

            error = f'CF challenge bypass failure: {uri}'

            webview.close()
            webview.exit()

        def on_title_changed(_webkit_webview, _title):
            nonlocal loaded

            if webview.webkit_webview.props.title.startswith('captcha'):
                logger.debug(f'{server.id}: Captcha `{webview.webkit_webview.props.title}` detected')

                # Show webview, user must complete a CAPTCHA
                webview.title.set_title(_('Please complete CAPTCHA'))
                webview.title.set_subtitle(server.name)
                if webview.window.page != webview.props.tag:
                    webview.show()

                return

            if webview.webkit_webview.props.title != 'ready':
                # We can't rely on `load-changed` event to detect if page is loaded or at least can be considered as loaded
                # because sometime FINISHED event never appends.
                # Instead, we consider page adequately loaded when its title is defined.
                if not loaded:
                    loaded = True
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
                    webview.webkit_webview.evaluate_javascript(js, -1)

                return

            # Challenge has been passed
            # Exit from webview if end of chalenge has not been detected in on_load_changed
            # Webview should not be closed, we need to store cookies first
            webview.exit()

            logger.debug(f'{server.id}: Page loaded, getting cookies...')
            webview.network_session.get_cookie_manager().get_cookies(server.base_url, None, on_get_cookies_finish, None)

        def on_get_cookies_finish(cookie_manager, result, _user_data):
            nonlocal done

            server.session = requests.Session()
            server.session.headers.update({'User-Agent': webview.user_agent})

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

        webview.connect_signal('exited', on_webview_exited)
        webview.connect_webview_signal('load-changed', on_load_changed)
        webview.connect_webview_signal('load-failed', on_load_failed)
        webview.connect_webview_signal('notify::title', on_title_changed)

        GLib.timeout_add(100, load_page)

        while not done and error is None:
            time.sleep(.1)

        if error:
            logger.warning(error)
            raise CfBypassError

        return func(*args, **kwargs)

    return wrapper


def eval_js(code):
    error = None
    res = None
    webview = Gio.Application.get_default().window.webview

    def load_page():
        if not webview.open('about:blank'):
            return True

        webview.connect_webview_signal('load-changed', on_load_changed)

        if DEBUG:
            webview.show()

    def on_evaluate_javascript_finish(_webkit_webview, result, _user_data=None):
        nonlocal error
        nonlocal res

        try:
            js_result = webview.webkit_webview.evaluate_javascript_finish(result)
        except GLib.GError:
            error = 'Failed to eval JS code'
        else:
            if js_result.is_string():
                res = js_result.to_string()

            if res is None:
                error = 'Failed to eval JS code'

        webview.close()

    def on_load_changed(_webkit_webview, event):
        if event != WebKit.LoadEvent.FINISHED:
            return

        webview.webkit_webview.evaluate_javascript(code, -1, None, None, None, on_evaluate_javascript_finish)

    GLib.timeout_add(100, load_page)

    while res is None and error is None:
        time.sleep(.1)

    if error:
        logger.warning(error)
        raise requests.exceptions.RequestException()

    return res


def get_page_html(url, user_agent=None, wait_js_code=None):
    error = None
    html = None
    webview = Gio.Application.get_default().window.webview

    def load_page():
        if not webview.open(url, user_agent=user_agent):
            return True

        webview.connect_webview_signal('load-changed', on_load_changed)
        webview.connect_webview_signal('load-failed', on_load_failed)
        webview.connect_webview_signal('notify::title', on_title_changed)

        if DEBUG:
            webview.show()

    def on_get_html_finish(_webkit_webview, result, _user_data=None):
        nonlocal error
        nonlocal html

        js_result = webview.webkit_webview.evaluate_javascript_finish(result)
        if js_result:
            html = js_result.to_string()

        if html is None:
            error = f'Failed to get chapter page html: {url}'

        webview.close()

    def on_load_changed(_webkit_webview, event):
        if event != WebKit.LoadEvent.FINISHED:
            return

        if wait_js_code:
            # Wait that everything needed has been loaded
            webview.webkit_webview.evaluate_javascript(wait_js_code, -1)
        else:
            webview.webkit_webview.evaluate_javascript('document.documentElement.outerHTML', -1, None, None, None, on_get_html_finish)

    def on_load_failed(_webkit_webview, _event, _uri, _gerror):
        nonlocal error

        error = f'Failed to load chapter page: {url}'

        webview.close()

    def on_title_changed(_webkit_webview, _title):
        nonlocal error

        if webview.webkit_webview.props.title == 'ready':
            # Everything we need has been loaded, we can retrieve page HTML
            webview.webkit_webview.evaluate_javascript('document.documentElement.outerHTML', -1, None, None, None, on_get_html_finish)

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
