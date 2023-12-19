# Copyright (C) 2019-2023 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import gc
from gettext import gettext as _
from queue import Empty, Queue
import threading
import time

from gi.repository import GLib

from komikku.explorer.common import DOWNLOAD_MAX_DELAY
from komikku.explorer.common import ExplorerSearchResultRow
from komikku.explorer.common import ExplorerSearchStackPage
from komikku.utils import log_error_traceback


class ExplorerSearchStackPageSearch(ExplorerSearchStackPage):
    __gtype_name__ = 'ExplorerSearchStackPageSearch'

    def __init__(self, parent):
        ExplorerSearchStackPage.__init__(self, parent)

        self.stack = self.parent.search_stack
        self.spinner = self.parent.search_spinner
        self.listbox = self.parent.search_listbox
        self.no_results_status_page = self.parent.search_no_results_status_page

        self.listbox.connect('row-activated', self.parent.on_manga_clicked)

    def search(self, term):
        # Find manga by Id
        if term.startswith('id:'):
            slug = term[3:]

            if not slug:
                return

            self.parent.show_manga_card(dict(slug=slug))
            return

        # Disallow empty search except for 'Local' server
        if not term and self.parent.server.id != 'local':
            return

        def run(server, queue):
            self.parent.register_request('search')

            try:
                if results := server.search(term, **self.parent.search_filters):
                    GLib.idle_add(complete, results, server, queue)
                else:
                    GLib.idle_add(error, results, server)
            except Exception as e:
                user_error_message = log_error_traceback(e)
                GLib.idle_add(error, None, server, user_error_message)
            finally:
                gc.collect()

        def run_covers(queue):
            while not queue.empty():
                try:
                    row, server = queue.get()
                except Empty:
                    continue
                else:
                    if self.window.page == self.parent.props.tag or self.window.previous_page == self.parent.props.tag:
                        start = time.time()
                        try:
                            data, _etag = server.get_manga_cover_image(row.manga_data['cover'])
                        except Exception:
                            pass
                        else:
                            GLib.idle_add(row.set_cover, data)

                            delay = min(2 * (time.time() - start), DOWNLOAD_MAX_DELAY)
                            if delay:
                                time.sleep(delay)

                    queue.task_done()

        def complete(results, server, queue):
            self.spinner.stop()

            if not self.parent.can_page_be_updated_with_results('search', server.id):
                return

            self.listbox.set_visible(True)

            for item in results:
                row = ExplorerSearchResultRow(item)
                self.listbox.append(row)
                if row.has_cover:
                    queue.put((row, server))

            self.stack.set_visible_child_name('results')

            thread_covers.start()

        def error(results, server, message=None):
            self.spinner.stop()

            if not self.parent.can_page_be_updated_with_results('search', server.id):
                return

            if results is None:
                self.no_results_status_page.set_title(_('Oops, search failed. Please try again.'))
                if message:
                    self.no_results_status_page.set_description(message)
            else:
                self.no_results_status_page.set_title(_('No Results Found'))
                self.no_results_status_page.set_description(_('Try a different search'))

            self.stack.set_visible_child_name('no_results')

        self.clear()
        self.spinner.start()
        self.stack.set_visible_child_name('loading')
        self.listbox.set_sort_func(None)

        if self.parent.requests.get('search') and self.parent.server.id in self.parent.requests['search']:
            self.window.show_notification(_('A request is already in progress.'), 2)
            return

        queue = Queue()

        thread = threading.Thread(target=run, args=(self.parent.server, queue))
        thread.daemon = True
        thread.start()

        thread_covers = threading.Thread(target=run_covers, args=(queue, ))
        thread_covers.daemon = True
