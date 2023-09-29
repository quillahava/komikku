# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import datetime
from enum import IntEnum
from functools import cache
from gettext import gettext as _
import importlib
import json
import logging
import os
from PIL import Image
import sqlite3
import shutil

from gi.repository import Gio

from komikku.servers.utils import convert_image
from komikku.servers.utils import get_server_class_name_by_id
from komikku.servers.utils import get_server_dir_name_by_id
from komikku.servers.utils import get_server_module_name_by_id
from komikku.servers.utils import unscramble_image
from komikku.utils import get_cached_data_dir
from komikku.utils import get_data_dir
from komikku.utils import is_flatpak
from komikku.utils import trunc_filename

logger = logging.getLogger('komikku')

VERSION = 12


def adapt_json(data):
    return (json.dumps(data, sort_keys=True)).encode()


def convert_json(blob):
    return json.loads(blob.decode())


sqlite3.register_adapter(dict, adapt_json)
sqlite3.register_adapter(list, adapt_json)
sqlite3.register_adapter(tuple, adapt_json)
sqlite3.register_converter('json', convert_json)


def backup_db():
    db_path = get_db_path()
    if os.path.exists(db_path) and check_db():
        print('Save a DB backup')
        shutil.copyfile(db_path, get_db_backup_path())


def check_db():
    db_conn = create_db_connection()

    if db_conn:
        try:
            res = db_conn.execute('PRAGMA integrity_check').fetchone()  # PRAGMA quick_check

            fk_violations = len(db_conn.execute('PRAGMA foreign_key_check').fetchall())

            ret = res[0] == 'ok' and fk_violations == 0
        except sqlite3.DatabaseError:
            logger.exception('Failed to check DB')
            ret = False

        db_conn.close()

    return ret


def clear_cached_data(manga_in_use=None):
    # Clear chapters cache
    cache_dir_path = get_cached_data_dir()
    for server_name in os.listdir(cache_dir_path):
        server_dir_path = os.path.join(cache_dir_path, server_name)
        if manga_in_use and manga_in_use.path.startswith(server_dir_path):
            for manga_name in os.listdir(server_dir_path):
                manga_dir_path = os.path.join(server_dir_path, manga_name)
                if manga_dir_path != manga_in_use.path:
                    shutil.rmtree(manga_dir_path)
        else:
            shutil.rmtree(server_dir_path)

    # Clear database
    db_conn = create_db_connection()
    with db_conn:
        if manga_in_use:
            db_conn.execute('DELETE FROM mangas WHERE in_library != 1 AND id != ?', (manga_in_use.id, ))
        else:
            db_conn.execute('DELETE FROM mangas WHERE in_library != 1')

    db_conn.close()


def create_db_connection():
    con = sqlite3.connect(get_db_path(), detect_types=sqlite3.PARSE_DECLTYPES)
    if con is None:
        print("Error: Can not create the database connection.")
        return None

    con.row_factory = sqlite3.Row

    # Enable integrity constraint
    con.execute('PRAGMA foreign_keys = ON')

    return con


def execute_sql(conn, sql):
    try:
        c = conn.cursor()
        c.execute(sql)
        conn.commit()
        c.close()
    except Exception as e:
        print('SQLite-error:', e)
        return False
    else:
        return True


@cache
def get_db_path():
    app_profile = Gio.Application.get_default().profile

    if is_flatpak() and app_profile == 'beta':
        # In Flathub beta version share same data folder with stable version:
        # ~/.var/app/info.febvre.Komikku/data/
        # So, DB files must have distinct names
        name = 'komikku_beta.db'
    else:
        name = 'komikku.db'

    return os.path.join(get_data_dir(), name)


@cache
def get_db_backup_path():
    app_profile = Gio.Application.get_default().profile

    if is_flatpak() and app_profile == 'beta':
        name = 'komikku_beta_backup.db'
    else:
        name = 'komikku_backup.db'

    return os.path.join(get_data_dir(), name)


def init_db():
    db_path = get_db_path()
    db_backup_path = get_db_backup_path()
    if os.path.exists(db_path) and os.path.exists(db_backup_path) and not check_db():
        # Restore backup
        print('Restore DB from backup')
        shutil.copyfile(db_backup_path, db_path)

    sql_create_mangas_table = """CREATE TABLE IF NOT EXISTS mangas (
        id integer PRIMARY KEY,
        slug text NOT NULL,
        url text, -- only used in case slug can't be used to forge the url
        server_id text NOT NULL,
        in_library integer,
        name text NOT NULL,
        authors json,
        scanlators json,
        genres json,
        synopsis text,
        status text,
        background_color text,
        borders_crop integer,
        landscape_zoom integer,
        page_numbering integer,
        reading_mode text,
        scaling text,
        sort_order text,
        last_read timestamp,
        last_update timestamp,
        UNIQUE (slug, server_id)
    );"""

    sql_create_chapters_table = """CREATE TABLE IF NOT EXISTS chapters (
        id integer PRIMARY KEY,
        manga_id integer REFERENCES mangas(id) ON DELETE CASCADE,
        slug text NOT NULL,
        url text, -- only used in case slug can't be used to forge the url
        title text NOT NULL,
        scanlators json,
        pages json,
        scrambled integer,
        date date,
        rank integer NOT NULL,
        downloaded integer NOT NULL,
        recent integer NOT NULL,
        read_progress text,
        read integer NOT NULL,
        last_page_read_index integer,
        last_read timestamp,
        UNIQUE (slug, manga_id)
    );"""

    sql_create_downloads_table = """CREATE TABLE IF NOT EXISTS downloads (
        id integer PRIMARY KEY,
        chapter_id integer REFERENCES chapters(id) ON DELETE CASCADE,
        status text NOT NULL,
        percent float NOT NULL,
        errors integer DEFAULT 0,
        date timestamp NOT NULL,
        UNIQUE (chapter_id)
    );"""

    sql_create_categories_table = """CREATE TABLE IF NOT EXISTS categories (
        id integer PRIMARY KEY,
        label text NOT NULL,
        UNIQUE (label)
    );"""

    sql_create_categories_mangas_association_table = """CREATE TABLE IF NOT EXISTS categories_mangas_association (
        category_id integer REFERENCES categories(id) ON DELETE CASCADE,
        manga_id integer REFERENCES mangas(id) ON DELETE CASCADE,
        UNIQUE (category_id, manga_id)
    );"""

    sql_create_indexes = [
        'CREATE INDEX IF NOT EXISTS idx_chapters_downloaded on chapters(manga_id, downloaded);',
        'CREATE INDEX IF NOT EXISTS idx_chapters_recent on chapters(manga_id, recent);',
        'CREATE INDEX IF NOT EXISTS idx_chapters_read on chapters(manga_id, read);',
    ]

    db_conn = create_db_connection()
    if db_conn is not None:
        db_version = db_conn.execute('PRAGMA user_version').fetchone()[0]

        execute_sql(db_conn, sql_create_mangas_table)
        execute_sql(db_conn, sql_create_chapters_table)
        execute_sql(db_conn, sql_create_downloads_table)
        execute_sql(db_conn, sql_create_categories_table)
        execute_sql(db_conn, sql_create_categories_mangas_association_table)
        for sql_create_index in sql_create_indexes:
            execute_sql(db_conn, sql_create_index)

        if db_version == 0:
            # First launch
            db_conn.execute('PRAGMA user_version = {0}'.format(VERSION))

        if 0 < db_version <= 1:
            # Version 0.10.0
            if execute_sql(db_conn, 'ALTER TABLE downloads ADD COLUMN errors integer DEFAULT 0;'):
                db_conn.execute('PRAGMA user_version = {0}'.format(2))

        if 0 < db_version <= 2:
            # Version 0.12.0
            if execute_sql(db_conn, 'ALTER TABLE mangas ADD COLUMN borders_crop integer;'):
                db_conn.execute('PRAGMA user_version = {0}'.format(3))

        if 0 < db_version <= 4:
            # Version 0.16.0
            if execute_sql(db_conn, 'ALTER TABLE chapters ADD COLUMN scanlators json;'):
                db_conn.execute('PRAGMA user_version = {0}'.format(5))

        if 0 < db_version <= 5:
            # Version 0.22.0
            if execute_sql(db_conn, 'ALTER TABLE mangas RENAME COLUMN reading_direction TO reading_mode;'):
                db_conn.execute('PRAGMA user_version = {0}'.format(6))

        if 0 < db_version <= 6:
            # Version 0.25.0
            if execute_sql(db_conn, sql_create_categories_table) and execute_sql(db_conn, sql_create_categories_mangas_association_table):
                db_conn.execute('PRAGMA user_version = {0}'.format(7))

        if 0 < db_version <= 7:
            # Version 0.31.0
            ids_mapping = dict(
                jaiminisbox__old='jaiminisbox',
                kireicake='kireicake:jaiminisbox',
                lupiteam='lupiteam:jaiminisbox',
                tuttoanimemanga='tuttoanimemanga:jaiminisbox',

                readcomicsonline='readcomicsonline:hatigarmscans',

                hatigarmscans__old='hatigarmscans',

                edelgardescans='edelgardescans:genkan',
                hatigarmscans='hatigarmscans:genkan',
                hunlightscans='hunlightscans:genkan',
                leviatanscans__old='leviatanscans:genkan',
                leviatanscans_es_old='leviatanscans_es:genkan',
                oneshotscans__old='oneshotscans:genkan',
                reaperscans='reaperscans:genkan',
                thenonamesscans='thenonamesscans:genkan',
                zeroscans='zeroscans:genkan',

                akumanga='akumanga:madara',
                aloalivn='aloalivn:madara',
                apollcomics='apollcomics:madara',
                araznovel='araznovel:madara',
                argosscan='argosscan:madara',
                atikrost='atikrost:madara',
                romance24h='romance24h:madara',
                wakascan='wakascan:madara',
            )
            res = True
            for new, old in ids_mapping.items():
                res &= execute_sql(db_conn, f"UPDATE mangas SET server_id = '{new}' WHERE server_id = '{old}';")

            if res:
                db_conn.execute('PRAGMA user_version = {0}'.format(8))

        if 0 < db_version <= 8:
            # Version 0.32.0
            if execute_sql(db_conn, 'ALTER TABLE mangas ADD COLUMN page_numbering integer;'):
                db_conn.execute('PRAGMA user_version = {0}'.format(9))

        if 0 < db_version <= 9:
            # Version 0.35.0
            execute_sql(db_conn, "UPDATE mangas SET server_id = 'reaperscans__old' WHERE server_id = 'reaperscans';")

            if execute_sql(db_conn, 'ALTER TABLE chapters ADD COLUMN last_read timestamp;'):
                db_conn.execute('PRAGMA user_version = {0}'.format(10))

        if 0 < db_version <= 10:
            # Version 1.0.0
            execute_sql(db_conn, 'ALTER TABLE mangas ADD COLUMN landscape_zoom integer;')
            execute_sql(db_conn, 'ALTER TABLE chapters ADD COLUMN read_progress text;')

            # Chapters: move reading status of pages in a new 'read_progress' field
            ids = []
            data = []
            manga_rows = db_conn.execute('SELECT id FROM mangas').fetchall()
            with db_conn:
                for manga_row in manga_rows:
                    chapter_rows = db_conn.execute('SELECT * FROM chapters WHERE manga_id = ?', (manga_row['id'],)).fetchall()
                    for chapter_row in chapter_rows:
                        if not chapter_row['pages']:
                            continue

                        read_progress = ''
                        for page in chapter_row['pages']:
                            read = page.pop('read', False)
                            read_progress += str(int(read))
                        if '1' in read_progress and '0' in read_progress:
                            ids.append(chapter_row['id'])
                            data.append({'pages': chapter_row['pages'], 'read_progress': read_progress})

                if ids:
                    update_rows(db_conn, 'chapters', ids, data)

                db_conn.execute('PRAGMA user_version = {0}'.format(11))

        if 0 < db_version <= 11:
            # Version 1.16.0
            execute_sql(db_conn, 'ALTER TABLE mangas ADD COLUMN in_library integer;')
            execute_sql(db_conn, 'UPDATE mangas SET in_library = 1;')
            db_conn.execute('PRAGMA user_version = {0}'.format(12))

        print('DB version', db_conn.execute('PRAGMA user_version').fetchone()[0])

        db_conn.close()


def delete_rows(db_conn, table, ids):
    seq = []
    if type(ids[0]) is dict:
        # Several keys (secondary) are used to delete a row
        sql = 'DELETE FROM {0} WHERE {1}'.format(table, ' AND '.join(f'{skey} = ?' for skey in ids[0].keys()))

        for item in ids:
            seq.append(tuple(item.values()))
    else:
        sql = 'DELETE FROM {0} WHERE id = ?'.format(table)

        for id_ in ids:
            seq.append((id_, ))

    try:
        db_conn.executemany(sql, seq)
    except Exception as e:
        print('SQLite-error:', e, ids)
        return False
    else:
        return True


def insert_row(db_conn, table, data):
    try:
        cursor = db_conn.execute(
            'INSERT INTO {0} ({1}) VALUES ({2})'.format(table, ', '.join(data.keys()), ', '.join(['?'] * len(data))),
            tuple(data.values())
        )
    except Exception as e:
        print('SQLite-error:', e, data)
        return None
    else:
        return cursor.lastrowid


def insert_rows(db_conn, table, data):
    sql = 'INSERT INTO {0} ({1}) VALUES ({2})'.format(table, ', '.join(data[0].keys()), ', '.join(['?'] * len(data[0])))

    seq = []
    for item in data:
        seq.append(tuple(item.values()))

    try:
        db_conn.executemany(sql, seq)
    except Exception as e:
        print('SQLite-error:', e, data)
        return False
    else:
        return True


def update_row(db_conn, table, id_, data):
    try:
        db_conn.execute(
            'UPDATE {0} SET {1} WHERE id = ?'.format(table, ', '.join(k + ' = ?' for k in data)),
            tuple(data.values()) + (id_,)
        )
    except Exception as e:
        print('SQLite-error:', e, data)
        return False
    else:
        return True


def update_rows(db_conn, table, ids, data):
    sql = 'UPDATE {0} SET {1} WHERE id = ?'.format(table, ', '.join(k + ' = ?' for k in data[0]))

    seq = []
    for index, id_ in enumerate(ids):
        seq.append(tuple(data[index].values()) + (id_, ))

    try:
        db_conn.executemany(sql, seq)
    except Exception as e:
        print('SQLite-error:', e, data)
        return False
    else:
        return True


class Manga:
    _chapters = None
    _server = None

    STATUSES = dict(
        complete=_('Complete'),
        ongoing=_('Ongoing'),
        suspended=_('Suspended'),
        hiatus=_('Hiatus'),
    )

    def __init__(self, server=None):
        if server:
            self._server = server

    @classmethod
    def get(cls, id_, server=None, db_conn=None):
        if db_conn is not None:
            row = db_conn.execute('SELECT * FROM mangas WHERE id = ?', (id_,)).fetchone()
        else:
            db_conn = create_db_connection()
            row = db_conn.execute('SELECT * FROM mangas WHERE id = ?', (id_,)).fetchone()
            db_conn.close()

        if row is None:
            return None

        manga = cls(server=server)
        for key in row.keys():
            setattr(manga, key, row[key])

        return manga

    @classmethod
    def new(cls, data, server, long_strip_detection):
        data = data.copy()
        chapters = data.pop('chapters')
        cover_url = data.pop('cover')

        # Fill data with internal data
        data.update(dict(
            in_library=0,
            # Add fake last_read date: allows to display recently added manga at the top of the library
            last_read=datetime.datetime.utcnow(),
        ))

        # Long strip detection (Webtoon)
        if long_strip_detection and server.is_long_strip(data):
            data.update(dict(
                reading_mode='webtoon',
                scaling='width',
            ))

        db_conn = create_db_connection()
        with db_conn:
            id_ = insert_row(db_conn, 'mangas', data)

            rank = 0
            for chapter_data in chapters:
                if not chapter_data.get('date'):
                    # Used today if not date is provided
                    chapter_data['date'] = datetime.date.today()

                chapter = Chapter.new(chapter_data, rank, id_, db_conn)
                if chapter is not None:
                    rank += 1

        db_conn.close()

        manga = cls.get(id_, server)

        if not os.path.exists(manga.path):
            os.makedirs(manga.path)

        manga._save_cover(cover_url)

        return manga

    @property
    def categories(self):
        db_conn = create_db_connection()
        rows = db_conn.execute(
            'SELECT c.id FROM categories c JOIN categories_mangas_association cma ON cma.category_id = c.id WHERE cma.manga_id = ?',
            (self.id,)
        )

        categories = []
        for row in rows:
            categories.append(row['id'])

        db_conn.close()

        return categories

    @property
    def chapters(self):
        if self._chapters is None:
            db_conn = create_db_connection()
            if self.sort_order and self.sort_order.endswith('asc'):
                rows = db_conn.execute('SELECT * FROM chapters WHERE manga_id = ? ORDER BY rank ASC', (self.id,))
            else:
                rows = db_conn.execute('SELECT * FROM chapters WHERE manga_id = ? ORDER BY rank DESC', (self.id,))

            self._chapters = []
            for row in rows:
                self._chapters.append(Chapter(row=row, manga=self))

            db_conn.close()

        return self._chapters

    @property
    def class_name(self):
        return get_server_class_name_by_id(self.server_id)

    @property
    def cover_fs_path(self):
        path = os.path.join(self.path, 'cover.jpg')
        if os.path.exists(path):
            return path

        return None

    @property
    def dir_name(self):
        return get_server_dir_name_by_id(self.server_id)

    @property
    def module_name(self):
        return get_server_module_name_by_id(self.server_id)

    @property
    def nb_downloaded_chapters(self):
        db_conn = create_db_connection()
        row = db_conn.execute(
            'SELECT count() AS downloaded FROM chapters WHERE manga_id = ? AND downloaded = 1 and read = 0', (self.id,)).fetchone()
        db_conn.close()

        return row['downloaded']

    @property
    def nb_recent_chapters(self):
        db_conn = create_db_connection()
        row = db_conn.execute('SELECT count() AS recents FROM chapters WHERE manga_id = ? AND recent = 1', (self.id,)).fetchone()
        db_conn.close()

        return row['recents']

    @property
    def nb_unread_chapters(self):
        db_conn = create_db_connection()
        row = db_conn.execute('SELECT count() AS unread FROM chapters WHERE manga_id = ? AND read = 0', (self.id,)).fetchone()
        db_conn.close()

        return row['unread']

    @property
    def path(self):
        if self.in_library:
            return os.path.join(get_data_dir(), self.dir_name, trunc_filename(self.name))

        return os.path.join(get_cached_data_dir(), self.dir_name, trunc_filename(self.name))

    @property
    def server(self):
        if self._server is None:
            module = importlib.import_module('.' + self.module_name, package='komikku.servers')
            self._server = getattr(module, self.class_name)()

        return self._server

    def _save_cover(self, url):
        if url is None:
            return

        # If cover has already been retrieved
        # Check first if it has changed using ETag
        current_etag = None
        cover_etag_fs_path = os.path.join(self.path, 'cover.etag')
        if os.path.exists(cover_etag_fs_path):
            with open(cover_etag_fs_path, 'r') as fp:
                current_etag = fp.read()

        # Save cover image file
        cover_data, etag = self.server.get_manga_cover_image(url, current_etag)
        if cover_data is None:
            return

        cover_fs_path = os.path.join(self.path, 'cover.jpg')
        with open(cover_fs_path, 'wb') as fp:
            fp.write(cover_data)

        if etag:
            with open(cover_etag_fs_path, 'w') as fp:
                fp.write(etag)
        elif os.path.exists(cover_etag_fs_path):
            os.remove(cover_etag_fs_path)

    def add_in_library(self):
        old_path = self.path
        self.update(dict(in_library=True))
        shutil.move(old_path, self.path)

    def delete(self):
        db_conn = create_db_connection()

        with db_conn:
            db_conn.execute('DELETE FROM mangas WHERE id = ?', (self.id, ))

        db_conn.close()

        # Delete folder except when server is 'local'
        if os.path.exists(self.path) and self.server_id != 'local':
            shutil.rmtree(self.path)

    def get_next_chapter(self, chapter, direction=1):
        """
        :param chapter: reference chapter
        :param direction: -1 for preceding chapter, 1 for following chapter
        """
        assert direction in (-1, 1), 'Invalid direction value'

        db_conn = create_db_connection()
        if direction == 1:
            row = db_conn.execute(
                'SELECT * FROM chapters WHERE manga_id = ? AND rank > ? ORDER BY rank ASC', (self.id, chapter.rank)).fetchone()
        else:
            row = db_conn.execute(
                'SELECT * FROM chapters WHERE manga_id = ? AND rank < ? ORDER BY rank DESC', (self.id, chapter.rank)).fetchone()
        db_conn.close()

        if not row:
            return None

        return Chapter(row=row, manga=self)

    def toggle_category(self, category_id, active):
        db_conn = create_db_connection()
        with db_conn:
            if active:
                insert_row(db_conn, 'categories_mangas_association', dict(category_id=category_id, manga_id=self.id))
            else:
                db_conn.execute(
                    'DELETE FROM categories_mangas_association WHERE category_id = ? AND manga_id = ?',
                    (category_id, self.id,)
                )

        db_conn.close()

    def update(self, data):
        """
        Updates specific fields

        :param dict data: fields to update
        :return: True on success False otherwise
        """
        ret = False

        # Update
        for key in data:
            setattr(self, key, data[key])

        db_conn = create_db_connection()
        with db_conn:
            ret = update_row(db_conn, 'mangas', self.id, data)

        db_conn.close()

        return ret

    def update_full(self):
        """
        Updates manga

        :return: True on success False otherwise, recent chapters IDs, number of deleted chapters
        :rtype: tuple
        """
        gone_chapters_ranks = []
        recent_chapters_ids = []
        nb_deleted_chapters = 0

        def get_free_rank(rank):
            if rank not in gone_chapters_ranks:
                return rank

            return get_free_rank(rank + 1)

        data = self.server.get_manga_data(dict(slug=self.slug, url=self.url, last_read=self.last_read))
        if data is None:
            return False, 0, 0, False

        synced = self.server.sync and data['last_read'] != self.last_read

        db_conn = create_db_connection()
        with db_conn:
            # Re-create the manga directory if it does not exist.
            if not os.path.exists(self.path):
                os.makedirs(self.path)

            # Update cover
            cover = data.pop('cover')
            if cover:
                self._save_cover(cover)

            # Update chapters
            chapters_data = data.pop('chapters')

            # First, delete chapters that no longer exist on server EXCEPT those marked as downloaded
            # In case of downloaded, we keep track of ranks because they must not be reused
            chapters_slugs = [chapter_data['slug'] for chapter_data in chapters_data]
            rows = db_conn.execute('SELECT * FROM chapters WHERE manga_id = ?', (self.id,))
            for row in rows:
                if row['slug'] not in chapters_slugs:
                    gone_chapter = Chapter.get(row['id'], manga=self, db_conn=db_conn)
                    if not gone_chapter.downloaded:
                        # Delete chapter
                        gone_chapter.delete(db_conn)
                        nb_deleted_chapters += 1

                        logger.warning(
                            '[UPDATE] {0} ({1}): Delete chapter {2} (no longer available)'.format(
                                self.name, self.server_id, gone_chapter.title
                            )
                        )
                    else:
                        # Keep track of rank freed
                        gone_chapters_ranks.append(gone_chapter.rank)

            # Then, add or update chapters
            rank = 0
            for chapter_data in chapters_data:
                row = db_conn.execute(
                    'SELECT * FROM chapters WHERE manga_id = ? AND slug = ?', (self.id, chapter_data['slug'])
                ).fetchone()

                rank = get_free_rank(rank)
                if row:
                    # Update changes
                    changes = {}
                    if row['title'] != chapter_data['title']:
                        changes['title'] = chapter_data['title']
                    if row['url'] != chapter_data.get('url'):
                        changes['url'] = chapter_data['url']
                    if chapter_data.get('date') and row['date'] != chapter_data['date']:
                        changes['date'] = chapter_data['date']
                    if row['scanlators'] != chapter_data.get('scanlators'):
                        changes['scanlators'] = chapter_data['scanlators']
                    if row['rank'] != rank:
                        changes['rank'] = rank
                    if changes:
                        update_row(db_conn, 'chapters', row['id'], changes)
                    rank += 1
                else:
                    # Add new chapter
                    if not chapter_data.get('date'):
                        # Used today if not date is provided
                        chapter_data['date'] = datetime.date.today()

                    chapter_data.update(dict(
                        manga_id=self.id,
                        rank=rank,
                        downloaded=chapter_data.get('downloaded', 0),
                        recent=1,
                        read=0,
                    ))
                    id_ = insert_row(db_conn, 'chapters', chapter_data)
                    if id_ is not None:
                        recent_chapters_ids.append(id_)
                        rank += 1

                        logger.info('[UPDATE] {0} ({1}): Add new chapter {2}'.format(self.name, self.server_id, chapter_data['title']))

            if len(recent_chapters_ids) > 0 or nb_deleted_chapters > 0:
                data['last_update'] = datetime.datetime.utcnow()

            self._chapters = None

            # Store old path
            old_path = self.path

            # Update
            for key in data:
                setattr(self, key, data[key])

            update_row(db_conn, 'mangas', self.id, data)

            if old_path != self.path:
                # Manga name changes, manga folder must be renamed too
                os.rename(old_path, self.path)

        db_conn.close()

        return True, recent_chapters_ids, nb_deleted_chapters, synced


class Chapter:
    _manga = None

    def __init__(self, row=None, manga=None):
        if row is not None:
            if manga:
                self._manga = manga
            for key in row.keys():
                setattr(self, key, row[key])

    @classmethod
    def get(cls, id_, manga=None, db_conn=None):
        if db_conn is not None:
            row = db_conn.execute('SELECT * FROM chapters WHERE id = ?', (id_,)).fetchone()
        else:
            db_conn = create_db_connection()
            row = db_conn.execute('SELECT * FROM chapters WHERE id = ?', (id_,)).fetchone()
            db_conn.close()

        if row is None:
            return None

        return cls(row, manga)

    @classmethod
    def new(cls, data, rank, manga_id, db_conn=None):
        # Fill data with internal data
        data = data.copy()
        data.update(dict(
            manga_id=manga_id,
            rank=rank,
            downloaded=data.get('downloaded', 0),
            recent=0,
            read=0,
        ))

        if db_conn is not None:
            id_ = insert_row(db_conn, 'chapters', data)
        else:
            db_conn = create_db_connection()

            with db_conn:
                id_ = insert_row(db_conn, 'chapters', data)

        chapter = cls.get(id_, db_conn=db_conn) if id_ is not None else None

        return chapter

    @property
    def manga(self):
        if self._manga is None:
            self._manga = Manga.get(self.manga_id)

        return self._manga

    @property
    def path(self):
        # BEWARE: self.slug may contain '/' characters
        # os.makedirs() must be used to create chapter's folder
        name = '/'.join([trunc_filename(part) for part in self.slug.split('/')])

        return os.path.join(self.manga.path, name)

    def clear(self, reset=False):
        # Delete folder except when server is 'local'
        if os.path.exists(self.path) and self.manga.server_id != 'local':
            shutil.rmtree(self.path)

        data = dict(
            pages=None,
            downloaded=0,
        )
        if reset:
            data.update(dict(
                read_progress=None,
                read=0,
                last_read=None,
                last_page_read_index=None,
            ))
        self.update(data)

    @staticmethod
    def clear_many(chapters, reset=False):
        # Assume the chapters belong to the same manga
        manga = chapters[0].manga
        ids = []
        data = []

        for chapter in chapters:
            # Delete folder except when server is 'local'
            if os.path.exists(chapter.path) and manga.server_id != 'local':
                shutil.rmtree(chapter.path)

            ids.append(chapter.id)

            updated_data = dict(
                pages=None,
                downloaded=0,
            )
            if reset:
                updated_data.update(dict(
                    read_progress=None,
                    read=0,
                    last_read=None,
                    last_page_read_index=None,
                ))
            data.append(updated_data)

        db_conn = create_db_connection()
        with db_conn:
            update_rows(db_conn, 'chapters', ids, data)

        db_conn.close()

    def delete(self, db_conn=None):
        if db_conn is not None:
            db_conn.execute('DELETE FROM chapters WHERE id = ?', (self.id, ))
        else:
            db_conn = create_db_connection()

            with db_conn:
                db_conn.execute('DELETE FROM chapters WHERE id = ?', (self.id, ))

            db_conn.close()

        if os.path.exists(self.path):
            shutil.rmtree(self.path)

    def get_page(self, index):
        page_path = self.get_page_path(index)
        if page_path:
            return page_path

        page = self.pages[index]

        data = self.manga.server.get_manga_chapter_page_image(self.manga.slug, self.manga.name, self.slug, page)
        if data is None:
            return None

        if not os.path.exists(self.path):
            os.makedirs(self.path, exist_ok=True)

        image = data['buffer']

        if data['mime_type'] == 'image/webp' or self.scrambled:
            if data['mime_type'] == 'image/webp':
                data['name'] = os.path.splitext(data['name'])[0] + '.jpg'
                image = convert_image(image, 'jpeg')

            if self.scrambled:
                image = unscramble_image(image)

        page_path = os.path.join(self.path, data['name'])

        if isinstance(image, Image.Image):
            image.save(page_path)
        else:
            with open(page_path, 'wb') as fp:
                fp.write(image)

        updated_data = {}

        # If page name can't be retrieved from `image` or `slug`, we store its name
        retrievable = False
        if page.get('image') and data['name'] == page['image'].split('?')[0].split('/')[-1]:
            retrievable = True
        elif page.get('slug') and data['name'] == page['slug'].split('/')[-1]:
            retrievable = True
        if not retrievable:
            self.pages[index]['name'] = data['name']
            updated_data['pages'] = self.pages

        downloaded = len(next(os.walk(self.path))[2]) == len(self.pages)
        if downloaded != self.downloaded:
            updated_data['downloaded'] = downloaded

        if updated_data:
            self.update(updated_data)

        return page_path

    def get_page_data(self, index):
        """
        Return page image data: buffer, mime type, name

        Useful for locally stored manga. Image data (bytes) are retrieved directly from archive.
        """
        return self.manga.server.get_manga_chapter_page_image(self.manga.slug, self.manga.name, self.slug, self.pages[index])

    def get_page_path(self, index):
        if not self.pages:
            return None

        page = self.pages[index]

        if page.get('name'):
            name = page['name']

        elif page.get('image'):
            # Extract filename
            name = page['image'].split('/')[-1]
            # Remove query string
            name = name.split('?')[0]

        elif page.get('slug'):
            # Extract filename
            name = page['slug'].split('/')[-1]

        else:
            return None

        path = os.path.join(self.path, name)

        return path if os.path.exists(path) else None

    def update(self, data):
        """
        Updates specific fields

        :param dict data: fields to update
        :return: True on success False otherwise
        """
        ret = False

        for key in data:
            setattr(self, key, data[key])

        db_conn = create_db_connection()
        with db_conn:
            ret = update_row(db_conn, 'chapters', self.id, data)

        db_conn.close()

        return ret

    def update_full(self):
        """
        Updates chapter

        Fetches server and saves chapter data

        :return: True on success False otherwise
        """
        if self.pages:
            return True

        data = self.manga.server.get_manga_chapter_data(self.manga.slug, self.manga.name, self.slug, self.url)
        if data is None or not data['pages']:
            return False

        return self.update(data)


class Category:
    def __init__(self, row=None):
        if row is not None:
            for key in row.keys():
                setattr(self, key, row[key])

    @classmethod
    def get(cls, id_, db_conn=None):
        if db_conn is not None:
            row = db_conn.execute('SELECT * FROM categories WHERE id = ?', (id_,)).fetchone()
        else:
            db_conn = create_db_connection()
            row = db_conn.execute('SELECT * FROM categories WHERE id = ?', (id_,)).fetchone()
            db_conn.close()

        if row is None:
            return None

        return cls(row)

    @classmethod
    def new(cls, label, db_conn=None):
        data = dict(
            label=label,
        )

        if db_conn is not None:
            id_ = insert_row(db_conn, 'categories', data)
        else:
            db_conn = create_db_connection()

            with db_conn:
                id_ = insert_row(db_conn, 'categories', data)

        category = cls.get(id_, db_conn=db_conn) if id_ is not None else None

        db_conn.close()

        return category

    @property
    def mangas(self):
        db_conn = create_db_connection()
        rows = db_conn.execute('SELECT manga_id FROM categories_mangas_association WHERE category_id = ?', (self.id,)).fetchall()
        db_conn.close()

        return [row['manga_id'] for row in rows] if rows else []

    def delete(self):
        db_conn = create_db_connection()

        with db_conn:
            db_conn.execute('DELETE FROM categories WHERE id = ?', (self.id, ))

        db_conn.close()

    def update(self, data):
        """
        Updates specific fields

        :param dict data: fields to update
        :return: True on success False otherwise
        """
        ret = False

        for key in data:
            setattr(self, key, data[key])

        db_conn = create_db_connection()
        with db_conn:
            ret = update_row(db_conn, 'categories', self.id, data)

        db_conn.close()

        return ret


class CategoryVirtual(IntEnum):
    ALL = 0
    UNCATEGORIZED = -1


class Download:
    _chapter = None

    STATUSES = dict(
        pending=_('Download pending'),
        downloaded=_('Downloaded'),
        downloading=_('Downloading'),
        error=_('Download error'),
    )

    @classmethod
    def get(cls, id_):
        db_conn = create_db_connection()
        row = db_conn.execute('SELECT * FROM downloads WHERE id = ?', (id_,)).fetchone()
        db_conn.close()

        if row is None:
            return None

        d = cls()
        for key in row.keys():
            setattr(d, key, row[key])

        return d

    @classmethod
    def get_by_chapter_id(cls, chapter_id):
        db_conn = create_db_connection()
        row = db_conn.execute('SELECT * FROM downloads WHERE chapter_id = ?', (chapter_id,)).fetchone()
        db_conn.close()

        if row:
            d = cls()

            for key in row.keys():
                setattr(d, key, row[key])

            return d

        return None

    @classmethod
    def next(cls, exclude_errors=False):
        db_conn = create_db_connection()
        if exclude_errors:
            row = db_conn.execute('SELECT * FROM downloads WHERE status = "pending" ORDER BY date ASC').fetchone()
        else:
            row = db_conn.execute('SELECT * FROM downloads ORDER BY date ASC').fetchone()
        db_conn.close()

        if row:
            c = cls()

            for key in row.keys():
                setattr(c, key, row[key])

            return c

        return None

    @property
    def chapter(self):
        if self._chapter is None:
            self._chapter = Chapter.get(self.chapter_id)

        return self._chapter

    def delete(self):
        db_conn = create_db_connection()

        with db_conn:
            db_conn.execute('DELETE FROM downloads WHERE id = ?', (self.id, ))

        db_conn.close()

    def update(self, data):
        """
        Updates download

        :param data: percent of pages downloaded, errors or status
        :return: True on success False otherwise
        """

        db_conn = create_db_connection()
        result = False

        with db_conn:
            if update_row(db_conn, 'downloads', self.id, data):
                result = True
                for key in data:
                    setattr(self, key, data[key])

        db_conn.close()

        return result
