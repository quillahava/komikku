# Copyright (C) 2019-2024 Valéry Febvre
# SPDX-License-Identifier: GPL-3.0-only or GPL-3.0-or-later
# Author: Valéry Febvre <vfebvre@easter-eggs.com>

from io import BytesIO
import logging
import math
import platform

import gi
from PIL import Image
from PIL import ImageChops

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Graphene', '1.0')

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Graphene
from gi.repository import Gsk
from gi.repository import Gtk
from gi.repository.GdkPixbuf import PixbufAnimation

logger = logging.getLogger('komikku')

ZOOM_FACTOR_DOUBLE_TAP = 2.5
ZOOM_FACTOR_MAX = 20
ZOOM_FACTOR_SCROLL_WHEEL = 1.3


class KImage(Gtk.Widget, Gtk.Scrollable):
    __gtype_name__ = 'KImage'
    __gsignals__ = {
        'clicked': (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
        'rendered': (GObject.SignalFlags.RUN_FIRST, None, (bool, )),
        'zoom-begin': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'zoom-end': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, path, data, texture, pixbuf, scaling='screen', crop=False, landscape_zoom=False, can_zoom=False):
        super().__init__()

        self.__rendered = False
        self.__can_zoom = can_zoom
        self.__crop = crop
        self.__hadj = None
        self.__landscape_zoom = self.__can_zoom and landscape_zoom
        self.__scaling = scaling
        self.__vadj = None
        self.__zoom = 1

        self.data = data
        self.path = path

        self.texture = texture
        self.texture_crop = None
        self.crop_bbox = None

        self.pixbuf = pixbuf
        self.animation_iter = None
        self.animation_tick_callback_id = None

        if texture:
            self.ratio = texture.get_width() / texture.get_height()
        else:
            self.ratio = pixbuf.get_width() / pixbuf.get_height()

        self.gesture_click_timeout_id = None
        self.pointer_position = None  # current pointer position
        self.zoom_center = None  # zoom position in image
        self.zoom_gesture_begin = None
        self.zoom_scaling = None  # zoom factor at scaling

        self.set_overflow(Gtk.Overflow.HIDDEN)

        if self.__can_zoom:
            # Controller to track pointer motion: used to know current cursor position
            self.controller_motion = Gtk.EventControllerMotion.new()
            self.add_controller(self.controller_motion)
            self.controller_motion.connect('motion', self.on_pointer_motion)

            # Controller to zoom with mouse wheel or Ctrl + 2-fingers touchpad gesture
            self.controller_scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
            self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.add_controller(self.controller_scroll)
            self.controller_scroll.connect('scroll', self.on_scroll)

            # Gesture click controller: double-tap zoom
            self.gesture_click = Gtk.GestureClick.new()
            self.gesture_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.gesture_click.set_button(1)
            self.gesture_click.connect('released', self.on_gesture_click_released)
            self.add_controller(self.gesture_click)

            # Gesture zoom controller (2-fingers touchpad/touchscreen gesture)
            self.gesture_zoom = Gtk.GestureZoom.new()
            self.gesture_zoom.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.gesture_zoom.connect('begin', self.on_gesture_zoom_begin)
            self.gesture_zoom.connect('end', self.on_gesture_zoom_end)
            self.gesture_zoom.connect('scale-changed', self.on_gesture_zoom_scale_changed)
            self.add_controller(self.gesture_zoom)

        if isinstance(self.pixbuf, PixbufAnimation):
            self.animation_iter = self.pixbuf.get_iter(None)
            self.animation_tick_callback_id = self.add_tick_callback(self.__animation_tick_callback)

    @classmethod
    def new_from_data(cls, data, scaling='screen', crop=False, landscape_zoom=False, can_zoom=False, static_animation=False):
        mime_type, _result_uncertain = Gio.content_type_guess(None, data)
        if not mime_type:
            return None

        try:
            if mime_type == 'image/gif' and not static_animation:
                stream = Gio.MemoryInputStream.new_from_data(data, None)
                pixbuf = PixbufAnimation.new_from_stream(stream)
                stream.close()
                texture = None
            else:
                pixbuf = None
                texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(None, data, texture, pixbuf, scaling=scaling, crop=crop, landscape_zoom=landscape_zoom, can_zoom=can_zoom)

    @classmethod
    def new_from_file(cls, path, scaling='screen', crop=False, landscape_zoom=False, can_zoom=False, static_animation=False):
        mime_type, _result_uncertain = Gio.content_type_guess(path, None)
        if not mime_type:
            return None

        try:
            if mime_type == 'image/gif' and not static_animation:
                pixbuf = PixbufAnimation.new_from_file(path)
                texture = None
            else:
                pixbuf = None
                texture = Gdk.Texture.new_from_filename(path)
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(path, None, texture, pixbuf, scaling=scaling, crop=crop, landscape_zoom=landscape_zoom, can_zoom=can_zoom)

    @classmethod
    def new_from_resource(cls, path):
        try:
            texture = Gdk.Texture.new_from_resource(path)
        except Exception:
            # Invalid image, corrupted image, unsupported image format,...
            return None

        return cls(None, None, texture, None)

    @property
    def borders(self):
        """ Width of vertical (top, bottom) and horizontal (left, right) bars """
        if self.widget_width > self.image_displayed_width:
            hborder = (self.widget_width - self.image_displayed_width) / 2
        else:
            hborder = 0

        if self.widget_height > self.image_displayed_height:
            vborder = (self.widget_height - self.image_displayed_height) / 2
        else:
            vborder = 0

        return (hborder, vborder)

    @property
    def can_zoom(self):
        return self.__can_zoom

    @GObject.Property(type=bool, default=False)
    def crop(self):
        return self.__crop and not self.animation_iter

    @crop.setter
    def crop(self, value):
        if self.__crop == value or self.animation_iter:
            return
        self.__crop = value
        self.queue_resize()

    @GObject.Property(type=Gtk.Adjustment)
    def hadjustment(self):
        return self.__hadj or Gtk.Adjustment()

    @hadjustment.setter
    def hadjustment(self, adj):
        if not adj:
            return
        adj.connect('value-changed', lambda adj: self.queue_draw())
        self.__hadj = adj
        self.configure_adjustments()

    @GObject.Property(type=Gtk.ScrollablePolicy, default=Gtk.ScrollablePolicy.MINIMUM)
    def hscroll_policy(self):
        return Gtk.ScrollablePolicy.MINIMUM

    @property
    def image_height(self):
        """ Image original height """
        if self.pixbuf:
            return self.pixbuf.get_height()

        if self.crop and self.crop_bbox:
            return self.crop_bbox[3] - self.crop_bbox[1]

        return self.texture.get_height() if self.texture else 0

    @property
    def image_width(self):
        """ Image original width """
        if self.pixbuf:
            return self.pixbuf.get_width()

        if self.crop and self.crop_bbox:
            return self.crop_bbox[2] - self.crop_bbox[0]

        return self.texture.get_width() if self.texture else 0

    @property
    def image_displayed_height(self):
        """ Image height with current zoom factor """
        return int(self.image_height * self.zoom)

    @property
    def image_displayed_width(self):
        """ Image width with current zoom factor """
        return int(self.image_width * self.zoom)

    @GObject.Property(type=bool, default=False)
    def landscape_zoom(self):
        return self.__landscape_zoom

    @landscape_zoom.setter
    def landscape_zoom(self, value):
        if self.__landscape_zoom == value:
            return
        self.__landscape_zoom = value
        self.queue_resize()

    @property
    def max_hadjustment_value(self):
        return max(self.image_displayed_width - self.widget_width, 0)

    @property
    def max_vadjustment_value(self):
        return max(self.image_displayed_height - self.widget_height, 0)

    @GObject.Property(type=str, default='screen')
    def scaling(self):
        """ Type of scaling:
        - adapt to screen (best-fit)
        - adapt to width
        - adapt to height
        - original size
        """
        return self.__scaling

    @scaling.setter
    def scaling(self, value):
        if self.__scaling == value:
            return
        self.__scaling = value
        self.queue_resize()

    @property
    def scaling_size(self):
        """ Image size at defined scaling """
        scaling = self.scaling
        if scaling != 'original':
            if self.landscape_zoom and scaling == 'screen' and self.image_width > self.image_height:
                # When page is landscape and scaling is 'screen', scale page to fit height
                scaling = 'height'

            max_width = self.widget_width
            max_height = self.widget_height

            adapt_to_width_height = max_width * self.image_height // self.image_width
            adapt_to_height_width = max_height * self.image_width // self.image_height

            if scaling == 'width' or (scaling == 'screen' and adapt_to_width_height <= max_height):
                # Adapt image to width
                width = max_width
                height = adapt_to_width_height
            elif scaling == 'height' or (scaling == 'screen' and adapt_to_height_width <= max_width):
                # Adapt image to height
                width = adapt_to_height_width
                height = max_height
        else:
            width = self.image_width
            height = self.image_height

        return (width, height)

    @property
    def scrollable(self):
        return isinstance(self.get_parent(), Gtk.ScrolledWindow)

    @GObject.Property(type=Gtk.Adjustment)
    def vadjustment(self):
        return self.__vadj or Gtk.Adjustment()

    @vadjustment.setter
    def vadjustment(self, adj):
        if not adj:
            return
        adj.connect('value-changed', lambda adj: self.queue_draw())
        self.__vadj = adj
        self.configure_adjustments()

    @GObject.Property(type=Gtk.ScrollablePolicy, default=Gtk.ScrollablePolicy.MINIMUM)
    def vscroll_policy(self):
        return Gtk.ScrollablePolicy.MINIMUM

    @property
    def widget_height(self):
        return self.get_height()

    @property
    def widget_width(self):
        return self.get_width()

    @GObject.Property(type=float)
    def zoom(self):
        """ Displayed zoom level """
        return self.__zoom

    @zoom.setter
    def zoom(self, value):
        if self.__zoom == value:
            return
        self.__zoom = value
        self.queue_resize()

    def __animation_tick_callback(self, image, clock):
        if self.animation_iter is None:
            return GLib.SOURCE_REMOVE

        # Do not animate if not visible
        if not self.get_mapped():
            return GLib.SOURCE_CONTINUE

        delay = self.animation_iter.get_delay_time()
        if delay == -1:
            return GLib.SOURCE_REMOVE

        # Check if it's time to show the next frame
        if self.animation_iter.advance(None):
            self.queue_draw()

        return GLib.SOURCE_CONTINUE

    def __compute_borders_crop_bbox(self):
        threshold = 225

        if self.path is None and self.data is None:
            return None

        def lookup(x):
            return 255 if x > threshold else 0

        try:
            with Image.open(self.path or BytesIO(self.data)) as im:
                with im.convert('L') as im_bw:
                    im_lookup = im_bw.point(lookup, mode='1')
        except Exception as error:
            logger.debug(error)
            return None

        with Image.new(im_lookup.mode, im_lookup.size, 255) as im_bg:
            return ImageChops.difference(im_lookup, im_bg).getbbox()

    def cancel_deceleration(self):
        if isinstance(self.get_parent(), Gtk.ScrolledWindow):
            self.get_parent().set_kinetic_scrolling(False)
            self.get_parent().set_kinetic_scrolling(True)

    def configure_adjustments(self):
        self.hadjustment.configure(
            # value
            max(min(self.hadjustment.props.value, self.max_hadjustment_value), 0),
            # lower value
            0,
            # upper value
            self.image_displayed_width,
            # step increment
            self.widget_width * 0.1,
            # page increment
            self.widget_width * 0.9,
            # page size
            min(self.widget_width, self.image_displayed_width)
        )

        self.vadjustment.configure(
            max(min(self.vadjustment.props.value, self.max_vadjustment_value), 0),
            0,
            self.image_displayed_height,
            self.widget_height * 0.1,
            self.widget_height * 0.9,
            min(self.widget_height, self.image_displayed_height)
        )

    def dispose(self):
        if self.__can_zoom:
            self.remove_controller(self.controller_motion)
            self.remove_controller(self.controller_scroll)
            self.remove_controller(self.gesture_click)
            self.remove_controller(self.gesture_zoom)

        if self.animation_tick_callback_id:
            self.remove_tick_callback(self.animation_tick_callback_id)

        self.pixbuf = None
        self.animation_iter = None
        self.texture = None
        self.texture_crop = None

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 0, int(for_size * self.ratio) if for_size != -1 else -1, -1, -1

        return 0, int(for_size / self.ratio) if for_size != -1 else -1, -1, -1

    def do_size_allocate(self, w, h, b):
        if self.crop and self.crop_bbox is None:
            self.crop_bbox = self.__compute_borders_crop_bbox()

        if self.zoom_scaling is None or self.zoom == self.zoom_scaling:
            self.zoom_scaling = self.scaling_size[0] / self.image_width
            self.set_zoom()
        else:
            self.configure_adjustments()

    def do_snapshot(self, snapshot):
        def crop_borders():
            """ Crop white borders """
            # Crop is possible if computed bbox is included in texture
            bbox = self.crop_bbox
            if bbox and (bbox[2] - bbox[0] < self.texture.get_width() or bbox[3] - bbox[1] < self.texture.get_height()):
                try:
                    with Image.open(self.path or BytesIO(self.data)) as im:
                        with im.convert('RGB') as im_rgb:
                            with im_rgb.crop(bbox) as im_crop:
                                with BytesIO() as io_buffer:
                                    # Use the very fast TIFF format (Pillow uses libtiff)
                                    im_crop.save(io_buffer, 'tiff')
                                    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(io_buffer.getvalue()))
                except Exception as error:
                    logger.debug(error)
                    return self.texture

            return self.texture

        if self.texture and self.crop and self.texture_crop is None:
            # Crop white borders
            self.texture_crop = crop_borders()
        elif self.animation_iter:
            # Get next frame (animated GIF)
            self.texture = Gdk.Texture.new_for_pixbuf(self.animation_iter.get_pixbuf())

        self.configure_adjustments()

        snapshot.save()

        width = self.image_displayed_width
        height = self.image_displayed_height

        if self.scrollable:
            x = -(self.hadjustment.props.value - (self.hadjustment.props.upper - width) / 2)
            snapshot.translate(Graphene.Point().init(int(x), 0))
            y = -(self.vadjustment.props.value - (self.vadjustment.props.upper - height) / 2)
            snapshot.translate(Graphene.Point().init(0, int(y)))

            # Center in widget when no scrolling
            snapshot.translate(
                Graphene.Point().init(
                    max((self.widget_width - width) // 2, 0),
                    max((self.widget_height - height) // 2, 0),
                )
            )

        # Append texture
        scale_factor = self.get_scale_factor()
        rect = Graphene.Rect().alloc()
        rect.init(0, 0, width * scale_factor, height * scale_factor)
        if self.zoom < 1:
            if self.texture.get_height() > 8192 and platform.machine() == 'aarch64':
                filter = Gsk.ScalingFilter.LINEAR
            else:
                filter = Gsk.ScalingFilter.TRILINEAR
        else:
            filter = Gsk.ScalingFilter.NEAREST
        if scale_factor != 1:
            snapshot.scale(1 / scale_factor, 1 / scale_factor)
        snapshot.append_scaled_texture(self.texture_crop if self.crop else self.texture, filter, rect)

        snapshot.restore()

        self.emit('rendered', self.__rendered)
        if not self.__rendered:
            self.__rendered = True

    def on_gesture_click_released(self, _gesture, n_press, x, y):
        def emit_clicked(x, y):
            GLib.source_remove(self.gesture_click_timeout_id)
            self.gesture_click_timeout_id = None
            self.emit('clicked', x, y)

        if n_press == 1 and self.gesture_click_timeout_id is None and self.zoom == self.zoom_scaling:
            # Schedule single click event to be able to detect double click
            dbl_click_time = Gtk.Settings.get_default().get_property('gtk-double-click-time')
            self.gesture_click_timeout_id = GLib.timeout_add(dbl_click_time, emit_clicked, x, y)

        elif n_press == 2:
            # Remove scheduled single click event
            if self.gesture_click_timeout_id:
                GLib.source_remove(self.gesture_click_timeout_id)
                self.gesture_click_timeout_id = None

            if self.zoom == self.zoom_scaling:
                self.set_zoom(self.zoom * ZOOM_FACTOR_DOUBLE_TAP, (x, y))
            else:
                self.set_zoom(self.zoom_scaling)

    def on_gesture_zoom_begin(self, _gesture, _sequence):
        self.cancel_deceleration()

        _active, x, y = self.gesture_zoom.get_bounding_box_center()
        self.zoom_center = (x, y)
        self.zoom_gesture_begin = self.zoom

        self.gesture_zoom.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_gesture_zoom_end(self, _gesture, _sequence):
        self.gesture_zoom.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_gesture_zoom_scale_changed(self, _gesture, scale):
        self.set_zoom(min(self.zoom_gesture_begin * scale, ZOOM_FACTOR_MAX), self.zoom_center)

        if self.gesture_zoom.get_device().get_source() == Gdk.InputSource.TOUCHSCREEN and self.zoom_center:
            # Move image to follow zoom position on touchscreen
            _active, x, y = self.gesture_zoom.get_bounding_box_center()
            self.hadjustment.set_value(self.hadjustment.get_value() + self.zoom_center[0] - x)
            self.vadjustment.set_value(self.vadjustment.get_value() + self.zoom_center[1] - y)
            self.zoom_center = (x, y)

        self.gesture_zoom.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_pointer_motion(self, _controller, x, y):
        self.pointer_position = (x, y)

    def on_scroll(self, _controller, _dx, dy):
        """ <Ctrl>+Scroll zooming """
        modifiers = Gtk.accelerator_get_default_mod_mask()
        state = self.controller_scroll.get_current_event_state()
        if state & modifiers == Gdk.ModifierType.CONTROL_MASK:
            factor = math.exp(-dy * math.log(ZOOM_FACTOR_SCROLL_WHEEL))
            self.set_zoom(self.zoom * factor, self.pointer_position)
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def set_allow_zooming(self, allow):
        if not self.__can_zoom:
            return

        self.controller_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE if allow else Gtk.PropagationPhase.NONE)
        self.gesture_zoom.set_propagation_phase(Gtk.PropagationPhase.CAPTURE if allow else Gtk.PropagationPhase.NONE)

    def set_zoom(self, zoom=None, center=None):
        """ Set zoom level for given position """

        if zoom is None:
            zoom = self.zoom_scaling
        else:
            zoom = max(zoom, self.zoom_scaling)
            if zoom != self.zoom_scaling and self.zoom == self.zoom_scaling:
                self.emit('zoom-begin')
            elif zoom == self.zoom_scaling and self.zoom != self.zoom_scaling:
                self.emit('zoom-end')

        if center:
            borders = self.borders
            zoom_ratio = self.zoom / zoom

        self.zoom = zoom

        self.configure_adjustments()

        if center:
            hadjustment_value = self.hadjustment.get_value()
            vadjustment_value = self.vadjustment.get_value()

            x = center[0]
            y = center[1]

            value = max((x + hadjustment_value - borders[0]) / zoom_ratio - x, 0)
            self.hadjustment.set_value(value)

            value = max((y + vadjustment_value - borders[1]) / zoom_ratio - y, 0)
            self.vadjustment.set_value(value)
