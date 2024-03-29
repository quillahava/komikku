# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import datetime
import logging
import os
import rarfile
import xml.etree.ElementTree as ET
import zipfile

from komikku.servers import Server
from komikku.servers.exceptions import ArchiveError
from komikku.servers.exceptions import ArchiveUnrarMissingError
from komikku.servers.exceptions import ServerException
from komikku.servers.utils import convert_image
from komikku.servers.utils import get_buffer_mime_type
from komikku.utils import get_data_dir

IMG_EXTENSIONS = ['bmp', 'gif', 'jpg', 'jpeg', 'png', 'tiff', 'webp']

logger = logging.getLogger('komikku.servers.local')


def is_archive(path):
    if zipfile.is_zipfile(path):
        return True
    if rarfile.is_rarfile(path):
        return True

    return False


class Archive:
    def __init__(self, path):
        try:
            if zipfile.is_zipfile(path):
                self.obj = CBZ(path)

            elif rarfile.is_rarfile(path):
                self.obj = CBR(path)
        except Exception as e:
            logger.exception(f'Bad/corrupt archive: {path}')
            raise ArchiveError from e

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.obj.archive.close()

    def get_info(self):
        # Parse ComicInfo.xml if exists
        data = dict(
            title=None,
            volume=None,
            authors=set(),
            translators=set(),
            genres=set(),
            synopsis=None,
            day=None,
            month=None,
            year=None,
        )
        info_xml = self.get_name_buffer('ComicInfo.xml')
        if not info_xml:
            return data

        tree = ET.ElementTree(ET.fromstring(info_xml))
        root = tree.getroot()

        for info in root.findall('./'):
            if not info.text:
                continue

            if info.tag in ('Series', 'Title', ):
                data['title'] = info.text
            elif info.tag == 'Volume':
                data['volume'] = info.text.strip()
            elif info.tag in ('Colorist', 'CoverArtist', 'Inker', 'Letterer', 'Penciller', 'Writer'):
                for author in info.text.split(','):
                    data['authors'].add(author.strip())
            elif info.tag == 'Translator':
                for translator in info.text.split(','):
                    data['translators'].add(translator.strip())
            elif info.tag == 'Genre':
                for genre in info.text.split(','):
                    data['genres'].add(genre.strip())
            elif info.tag == 'Manga' and info.text.strip() == 'Yes':
                data['genres'].add('Manga')
            elif info.tag == 'Summary':
                data['synopsis'] = info.text.strip()
            elif info.tag in ('Day', 'Month', 'Year'):
                data[info.tag.lower()] = int(info.text.strip())

        return data

    def get_namelist(self):
        names = []
        for name in self.obj.get_namelist():
            _root, ext = os.path.splitext(name)
            if ext[1:].lower() in IMG_EXTENSIONS:
                names.append(name)

        return sorted(names)

    def get_name_buffer(self, name):
        return self.obj.get_name_buffer(name)


class CBR:
    """Comic Book Rar (CBR) format"""

    def __init__(self, path):
        self.path = path
        self.archive = rarfile.RarFile(self.path)

    def get_namelist(self):
        return self.archive.namelist()

    def get_name_buffer(self, name):
        try:
            return self.archive.read(name)
        except rarfile.NoRarEntry as e:
            logger.info(f'{self.path}: {e}')
            return None
        except rarfile.RarCannotExec as e:
            logger.exception('Failed to execute unrar command')
            raise ArchiveUnrarMissingError from e
        except Exception as e:
            logger.info(f'{self.path}: {e}')
            raise ServerException(e) from e


class CBZ:
    """Comic Book Zip (CBZ) format

    Can also handle EPUB archives if images are well named (use of zero as a prefix to numbers to keep correct order)
    """

    def __init__(self, path):
        self.path = path
        self.archive = zipfile.ZipFile(self.path)

    def get_namelist(self):
        return self.archive.namelist()

    def get_name_buffer(self, name):
        try:
            return self.archive.read(name)
        except KeyError as e:
            logger.info(f'{self.path}: {e}')
            return None
        except Exception as e:
            logger.info(f'{self.path}: {e}')
            raise ServerException(e) from e


class Local(Server):
    id = 'local'
    name = 'Local'
    lang = ''

    def get_manga_cover_image(self, data, etag=None):
        if data is None:
            return None, None

        with Archive(data['path']) as archive:
            buffer = archive.get_name_buffer(data['name'])
        if buffer is None:
            return None, None

        mime_type = get_buffer_mime_type(buffer)
        if not mime_type.startswith('image'):
            return None, None

        if mime_type == 'image/webp':
            buffer = convert_image(buffer, ret_type='bytes')

        return buffer, None

    def get_manga_data(self, initial_data):
        data = initial_data.copy()
        data.update(dict(
            authors=[],
            scanlators=[],
            genres=[],
            status=None,
            chapters=[],
            synopsis=None,
            cover=None,
            server_id=self.id,
            url=None,
        ))

        dir_path = os.path.join(get_data_dir(), self.id, data['slug'])
        if not os.path.exists(dir_path):
            return None

        # Chapters
        for _path, _dirs, files in os.walk(dir_path):
            for file in sorted(files):
                path = os.path.join(dir_path, file)
                if not is_archive(os.path.join(dir_path, file)):
                    continue

                try:
                    with Archive(path) as archive:
                        names = archive.get_namelist()

                        # Used some chapters/volumes info to populate comic data
                        info = archive.get_info()
                        for genre in info['genres']:
                            if genre not in data['genres']:
                                data['genres'].append(genre)
                        for author in info['authors']:
                            if author not in data['authors']:
                                data['authors'].append(author)
                        for translator in info['translators']:
                            if translator not in data['scanlators']:
                                data['scanlators'].append(translator)
                        if not data['synopsis'] and info['synopsis']:
                            data['synopsis'] = info['synopsis']

                        # Cover is by default 1st page of 1st chapter/volume (archive)
                        if data['cover'] is None:
                            data['cover'] = dict(
                                path=path,
                                name=names[0],
                            )

                        title = info['title'] or os.path.splitext(file)[0]
                        if info['volume']:
                            title = f'{info["volume"]} - {title}'
                        date = datetime.date(info['year'], info['month'] or 1, info['day'] or 1) if info['year'] else None

                        chapter = dict(
                            slug=file,
                            title=title,
                            date=date,
                            scanlators=list(info['translators']),
                            downloaded=1,
                        )

                        data['chapters'].append(chapter)
                except Exception:
                    logger.exception(f'Failed to retrieve chapters of {data["name"]}')

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        path = os.path.join(get_data_dir(), self.id, manga_slug, chapter_slug)
        if not os.path.exists(path):
            return None

        with Archive(path) as archive:
            names = archive.get_namelist()

        data = dict(
            pages=[],
        )
        for name in names:
            data['pages'].append(dict(
                slug=name,
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        path = os.path.join(get_data_dir(), self.id, manga_slug, chapter_slug)
        if not os.path.exists(path):
            return None

        with Archive(path) as archive:
            content = archive.get_name_buffer(page['slug'])

        mime_type = get_buffer_mime_type(content)
        if not mime_type.startswith('image'):
            return None

        return dict(
            buffer=content,
            mime_type=mime_type,
            name=page['slug'],
        )

    def get_manga_url(self, slug, url):
        return None

    def get_latest_updates(self):
        """
        Returns list of latest updated manga
        """
        dir_path = os.path.join(get_data_dir(), self.id)

        result = {}
        for name in os.listdir(dir_path):
            manga_folder = os.path.join(dir_path, name)

            if not os.path.isdir(manga_folder):
                continue

            result[os.path.getmtime(manga_folder)] = dict(
                slug=name,
                name=name,
            )

        return [item for key, item in sorted(result.items(), reverse=True)][:100]

    def search(self, term):
        dir_path = os.path.join(get_data_dir(), self.id)

        result = []
        for name in sorted(os.listdir(dir_path)):
            if not os.path.isdir(os.path.join(dir_path, name)):
                continue

            if term and term.lower() not in name.lower():
                continue

            result.append(dict(
                slug=name,
                name=name,
            ))

        return result
