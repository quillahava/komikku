# -*- coding: utf-8 -*-

# Copyright (C) 2020 Liliana Prikler
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Liliana Prikler <liliana.prikler@gmail.com>

from .utils import get_server_main_id_by_id, get_server_class_name_by_id

from collections import Iterable

from functools import lru_cache

from importlib import import_module
from importlib.abc import MetaPathFinder
from importlib.machinery import SourceFileLoader

import inspect
import logging

from operator import itemgetter

from os import environ, sep, pathsep
import os.path

from pkgutil import iter_modules

from sys import meta_path


logger = logging.getLogger('komikku.servers')


class KomikkuServerFinder(MetaPathFinder):

    def __init__(self, path=None):
        self._prefix = 'komikku.servers.'
        if isinstance(path, str):
            self._servers_path = [os.path.abspath(p) for p in path.split(pathsep)]
        else:
            self._servers_path = path

    def find_spec(self, fullname, path, target=None):
        if fullname.startswith(self._prefix):
            shortname = fullname[len(self._prefix):]
            filename_base = shortname.replace('.', '/')
            for servers_path in self._servers_path:
                candidate1 = os.path.join(servers_path, filename_base) + '.py'
                candidate2 = os.path.join(servers_path, filename_base, '__init__.py')
                if os.path.exists(candidate1):
                    return self._module_spec(fullname, candidate1)
                if os.path.exists(candidate2):
                    return self._module_spec(fullname, candidate2)

    def _module_spec(self, fullname, filename):
        return importlib.machinery.ModuleSpec(
            fullname,
            KomikkuServerLoader(fullname, filename),
            origin=filename,
        )

    def install(self):
        global meta_path
        if self._servers_path and not self in meta_path:
            meta_path.append(self)


class KomikkuServerLoader(SourceFileLoader):

    def create_module(self, spec):
        # Compare and contrast _new_module in importlib._bootstrap
        # We set the file name early, because we only load real files anyway,
        # see KomikkuServerFinder.find_spec, and because it helps locating
        # relative files, such as logos.
        module = type(importlib)(spec.name)
        module.__file__ = spec.origin
        return module


server_finder = KomikkuServerFinder(environ.get('KOMIKKU_SERVERS_PATH'))


@lru_cache(maxsize=None)
def get_servers_list(include_disabled=False, order_by=('lang', 'name')):
    global server_finder

    def iter_namespace(ns_pkg):
        # Specifying the second argument (prefix) to iter_modules makes the
        # returned name an absolute name instead of a relative one. This allows
        # import_module to work without having to do additional modification to
        # the name.
        return iter_modules(ns_pkg.__path__, ns_pkg.__name__ + '.')

    modules = []
    if server_finder in meta_path:
        # Load servers from external folders defined in KOMIKKU_SERVERS_PATH environment variable
        for servers_path in server_finder._servers_path:
            if not os.path.exists(servers_path):
                continue

            count = 0
            for path, _dirs, _files in os.walk(servers_path):
                relpath = path[len(servers_path):]
                if not relpath:
                    continue

                relname = relpath.replace(sep, '.')
                if relname == '.multi':
                    continue

                modules.append(import_module(relname, package='komikku.servers'))
                count += 1

            logger.info('Load {0} servers from external folder: {1}'.format(count, servers_path))
    else:
        # fallback to local exploration
        import komikku.servers

        for _finder, name, _ispkg in iter_namespace(komikku.servers):
            modules.append(import_module(name))

    servers = []
    for module in modules:
        for _name, obj in dict(inspect.getmembers(module)).items():
            if not hasattr(obj, 'id') or not hasattr(obj, 'name') or not hasattr(obj, 'lang'):
                continue
            if NotImplemented in (obj.id, obj.name, obj.lang):
                continue

            if not include_disabled and obj.status == 'disabled':
                continue

            if inspect.isclass(obj):
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
