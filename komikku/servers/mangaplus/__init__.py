# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from functools import wraps
import requests
import re
from typing import List
import uuid
import unidecode

from pure_protobuf.dataclasses_ import field, message
from pure_protobuf.types import int32

from komikku.servers import Server
from komikku.servers import USER_AGENT
from komikku.servers.utils import get_buffer_mime_type

LANGUAGES_CODES = dict(
    en='eng',
    es='esp',
    fr='fra',
    pt_BR='ptb',
    ru='rus',
    id='ind',
    th='tha',
    vi='vie',
)
RE_ENCRYPTION_KEY = re.compile('.{1,2}')
SERVER_NAME = 'MANGA Plus by SHUEISHA'

headers = {
    'User-Agent': USER_AGENT,
    'Origin': 'https://mangaplus.shueisha.co.jp',
    'Referer': 'https://mangaplus.shueisha.co.jp',
    'SESSION-TOKEN': repr(uuid.uuid1()),
}


def set_lang(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        server = args[0]
        if not server.is_lang_set:
            server.session_get(server.api_params_url, params=dict(lang=LANGUAGES_CODES[server.lang]))
            server.is_lang_set = True

        return func(*args, **kwargs)

    return wrapper


class Mangaplus(Server):
    id = 'mangaplus'
    name = SERVER_NAME
    lang = 'en'

    is_lang_set = False

    base_url = 'https://mangaplus.shueisha.co.jp'
    api_url = 'https://jumpg-webapi.tokyo-cdn.com/api'
    api_params_url = api_url + '/featured'
    api_search_url = api_url + '/title_list/all'
    api_latest_updates_url = api_url + '/web/web_home?lang={0}'
    api_most_populars_url = api_url + '/title_list/ranking'
    api_manga_url = api_url + '/title_detail?title_id={0}'
    api_chapter_url = api_url + '/manga_viewer?chapter_id={0}&split=yes&img_quality=high'
    manga_url = base_url + '/titles/{0}'

    def __init__(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = headers

    @set_lang
    def get_manga_data(self, initial_data):
        """
        Returns manga data from API

        Initial data should contain at least manga's slug (provided by search)
        """
        assert 'slug' in initial_data, 'Slug is missing in initial data'

        r = self.session_get(self.api_manga_url.format(initial_data['slug']))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'application/octet-stream':
            return None

        resp = MangaplusResponse.loads(r.content)
        if resp.error:
            return None

        resp_data = resp.success.title_detail

        data = initial_data.copy()
        data.update(dict(
            name=resp_data.title.name,
            authors=[resp_data.title.author],
            scanlators=['Shueisha'],
            genres=[],
            status=None,
            synopsis=resp_data.synopsis,
            chapters=[],
            server_id=self.id,
            cover=resp_data.title.portrait_image_url,
        ))

        # Status
        if 'completed' in resp_data.non_appearance_info or 'completado' in resp_data.non_appearance_info:
            data['status'] = 'complete'
        else:
            data['status'] = 'ongoing'

        # Chapters
        for chapters in (resp_data.first_chapters, resp_data.last_chapters):
            for chapter in chapters:
                data['chapters'].append(dict(
                    slug=str(chapter.id),
                    title='{0} - {1}'.format(chapter.name, chapter.subtitle),
                    date=datetime.fromtimestamp(chapter.start_timestamp).date(),
                ))

        return data

    @set_lang
    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        """
        Returns manga chapter data from API

        Currently, only pages are expected.
        """
        r = self.session_get(self.api_chapter_url.format(chapter_slug))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'application/octet-stream':
            return None

        resp = MangaplusResponse.loads(r.content)
        if resp.error:
            return None

        resp_data = resp.success.manga_viewer

        data = dict(
            pages=[],
        )
        for page in resp_data.pages:
            if page.page is None:
                continue

            data['pages'].append(dict(
                slug=None,
                image=page.page.image_url,
                encryption_key=page.page.encryption_key,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        """
        Returns chapter page scan (image) content
        """
        r = self.session_get(page['image'])
        if r.status_code != 200:
            return None

        if page['encryption_key'] is not None:
            # Decryption
            key_stream = [int(v, 16) for v in RE_ENCRYPTION_KEY.findall(page['encryption_key'])]
            block_size_in_bytes = len(key_stream)

            content = bytes([int(v) ^ key_stream[index % block_size_in_bytes] for index, v in enumerate(r.content)])
        else:
            content = r.content

        mime_type = get_buffer_mime_type(content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=content,
            mime_type=mime_type,
            name=page['image'].split('?')[0].split('/')[-1],
        )

    def get_manga_url(self, slug, url):
        """
        Returns manga absolute URL
        """
        return self.manga_url.format(slug)

    @set_lang
    def get_latest_updates(self):
        """
        Returns latest updates
        """
        r = self.session_get(self.api_latest_updates_url.format(LANGUAGES_CODES[self.lang]))
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'application/octet-stream':
            return None

        resp_data = MangaplusResponse.loads(r.content)
        if resp_data.error:
            return None

        results = []
        for group in resp_data.success.web_home_view.update_title_groups:
            for update_title in group.titles:
                title = update_title.title
                if title.language != LanguageEnum.from_code(self.lang):
                    continue

                results.append(dict(
                    slug=title.id,
                    name=title.name,
                    cover=title.portrait_image_url,
                ))

        return results

    @set_lang
    def get_most_populars(self):
        """
        Returns hottest manga list
        """
        r = self.session_get(self.api_most_populars_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'application/octet-stream':
            return None

        resp_data = MangaplusResponse.loads(r.content)
        if resp_data.error:
            return None

        results = []
        for title in resp_data.success.titles_ranking.titles:
            if title.language != LanguageEnum.from_code(self.lang):
                continue

            results.append(dict(
                slug=title.id,
                name=title.name,
                cover=title.portrait_image_url,
            ))

        return results

    @set_lang
    def search(self, term):
        r = self.session_get(self.api_search_url)
        if r.status_code != 200:
            return None

        mime_type = get_buffer_mime_type(r.content)
        if mime_type != 'application/octet-stream':
            return None

        resp_data = MangaplusResponse.loads(r.content)
        if resp_data.error:
            return None

        results = []
        term = unidecode.unidecode(term).lower()
        for title in resp_data.success.titles_all.titles:
            if title.language != LanguageEnum.from_code(self.lang):
                continue
            if term not in unidecode.unidecode(title.name).lower():
                continue

            results.append(dict(
                slug=title.id,
                name=title.name,
                cover=title.portrait_image_url,
            ))

        return results


class Mangaplus_es(Mangaplus):
    id = 'mangaplus_es'
    name = SERVER_NAME
    lang = 'es'


class Mangaplus_fr(Mangaplus):
    id = 'mangaplus_fr'
    name = SERVER_NAME
    lang = 'fr'


class Mangaplus_id(Mangaplus):
    id = 'mangaplus_id'
    name = SERVER_NAME
    lang = 'id'


class Mangaplus_pt_br(Mangaplus):
    id = 'mangaplus_pt_br'
    name = SERVER_NAME
    lang = 'pt_BR'


class Mangaplus_ru(Mangaplus):
    id = 'mangaplus_ru'
    name = SERVER_NAME
    lang = 'ru'


class Mangaplus_th(Mangaplus):
    id = 'mangaplus_th'
    name = SERVER_NAME
    lang = 'th'


class Mangaplus_vi(Mangaplus):
    id = 'mangaplus_vi'
    name = SERVER_NAME
    lang = 'vi'


# Protocol Buffers messages used to deserialize API responses
# https://gist.github.com/ZaneHannanAU/437531300c4df524bdb5fd8a13fbab50

class ActionEnum(IntEnum):
    DEFAULT = 0
    UNAUTHORIZED = 1
    MAINTAINENCE = 2
    GEOIP_BLOCKING = 3


class LanguageEnum(IntEnum):
    ENGLISH = 0
    SPANISH = 1
    FRENCH = 2
    INDONESIAN = 3
    PORTUGUESE_BR = 4
    RUSSIAN = 5
    THAI = 6
    VIET = 9

    @classmethod
    def from_code(cls, code):
        # MUST BE kept in sync with `LANGUAGES_CODES` defined above
        if code == 'en':
            return cls.ENGLISH.value
        if code == 'es':
            return cls.SPANISH.value
        if code == 'fr':
            return cls.FRENCH.value
        if code == 'id':
            return cls.INDONESIAN.value
        if code == 'pt_BR':
            return cls.PORTUGUESE_BR.value
        if code == 'ru':
            return cls.RUSSIAN.value
        if code == 'th':
            return cls.THAI.value
        if code == 'vi':
            return cls.VIET.value


class UpdateTimingEnum(IntEnum):
    NOT_REGULARLY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7
    DAY = 8


@message
@dataclass
class Popup:
    subject: str = field(1)
    body: str = field(2)


@message
@dataclass
class ErrorResult:
    action: ActionEnum = field(1)
    english_popup: Popup = field(2)
    spanish_popup: Popup = field(3)
    debug_info: str = field(4)


@message
@dataclass
class MangaPage:
    image_url: str = field(1)
    width: int32 = field(2)
    height: int32 = field(3)
    encryption_key: str = field(5, default=None)


@message
@dataclass
class Page:
    page: MangaPage = field(1, default=None)


@message
@dataclass
class MangaViewer:
    pages: List[Page] = field(1, default_factory=list)


@message
@dataclass
class Chapter:
    title_id: int32 = field(1)
    id: int32 = field(2)
    name: str = field(3)
    subtitle: str = field(4, default=None)
    start_timestamp: int32 = field(6, default=None)
    end_timestamp: int32 = field(7, default=None)


@message
@dataclass
class Title:
    id: int32 = field(1)
    name: str = field(2)
    author: str = field(3)
    portrait_image_url: str = field(4)
    landscape_image_url: str = field(5)
    view_count: int32 = field(6)
    language: LanguageEnum = field(7, default=LanguageEnum.ENGLISH)


@message
@dataclass
class TitleDetail:
    title: Title = field(1)
    title_image_url: str = field(2)
    synopsis: str = field(3)
    background_image_url: str = field(4)
    next_timestamp: int32 = field(5, default=0)
    update_timimg: UpdateTimingEnum = field(6, default=UpdateTimingEnum.DAY)
    viewing_period_description: str = field(7, default=None)
    non_appearance_info: str = field(8, default='')
    first_chapters: List[Chapter] = field(9, default_factory=list)
    last_chapters: List[Chapter] = field(10, default_factory=list)
    is_simul_related: bool = field(14, default=True)
    chapters_descending: bool = field(17, default=True)


@message
@dataclass
class TitlesAll:
    titles: List[Title] = field(1)


@message
@dataclass
class TitlesRanking:
    titles: List[Title] = field(1)


@message
@dataclass
class UpdatedTitle:
    title: Title = field(1, default=None)


@message
@dataclass
class UpdatedTitleGroup:
    group_name: str = field(1, default=None)
    titles: List[UpdatedTitle] = field(2, default_factory=list)


@message
@dataclass
class WebHomeView:
    update_title_groups: List[UpdatedTitleGroup] = field(2, default_factory=list)


@message
@dataclass
class SuccessResult:
    is_featured_updated: bool = field(1, default=False)
    titles_all: TitlesAll = field(5, default=None)
    titles_ranking: TitlesRanking = field(6, default=None)
    title_detail: TitleDetail = field(8, default=None)
    manga_viewer: MangaViewer = field(10, default=None)
    web_home_view: WebHomeView = field(11, default=None)


@message
@dataclass
class MangaplusResponse:
    success: SuccessResult = field(1, default=None)
    error: ErrorResult = field(2, default=None)
