# Copyright (C) 2019-2022 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _


class ServerException(Exception):
    def __init__(self, message):
        self.message = _('Error: {}').format(message)
        super().__init__(self.message)


class ArchiveError(ServerException):
    def __init__(self):
        super().__init__(_('Local archive is corrupt.'))


class ArchiveUnrarMissingError(ServerException):
    def __init__(self):
        super().__init__(_("Unable to extract page. Maybe the 'unrar' tool is missing?"))


class CloudflareBypassError(ServerException):
    def __init__(self):
        super().__init__(_('Failed to bypass Cloudflare protection. Please try again.'))


class NotFoundError(ServerException):
    def __init__(self):
        super().__init__(_('No longer exists.'))
