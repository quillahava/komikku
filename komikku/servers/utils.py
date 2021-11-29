# Copyright (C) 2019-2021 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from bs4 import NavigableString
import dateparser
import datetime
from functools import lru_cache
from functools import wraps
import importlib
import inspect
from io import BytesIO
import logging
import magic
from operator import itemgetter
import os
from PIL import Image
from pkgutil import iter_modules
import struct
import sys

from komikku.servers.loader import server_finder

logger = logging.getLogger('komikku.servers')


def convert_date_string(date, format=None):
    if format is not None:
        try:
            d = datetime.datetime.strptime(date, format)
        except Exception:
            d = dateparser.parse(date)
    else:
        d = dateparser.parse(date)

    return d.date() if d else None


def convert_image(image, format='jpeg', ret_type='image'):
    """Convert an image to a specific format

    :param image: PIL.Image.Image or bytes object
    :param format: convertion format: jpeg, png, webp,...
    :param ret_type: image (PIL.Image.Image) or bytes (bytes object)
    """
    if not isinstance(image, Image.Image):
        image = Image.open(BytesIO(image))

    io_buffer = BytesIO()
    image.convert('RGB').save(io_buffer, format)
    if ret_type == 'bytes':
        return io_buffer.getbuffer()
    io_buffer.seek(0)
    return Image.open(io_buffer)


# https://github.com/italomaia/mangarock.py/blob/master/mangarock/mri_to_webp.py
def convert_mri_data_to_webp_buffer(data):
    size_list = [0] * 4
    size = len(data)
    header_size = size + 7

    # little endian byte representation
    # zeros to the right don't change the value
    for i, byte in enumerate(struct.pack('<I', header_size)):
        size_list[i] = byte

    buffer = [
        82,  # R
        73,  # I
        70,  # F
        70,  # F
        size_list[0],
        size_list[1],
        size_list[2],
        size_list[3],
        87,  # W
        69,  # E
        66,  # B
        80,  # P
        86,  # V
        80,  # P
        56,  # 8
    ]

    for bit in data:
        buffer.append(101 ^ bit)

    return bytes(buffer)


def do_login(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        server = args[0]
        if not server.logged_in:
            server.do_login()

        return func(*args, **kwargs)

    return wrapper


def get_allowed_servers_list(settings):
    servers_settings = settings.servers_settings
    servers_languages = settings.servers_languages

    servers = []
    for server_data in get_servers_list():
        if servers_languages and server_data['lang'] not in servers_languages:
            continue

        server_settings = servers_settings.get(get_server_main_id_by_id(server_data['id']))
        if server_settings is not None and (not server_settings['enabled'] or server_settings['langs'].get(server_data['lang']) is False):
            continue

        if settings.nsfw_content is False and server_data['is_nsfw']:
            continue

        servers.append(server_data)

    return servers


def get_buffer_mime_type(buffer):
    try:
        if hasattr(magic, 'detect_from_content'):
            # Using file-magic module: https://github.com/file/file
            return magic.detect_from_content(buffer[:128]).mime_type
        else:
            # Using python-magic module: https://github.com/ahupp/python-magic
            return magic.from_buffer(buffer[:128], mime=True)
    except Exception:
        return ''


def get_file_mime_type(path):
    try:
        if hasattr(magic, 'detect_from_filename'):
            # Using file-magic module: https://github.com/file/file
            return magic.detect_from_filename(path).mime_type
        else:
            # Using python-magic module: https://github.com/ahupp/python-magic
            return magic.from_file(path, mime=True)
    except Exception:
        return ''


def get_server_class_name_by_id(id):
    """Returns server class name

    id format is:

    name[_lang][_whatever][:module_name]

    - `name` is the name of the server.
    - `lang` is the language of the server (optional).
      Only useful when server belongs to a multi-languages server.
    - `whatever` is any string (optional).
      Only useful when a server must be backed up because it's dead.
      Beware, if `whatever` is defined, `lang` must be present even if it's empty.
      Example of value: old, bak, dead,...
    - `module_name` is the name of the module in which the server is defined (optional).
      Only useful if `module_name` is different from `name`.
    """
    return id.split(':')[0].capitalize()


def get_server_dir_name_by_id(id):
    name = id.split(':')[0]
    # Remove _whatever
    name = '_'.join(filter(None, name.split('_')[:2]))

    return name


def get_server_main_id_by_id(id):
    return id.split(':')[0].split('_')[0]


def get_server_module_name_by_id(id):
    return id.split(':')[-1].split('_')[0]


@lru_cache(maxsize=None)
def get_servers_list(include_disabled=False, order_by=('lang', 'name')):
    def iter_namespace(ns_pkg):
        # Specifying the second argument (prefix) to iter_modules makes the
        # returned name an absolute name instead of a relative one. This allows
        # import_module to work without having to do additional modification to
        # the name.
        return iter_modules(ns_pkg.__path__, ns_pkg.__name__ + '.')

    modules = []
    if server_finder in sys.meta_path:
        # Load servers from external folders defined in KOMIKKU_SERVERS_PATH environment variable
        for servers_path in server_finder.paths:
            if not os.path.exists(servers_path):
                continue

            count = 0
            for path, _dirs, _files in os.walk(servers_path):
                relpath = path[len(servers_path):]
                if not relpath:
                    continue

                relname = relpath.replace(os.path.sep, '.')
                if relname == '.multi':
                    continue

                modules.append(importlib.import_module(relname, package='komikku.servers'))
                count += 1

            logger.info('Load {0} servers from external folder: {1}'.format(count, servers_path))
    else:
        # fallback to local exploration
        import komikku.servers

        for _finder, name, _ispkg in iter_namespace(komikku.servers):
            modules.append(importlib.import_module(name))

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


def get_soup_element_inner_text(outer):
    return ''.join([el for el in outer if isinstance(el, NavigableString)]).strip()


# https://github.com/Harkame/JapScanDownloader
def unscramble_image(image):
    """Unscramble an image

    :param image: PIL.Image.Image or bytes object
    """
    if not isinstance(image, Image.Image):
        image = Image.open(BytesIO(image))

    temp = Image.new('RGB', image.size)
    output_image = Image.new('RGB', image.size)

    for x in range(0, image.width, 200):
        col1 = image.crop((x, 0, x + 100, image.height))

        if x + 200 <= image.width:
            col2 = image.crop((x + 100, 0, x + 200, image.height))
            temp.paste(col1, (x + 100, 0))
            temp.paste(col2, (x, 0))
        else:
            col2 = image.crop((x + 100, 0, image.width, image.height))
            temp.paste(col1, (x, 0))
            temp.paste(col2, (x + 100, 0))

    for y in range(0, temp.height, 200):
        row1 = temp.crop((0, y, temp.width, y + 100))

        if y + 200 <= temp.height:
            row2 = temp.crop((0, y + 100, temp.width, y + 200))
            output_image.paste(row1, (0, y + 100))
            output_image.paste(row2, (0, y))
        else:
            row2 = temp.crop((0, y + 100, temp.width, temp.height))
            output_image.paste(row1, (0, y))
            output_image.paste(row2, (0, y + 100))

    return output_image
