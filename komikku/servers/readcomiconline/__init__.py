# -*- coding: utf-8 -*-

# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import BeautifulSoup
import functools
import logging
import requests
import time

from gi.repository import GLib
from gi.repository import WebKit2

from komikku.servers import headless_browser
from komikku.servers import Server
from komikku.servers import USER_AGENT_MOBILE
from komikku.servers.exceptions import CloudflareBypassError
from komikku.servers.utils import get_buffer_mime_type

headers = {
    'User-Agent': USER_AGENT_MOBILE,
    'Origin': 'https://readcomiconline.li',
}

logger = logging.getLogger('komikku.servers.readcomiconline')


def bypass_cloudflare(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        server = args[0]
        if server.session:
            return func(*args, **kwargs)

        cf_reload_count = -1
        done = False
        error = None

        def load_page():
            if not headless_browser.open(server.base_url, user_agent=USER_AGENT_MOBILE):
                return True

            headless_browser.connect_signal('load-changed', on_load_changed)
            headless_browser.connect_signal('load-failed', on_load_failed)
            headless_browser.connect_signal('notify::title', on_title_changed)

        def on_load_changed(webview, event):
            nonlocal cf_reload_count
            nonlocal error

            if event != WebKit2.LoadEvent.COMMITTED:
                return

            cf_reload_count += 1
            if cf_reload_count > 20:
                error = 'Max Cloudflare reload exceeded'
                headless_browser.close()
                return

            # Detect end of Cloudflare challenge via JavaScript
            js = """
                const checkCF = setInterval(() => {
                    if (!document.getElementById('cf-content')) {
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
            server.session.headers.update({'User-Agent': USER_AGENT_MOBILE})

            for cookie in cookie_manager.get_cookies_finish(result):
                rcookie = requests.cookies.create_cookie(
                    name=cookie.name,
                    value=cookie.value,
                    domain=cookie.domain,
                    path=cookie.path,
                    expires=cookie.expires.to_time_t() if cookie.expires else None,
                )
                server.session.cookies.set_cookie(rcookie)

            done = True
            headless_browser.close()

        GLib.timeout_add(100, load_page)

        while not done and error is None:
            time.sleep(.1)

        if error:
            logger.warning(error)
            raise CloudflareBypassError

        return func(*args, **kwargs)

    return wrapper


def get_chapter_page_html(url):
    error = None
    html = None

    def load_page():
        if not headless_browser.open(url, user_agent=USER_AGENT_MOBILE):
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

        # Wait until all images URLs are inserted in DOM
        js = """
            const checkReady = setInterval(() => {
                if (document.querySelectorAll('#divImage img[src^="http"]').length === document.querySelectorAll('#divImage img').length) {
                    clearInterval(checkReady);
                    document.title = 'ready';
                }
            }, 100);
        """

        headless_browser.webview.run_javascript(js, None, None, None)

    def on_load_failed(_webview, _event, _uri, gerror):
        nonlocal error

        error = f'Failed to load chapter page: {url}'

        headless_browser.close()

    def on_title_changed(_webview, _title):
        if headless_browser.webview.props.title == 'ready':
            # All images have been inserted in DOM, we can retrieve page HTML
            headless_browser.webview.run_javascript('document.documentElement.outerHTML', None, on_get_html_finish, None)

    GLib.timeout_add(100, load_page)

    while html is None and error is None:
        time.sleep(.1)

    if error:
        logger.warning(error)
        raise requests.exceptions.RequestException()

    return html


class Readcomiconline(Server):
    id = 'readcomiconline'
    name = 'Read Comic Online'
    lang = 'en'

    base_url = 'https://readcomiconline.li'
    most_populars_url = base_url + '/ComicList/MostPopular'
    search_url = base_url + '/Search/SearchSuggest'
    manga_url = base_url + '/Comic/{0}'
    chapter_url = base_url + '/Comic/{0}/{1}'

    def __init__(self):
        self.session = None

    @bypass_cloudflare
    def get_manga_data(self, initial_data):
        """
        Returns comic data by scraping manga HTML page content

        Initial data should contain at least comic's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(self.manga_url.format(initial_data['slug'], 1))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],  # not available
            genres=[],
            status=None,
            synopsis=None,
            chapters=[],
            server_id=self.id,
            cover=None,
        ))

        soup = BeautifulSoup(r.content, 'html.parser')

        info_elements = soup.select_one('div.col.info')

        data['name'] = soup.select('.heading h3')[0].text.strip()
        cover_path = soup.select_one('div.col.cover img').get('src')
        if cover_path.startswith('http'):
            data['cover'] = cover_path
        else:
            data['cover'] = '{0}{1}'.format(self.base_url, cover_path)

        for p_element in info_elements.find_all('p'):
            if not p_element.span:
                continue

            span_element = p_element.span.extract()
            label = span_element.text.strip()

            if label.startswith('Genres'):
                data['genres'] = [a_element.text.strip() for a_element in p_element.find_all('a')]

            elif label.startswith(('Writer', 'Artist')):
                for a_element in p_element.find_all('a'):
                    value = a_element.text.strip()
                    if value not in data['authors']:
                        data['authors'].append(value)

            elif label.startswith('Status'):
                value = p_element.text.strip()
                if 'Completed' in value:
                    data['status'] = 'complete'
                elif 'Ongoing' in value:
                    data['status'] = 'ongoing'

        data['synopsis'] = soup.select_one('div.main > div > div:nth-child(4) > div:nth-child(3)').text.strip()

        # Chapters (Issues)
        for li_element in reversed(soup.find('ul', class_='list').find_all('li')):
            data['chapters'].append(dict(
                slug=li_element.a.get('href').split('?')[0].split('/')[-1],
                title=li_element.a.text.strip(),
                date=None,  # Not available in mobile version
            ))

        return data

    @bypass_cloudflare
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns comic chapter data

        Currently, only pages are expected.
        """
        html = get_chapter_page_html(self.chapter_url.format(manga_slug, chapter_slug))

        soup = BeautifulSoup(html, 'html.parser')

        data = dict(
            pages=[],
        )
        for img_element in soup.select('#divImage img'):
            data['pages'].append(dict(
                image=img_element.get('src'),
                slug=None,
            ))

        return data

    @bypass_cloudflare
    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(page['image'])
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
        Returns comic absolute URL
        """
        return self.manga_url.format(slug)

    @bypass_cloudflare
    def get_most_populars(self):
        """
        Returns most popular comics list
        """
        results = []

        r = self.session.get(self.most_populars_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'html.parser')

        for element in soup.find('div', class_='item-list').find_all(class_='info'):
            a_element = element.p.a
            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
            ))

        return results

    @bypass_cloudflare
    def search(self, term):
        results = []
        term = term.lower()

        r = self.session.post(
            self.search_url,
            data=dict(
                type='Comic',
                keyword=term
            ),
            headers={
                'x-requested-with': 'XMLHttpRequest',
                'referer': self.base_url
            }
        )
        if r.status_code != 200:
            return None
        if not r.text:
            # No results
            return results

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'text/html':
            return None

        soup = BeautifulSoup(r.content, 'html.parser')

        for a_element in soup:
            if not a_element.get('href'):
                continue

            results.append(dict(
                name=a_element.text.strip(),
                slug=a_element.get('href').split('/')[-1],
            ))

        return results
