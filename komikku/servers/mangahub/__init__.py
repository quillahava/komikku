# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: ISO-morphism <me@iso-morphism.name>

import cloudscraper
from functools import wraps
import json
import logging

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type
from komikku.servers.utils import convert_date_string

logger = logging.getLogger('komikku.servers.mangahub')


def get_api_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        server = args[0]
        if not server.api_key:
            server.session_get(server.base_url)
            for cookie in server.session.cookies:
                if cookie.name == 'mhub_access':
                    server.api_key = cookie.value
                    break

        return func(*args, **kwargs)

    return wrapper


class Mangahub(Server):
    id = 'mangahub'
    name = 'MangaHub'
    lang = 'en'
    long_strip_genres = ['Webtoon', 'Webtoons', 'LONG STRIP', 'LONG STRIP ROMANCE', ]

    base_url = 'https://mangahub.io'
    search_url = base_url + '/search'
    manga_url = base_url + '/manga/{0}'
    chapter_url = base_url + '/chapter/{0}/{1}'
    api_url = 'https://api.mghubcdn.com/graphql'
    image_url = 'https://img.mghubcdn.com/file/imghub/{0}'
    cover_url = 'https://thumb.mghubcdn.com/{0}'

    def __init__(self):
        self.api_key = None

        if self.session is None:
            self.session = cloudscraper.create_scraper()
            self.session.headers = {
                'User-Agent': USER_AGENT,
            }

    @get_api_key
    def get_manga_data(self, initial_data):
        """
        Returns manga data via GraphQL API.

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        query = {
            'query': '{latestPopular(x:m01){id,rank,title,slug,image,latestChapter,unauthFile,updatedDate}manga(x:m01,slug:"%s"){id,rank,title,slug,status,image,latestChapter,author,artist,genres,description,alternativeTitle,mainSlug,isYaoi,isPorn,isSoftPorn,unauthFile,noCoverAd,isLicensed,createdDate,updatedDate,chapters{id,number,title,slug,date}}}' % initial_data['slug']
        }
        r = self.session.post(
            self.api_url,
            json=query,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Referer': self.base_url + '/',
                'Origin': self.base_url,
                'x-mhub-access': self.api_key,
            }
        )
        if r.status_code != 200:
            return None

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

        manga = r.json()['data']['manga']

        data['name'] = manga['title']
        data['cover'] = self.cover_url.format(manga['image'])

        # Details
        data['authors'] = [author.strip() for author in manga['author'].split(',')]
        for artist in manga['artist'].split(','):
            artist = artist.strip()
            if artist not in data['authors']:
                data['authors'].append(artist)

        data['genres'] = [genre.strip() for genre in manga['genres'].split(',')]

        if manga['status'] == 'ongoing':
            data['status'] = 'ongoing'
        elif manga['status'] == 'completed':
            data['status'] = 'complete'

        data['synopsis'] = manga['description']

        # Chapters
        for chapter in manga['chapters']:
            if chapter['title']:
                title = '#{0} - {1}'.format(chapter['number'], chapter['title'])
            else:
                title = '#{0}'.format(chapter['number'])

            data['chapters'].append(dict(
                slug='chapter-{}'.format(chapter['number']),
                title=title,
                date=convert_date_string(chapter['date'].split('T')[0], format='%Y-%m-%d'),
            ))

        return data

    @get_api_key
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns chapter's data via GraphQL API

        Currently, only pages are expected.
        """
        query = {
            'query': '{chapter(x:m01,slug:"%s",number:%s){id,title,mangaID,number,slug,date,pages,noAd,manga{id,title,slug,mainSlug,author,isWebtoon,isYaoi,isPorn,isSoftPorn,unauthFile,isLicensed}}}' % (manga_slug, chapter_slug.replace('chapter-', ''))
        }
        r = self.session_post(
            self.api_url,
            json=query,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Referer': self.base_url + '/',
                'Origin': self.base_url,
                'x-mhub-access': self.api_key,
            },
        )
        if r.status_code != 200:
            return None

        data = dict(
            pages=[],
        )

        pages = json.loads(r.json()['data']['chapter']['pages'])
        for path in pages.values():
            data['pages'].append(dict(
                slug=path,
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(
            self.image_url.format(page['slug']),
            headers={
                'Accept': 'image/webp,image/*;q=0.8,*/*;q=0.5',
                'Referer': self.chapter_url.format(manga_slug, chapter_slug),
            },
        )
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=r.content,
            mime_type=mime_type,
            name=page['slug'].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    def get_most_populars(self):
        """
        Returns most popular manga list
        """
        return self.search('', populars=True)

    @get_api_key
    def search(self, term, populars=False):
        if populars:
            query = {
                'query': '{latestPopular(x:m01){id,title,slug,image,latestChapter,unauthFile}}'
            }
        else:
            query = {
                'query': '{search(x:m01,q:"%s",limit:10){rows{id,title,slug,image,rank,latestChapter,createdDate}}}' % term
            }

        r = self.session.post(self.api_url, json=query, headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Referer': self.base_url + '/',
            'Origin': self.base_url,
            'x-mhub-access': self.api_key,
        })
        if r.status_code != 200:
            return None

        if populars:
            data = r.json()['data']['latestPopular']
        else:
            data = r.json()['data']['search']['rows']

        results = []
        for row in data:
            results.append(dict(
                slug=row['slug'],
                name=row['title'],
            ))

        return results
