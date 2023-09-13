# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from contextlib import closing
import json
import keyring
from keyring.credentials import Credential
import logging
import os

from komikku.utils import get_data_dir

keyring.core.init_backend()

logger = logging.getLogger('komikku')


class CustomCredential(Credential):
    """Custom credentials implementation with an additional 'address' attribute"""

    def __init__(self, username, password, address=None):
        self._username = username
        self._password = password
        self._address = address

    @property
    def address(self):
        return self._address

    @property
    def password(self):
        return self._password

    @property
    def username(self):
        return self._username


class KeyringHelper:
    """Simple helper to store servers accounts credentials using Python keyring library"""

    appid = 'info.febvre.Komikku'

    def __init__(self, fallback_keyring='plaintext'):
        if self.is_disabled or not self.has_recommended_backend:
            if fallback_keyring == 'plaintext':
                keyring.set_keyring(PlaintextKeyring())

    @property
    def has_recommended_backend(self):
        """ Returns True if at least one supported backend is available, False otherwise """

        # At this time, SecretService is the only backend that support a collection of items with arbitrary attributes
        # Known working implementations are:
        # - GNOME Keyring
        # - KeePassXC Secret Service integration (tested, work well)

        # Freedesktop.org Secret Service specification was written by both GNOME and KDE projects together
        # but it’s supported by the GNOME Keyring only
        # ksecretservice (https://community.kde.org/KDE_Utils/ksecretsservice) exists but is unfinished and seems unmaintained
        current_keyring = keyring.get_keyring()
        return current_keyring is not None and isinstance(current_keyring, keyring.backends.SecretService.Keyring)

    @property
    def is_disabled(self):
        return hasattr(keyring.backends, 'null') and isinstance(self.keyring, keyring.backends.null.Keyring)

    @property
    def keyring(self):
        current_keyring = keyring.get_keyring()

        if isinstance(current_keyring, keyring.backends.chainer.ChainerBackend):
            # Search SecretService backend
            for backend in current_keyring.backends:
                if isinstance(backend, keyring.backends.SecretService.Keyring):
                    return backend

            return None

        return current_keyring

    def get(self, service):
        if self.is_disabled:
            return None

        current_keyring = self.keyring
        if isinstance(current_keyring, keyring.backends.SecretService.Keyring):
            collection = current_keyring.get_preferred_collection()

            credential = None
            with closing(collection.connection):
                items = collection.search_items({'service': service})
                for item in items:
                    current_keyring.unlock(item)
                    username = item.get_attributes().get('username')
                    if username is None:
                        # Try to find username in 'login' attribute instead of 'username'
                        # Backward compatibility with the previous implementation which used libsecret
                        username = item.get_attributes().get('login')
                    if username:
                        credential = CustomCredential(username, item.get_secret().decode('utf-8'), item.get_attributes().get('address'))
        else:
            # Fallback backend
            credential = current_keyring.get_credential(service, None)

        if credential is None or credential.username is None:
            return None

        return credential

    def store(self, service, username, password, address=None):
        if self.is_disabled:
            return

        current_keyring = self.keyring
        if isinstance(current_keyring, keyring.backends.SecretService.Keyring):
            collection = current_keyring.get_preferred_collection()

            label = f'{self.appid}: {username}@{service}'
            attributes = {
                'application': self.appid,
                'service': service,
                'username': username,
            }
            if address is not None:
                attributes['address'] = address

            with closing(collection.connection):
                # Delete previous credential if exists
                items = collection.search_items({'service': service})
                for item in items:
                    item.delete()

                collection.create_item(label, attributes, password)
        else:
            # Fallback backend
            current_keyring.set_password(service, username, password, address)


class PlaintextKeyring(keyring.backend.KeyringBackend):
    """Simple File Keyring with no encryption

    Used as fallback when no supported Keyring backend is found
    """

    priority = 1

    def __init__(self):
        super().__init__()

    @property
    def filename(self):
        return os.path.join(self.folder, 'plaintext.keyring')

    @property
    def folder(self):
        return os.path.join(get_data_dir(), 'keyrings')

    def _read(self):
        if not os.path.exists(self.filename):
            return {}

        with open(self.filename, 'r') as fp:
            return json.load(fp)

    def _save(self, data):
        if not os.path.exists(self.folder):
            os.mkdir(self.folder)

        with open(self.filename, 'w+') as fp:
            json.dump(data, fp, indent=2)

        os.chmod(self.filename, 0o600)

    def get_credential(self, service, _username):
        data = self._read()
        if service in data:
            return CustomCredential(data[service]['username'], data[service]['password'], data[service].get('address'))
        return None

    def get_password(self, service, username):
        pass

    def set_password(self, service, username, password, address=None):
        data = self._read()
        data[service] = dict(
            username=username,
            password=password,
        )
        if address is not None:
            data[service]['address'] = address
        self._save(data)
