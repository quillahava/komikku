# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

import gi
import os
import platform

gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
gi.require_version('Soup', '3.0')
gi.require_version('WebKit', '6.0')

from gi.repository import Adw
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gsk
from gi.repository import Gtk
from gi.repository import Soup
from gi.repository import WebKit

from komikku.models.database import VERSION as DB_VERSION
from komikku.utils import check_cmdline_tool


class DebugInfo:
    def __init__(self, app):
        self.app_id = app.application_id
        self.profile = app.profile
        self.version = app.version

    def get_flatpak_info(self):
        path = os.path.join(GLib.get_user_runtime_dir(), 'flatpak-info')
        if not os.path.exists(path):
            return None

        data = [
            ('Application', 'runtime'),
            ('Instance', 'runtime-commit'),
            ('Instance', 'arch'),
            ('Instance', 'flatpak-version'),
            ('Instance', 'devel'),
        ]

        info = dict()
        keyfile = GLib.KeyFile.new()
        keyfile.load_from_file(path, 0)
        for group, key in data:
            try:
                info[key] = keyfile.get_string(group, key)
            except Exception:
                info[key] = 'N/A'

        return info

    def get_gtk_info(self):
        info = {}

        display = Gdk.Display.get_default()

        backend = display.__class__.__name__
        if backend == 'X11Display':
            info['backend'] = 'X11'
        elif backend == 'WaylandDisplay':
            info['backend'] = 'Wayland'
        elif backend == 'BroadwayDisplay':
            info['backend'] = 'Broadway'
        elif backend == 'GdkMacosDisplay':
            info['backend'] = 'macOS'
        else:
            info['backend'] = backend

        surface = Gdk.Surface.new_toplevel(display)
        gsk_renderer = Gsk.Renderer.new_for_surface(surface)

        renderer = gsk_renderer.__class__.__name__
        if renderer == 'VulkanRenderer':
            info['renderer'] = 'Vulkan'
        elif renderer == 'GLRenderer':
            info['renderer'] = 'GL'
        elif renderer == 'CairoRenderer':
            info['renderer'] = 'Cairo'
        else:
            info['renderer'] = renderer

        info['animations'] = Gtk.Settings.get_default().get_property('gtk-enable-animations')
        info['theme'] = Gtk.Settings.get_default().get_property('gtk-theme-name')
        info['icon-theme'] = Gtk.Settings.get_default().get_property('gtk-icon-theme-name')

        gsk_renderer.unrealize()

        return info

    def get_tools_info(self):
        info = {}

        # Unrar (not available in flatpak sandbox)
        status, ret = check_cmdline_tool('unrar')
        info['unrar'] = ret.split('\n')[0] if status else 'N/A'

        # Unar
        status, ret = check_cmdline_tool(['unar', '-v'])
        if not status:
            # Check flatpak location
            status, ret = check_cmdline_tool(['/app/bin/unar', '-v'])
        info['unar'] = ret if status else 'N/A'

        return info

    def generate(self):
        info = 'Komikku:\n'
        info += f'- Version: {self.version}\n'
        info += f'- Profile: {self.profile}\n'
        info += f'- DB version: {DB_VERSION}\n'
        info += f'- ID: {self.app_id}\n'
        info += '\n'

        info += 'Compiled against:\n'
        info += f'- GLib: {GLib.MAJOR_VERSION}.{GLib.MINOR_VERSION}.{GLib.MICRO_VERSION}\n'
        info += f'- GTK: {Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}.{Gtk.MICRO_VERSION}\n'
        info += f'- Adwaita: {Adw.VERSION_S}\n'
        info += f'- WebKitGTK: {WebKit.MAJOR_VERSION}.{WebKit.MINOR_VERSION}.{WebKit.MICRO_VERSION}\n'
        info += f'- Soup: {Soup.MAJOR_VERSION}.{Soup.MINOR_VERSION}.{Soup.MICRO_VERSION}\n'
        info += '\n'

        info += 'Running against:\n'
        info += f'- GLib: {GLib.glib_version[0]}.{GLib.glib_version[1]}.{GLib.glib_version[2]}\n'
        info += f'- GTK: {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}\n'
        info += f'- Adwaita: {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}\n'
        info += f'- WebKitGTK: {WebKit.get_major_version()}.{WebKit.get_minor_version()}.{WebKit.get_micro_version()}\n'
        info += f'- Soup: {Soup.get_major_version()}.{Soup.get_minor_version()}.{Soup.get_micro_version()}\n'
        info += '\n'

        info += 'System:\n'
        info += f'- Name: {GLib.get_os_info("NAME")}\n'
        info += f'- Version: {GLib.get_os_info("VERSION") or "N/A"}\n'
        info += f"- CPU arch: {platform.machine()}\n"
        info += '\n'

        if flatpak_info := self.get_flatpak_info():
            info += 'Flatpak:\n'
            info += f'- Runtime: {flatpak_info["runtime"]}\n'
            info += f'- Runtime commit: {flatpak_info["runtime-commit"]}\n'
            info += f'- Arch: {flatpak_info["arch"]}\n'
            info += f'- Flatpak version: {flatpak_info["flatpak-version"]}\n'
            info += f'- Devel: {flatpak_info["devel"]}\n'
            info += '\n'

        gtk_info = self.get_gtk_info()
        info += 'GTK:\n'
        info += f"- GDK backend: {gtk_info['backend']}\n"
        info += f"- GSK renderer: {gtk_info['renderer']}\n"
        info += f"- Animations: {gtk_info['animations']}\n"
        info += f"- Theme: {gtk_info['theme']}\n"
        info += f"- Icon theme: {gtk_info['icon-theme']}\n"
        info += '\n'

        info += 'Python:\n'
        info += f"- Version: {platform.python_version()}\n"
        info += f"- PyGObject: {'.'.join(str(v) for v in gi.version_info)}\n"
        info += '\n'

        info += 'Environment:\n'
        info += f'- Desktop: {GLib.getenv("XDG_CURRENT_DESKTOP")}\n'
        info += f'- Session: {GLib.getenv("XDG_SESSION_DESKTOP")} ({GLib.getenv("XDG_SESSION_TYPE")})\n'
        info += f'- Language: {GLib.getenv("LANG")}\n'
        info += f'- Running inside Builder: {"Yes" if GLib.getenv("INSIDE_GNOME_BUILDER") else "No"}\n'
        if gtk_debug := GLib.getenv("GTK_DEBUG"):
            info += f'- GTK_DEBUG: {gtk_debug}\n'
        if gtk_theme := GLib.getenv("GTK_THEME"):
            info += f'- GTK_THEME: {gtk_theme}\n'
        if adw_debug_color_scheme := GLib.getenv("ADW_DEBUG_COLOR_SCHEME"):
            info += f'- ADW_DEBUG_COLOR_SCHEME: {adw_debug_color_scheme}\n'
        if adw_debug_high_contrast := GLib.getenv("ADW_DEBUG_HIGH_CONTRAST"):
            info += f'- ADW_DEBUG_HIGH_CONTRAST: {adw_debug_high_contrast}\n'
        if adw_disable_portal := GLib.getenv("ADW_DISABLE_PORTAL"):
            info += f'- ADW_DISABLE_PORTAL: {adw_disable_portal}\n'
        info += '\n'

        tools_info = self.get_tools_info()
        info += 'Command-line tools:\n'
        info += f'- unrar: {tools_info["unrar"]}\n'
        info += f'- unar: {tools_info["unar"]}'

        return info
