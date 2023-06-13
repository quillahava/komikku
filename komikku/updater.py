# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from gettext import gettext as _
from gettext import ngettext
import threading

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject

from komikku.utils import log_error_traceback
from komikku.models import create_db_connection
from komikku.models import Manga
from komikku.models import Settings
from komikku.utils import if_network_available


class Updater(GObject.GObject):
    """
    Mangas updater
    """
    __gsignals__ = {
        'manga-updated': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT, int, int, bool)),
    }

    queue = []
    running = False
    stop_flag = False
    update_at_startup_done = False
    update_library_flag = False

    def __init__(self, window):
        GObject.GObject.__init__(self)

        self.window = window

    def add(self, mangas):
        if not isinstance(mangas, list):
            mangas = [mangas, ]
        mangas.reverse()

        for manga in mangas:
            if manga.id not in self.queue and manga.server.status == 'enabled':
                self.queue.append(manga.id)

    @if_network_available
    def start(self):
        def show_notification(id, title, body=None):
            if Settings.get_default().desktop_notifications:
                notification = Gio.Notification.new(title)
                notification.set_priority(Gio.NotificationPriority.HIGH)
                if body:
                    notification.set_body(body)
                self.window.application.send_notification(id, notification)
            else:
                # Use in-app notification
                self.window.show_notification(f'{title}\n{body}' if body else title)

        def run():
            total_chapters = 0
            total_errors = 0
            total_successes = 0

            while self.queue:
                if self.stop_flag is True:
                    break

                manga = Manga.get(self.queue.pop(0))
                if manga is None:
                    continue

                try:
                    status, recent_chapters_ids, nb_deleted_chapters, synced = manga.update_full()
                    if status is True:
                        nb_chapters = len(recent_chapters_ids)
                        if nb_chapters > 0:
                            total_chapters += nb_chapters
                            total_successes += 1
                        GLib.idle_add(complete, manga, recent_chapters_ids, nb_deleted_chapters, synced)
                    else:
                        total_errors += 1
                        GLib.idle_add(error, manga)
                except Exception as e:
                    user_error_message = log_error_traceback(e)
                    total_errors += 1
                    GLib.idle_add(error, manga, user_error_message)

            self.running = False

            # End notification
            if self.update_library_flag:
                self.update_library_flag = False
                if total_errors > 0:
                    title = _('Library update completed with errors')
                else:
                    title = _('Library update completed')
            else:
                if total_errors > 0:
                    title = _('Update completed with errors')
                else:
                    title = _('Update completed')

            messages = []
            if total_chapters > 0:
                messages.append(ngettext('{0} successful update', '{0} successful updates', total_successes).format(total_successes))
                messages.append(ngettext('{0} new chapter', '{0} new chapters', total_chapters).format(total_chapters))
            else:
                messages.append(_('No new chapters'))

            if total_errors > 0:
                messages.append(ngettext('{0} update failed', '{0} updates failed', total_errors).format(total_errors))

            GLib.timeout_add(2000, show_notification, 'updater.0', title, '\n'.join(messages))

        def complete(manga, recent_chapters_ids, nb_deleted_chapters, synced):
            nb_recent_chapters = len(recent_chapters_ids)

            if nb_recent_chapters > 0:
                show_notification(
                    f'updater.{manga.id}',
                    manga.name,
                    ngettext('{0} new chapter', '{0} new chapters', nb_recent_chapters).format(nb_recent_chapters)
                )

                # Auto download new chapters
                if Settings.get_default().new_chapters_auto_download:
                    self.window.downloader.add(recent_chapters_ids)
                    self.window.downloader.start()

            self.emit('manga-updated', manga, nb_recent_chapters, nb_deleted_chapters, synced)

            return False

        def error(manga, message=None):
            show_notification(
                f'updater.{manga.id}',
                manga.name,
                message or _('Oops, update has failed. Please try again.')
            )

            return False

        if self.running or len(self.queue) == 0:
            return

        if self.update_library_flag:
            title = _('Library update started')
        else:
            title = _('Update started')
        show_notification('updater.0', title)

        self.running = True
        self.stop_flag = False

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def remove(self, manga):
        if manga.id in self.queue:
            self.queue.remove(manga.id)

    def stop(self):
        if self.running:
            self.stop_flag = True

    @if_network_available
    def update_library(self, startup=False):
        self.update_library_flag = True
        if startup:
            self.update_at_startup_done = True

        db_conn = create_db_connection()
        rows = db_conn.execute('SELECT * FROM mangas WHERE in_library = 1 ORDER BY last_read DESC').fetchall()
        db_conn.close()

        for row in rows:
            self.add(Manga.get(row['id']))

        self.start()
