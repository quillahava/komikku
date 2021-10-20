# -*- coding: utf-8 -*-

# Copyright (C) 2021 Liliana Prikler
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Liliana Prikler <liliana.prikler@gmail.com>

import importlib.abc
import importlib.machinery
import os
import sys
import types


class ServerFinder(importlib.abc.MetaPathFinder):
    _PREFIX = 'komikku.servers.'

    def __init__(self, path=None):
        if isinstance(path, str):
            self.paths = [os.path.abspath(p) for p in path.split(os.pathsep)]
        else:
            self.paths = []

    def find_spec(self, fullname, path, target=None):
        """Attempt to locate the requested module

        fullname is the fully-qualified name of the module,
        path is set to parent package __path__ for sub-modules/packages or None otherwise,
        target can be a module object but is unused here.
        """
        if not fullname.startswith(self._PREFIX):
            return None

        name = fullname[len(self._PREFIX):]
        base_dir = name.replace('.', '/')
        for path in self.paths:
            candidate_path = os.path.join(path, base_dir, '__init__.py')
            if os.path.exists(candidate_path):
                return importlib.machinery.ModuleSpec(
                    fullname,
                    ServerLoader(fullname, candidate_path),
                    origin=candidate_path,
                )

        return None

    def install(self):
        if self.paths and self not in sys.meta_path:
            sys.meta_path.append(self)


class ServerLoader(importlib.machinery.SourceFileLoader):
    def create_module(self, spec):
        """Create the given module from the supplied module spec

        Compare and contrast _new_module in importlib._bootstrap
        We set the file name early, because we only load real files anyway,
        see ServerFinder.find_spec, and because it helps locating
        relative files, such as logos.
        """
        module = types.ModuleType(spec.name)

        module.__file__ = spec.origin
        if not self.get_source(spec.name):
            module.__path__ = [os.path.dirname(spec.origin)]

        return module


server_finder = ServerFinder(os.environ.get('KOMIKKU_SERVERS_PATH'))
