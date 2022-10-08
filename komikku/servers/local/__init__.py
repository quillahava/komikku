# -*- coding: utf-8 -*-

# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import os
import rarfile
import zipfile

from komikku.servers import Server
from komikku.servers.utils import convert_image
from komikku.servers.utils import get_buffer_mime_type
from komikku.utils import get_data_dir

IMG_EXTENSIONS = ['bmp', 'gif', 'jpg', 'jpeg', 'png', 'webp']


def is_archive(path):
    if zipfile.is_zipfile(path):
        return True
    elif rarfile.is_rarfile(path):
        return True

    return False


class Archive:
    def __init__(self, path):
        if zipfile.is_zipfile(path):
            self.obj = CBZ(path)

        elif rarfile.is_rarfile(path):
            self.obj = CBR(path)

    def get_namelist(self):
        names = []
        for name in self.obj.get_namelist():
            _root, ext = os.path.splitext(name)
            if ext[1:].lower() in IMG_EXTENSIONS:
                names.append(name)

        return names

    def get_name_buffer(self, name):
        return self.obj.get_name_buffer(name)


class CBR:
    def __init__(self, path):
        self.path = path

    def get_namelist(self):
        with rarfile.RarFile(self.path) as archive:
            return archive.namelist()

    def get_name_buffer(self, name):
        with rarfile.RarFile(self.path) as archive:
            try:
                return archive.read(name)
            except Exception:
                # `unrar` command line tool is missing
                return None


class CBZ:
    def __init__(self, path):
        self.path = path

    def get_namelist(self):
        with zipfile.ZipFile(self.path) as archive:
            return archive.namelist()

    def get_name_buffer(self, name):
        with zipfile.ZipFile(self.path) as archive:
            return archive.read(name)


class Local(Server):
    id = 'local'
    name = 'Local'
    lang = ''

    def get_manga_cover_image(self, data):
        if data is None:
            return None

        archive = Archive(data['path'])
        buffer = archive.get_name_buffer(data['name'])
        if buffer is None:
            return None

        mime_type = get_buffer_mime_type(buffer)
        if not mime_type.startswith('image'):
            return None

        if mime_type == 'image/webp':
            buffer = convert_image(buffer, ret_type='bytes')

        return buffer

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

                data['chapters'].append(dict(
                    slug=file,
                    title=os.path.splitext(file)[0],
                    date=None,
                    downloaded=1,
                ))

        # Cover is by default 1st page of 1st chapter (archive)
        if len(data['chapters']) > 0:
            path = os.path.join(dir_path, data['chapters'][0]['slug'])
            archive = Archive(path)
            data['cover'] = dict(
                path=path,
                name=archive.get_namelist()[0],
            )

        return data

    def get_manga_chapter_data(self, manga_slug, manga_name, chapter_slug, chapter_url):
        path = os.path.join(get_data_dir(), self.id, manga_slug, chapter_slug)
        if not os.path.exists(path):
            return None

        archive = Archive(path)

        data = dict(
            pages=[],
        )
        for name in archive.get_namelist():
            data['pages'].append(dict(
                slug=name,
                image=None,
            ))

        return data

    def get_manga_chapter_page_image(self, manga_slug, manga_name, chapter_slug, page):
        path = os.path.join(get_data_dir(), self.id, manga_slug, chapter_slug)
        if not os.path.exists(path):
            return None

        archive = Archive(path)
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

    def get_most_populars(self):
        return self.search('')

    def search(self, term):
        dir_path = os.path.join(get_data_dir(), self.id)

        result = []
        for name in os.listdir(dir_path):
            if not os.path.isdir(os.path.join(dir_path, name)):
                continue

            if term and term.lower() not in name.lower():
                continue

            result.append(dict(
                slug=name,
                name=name,
            ))

        return result
