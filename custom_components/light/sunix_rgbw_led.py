"""
Support for the Sunix RGB / RGBWWCW WiFi LED Strip controller

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/light.sunix/
"""

import logging
from enum import Enum

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_EFFECT, ATTR_COLOR_TEMP, SUPPORT_BRIGHTNESS,
    SUPPORT_RGB_COLOR, SUPPORT_COLOR_TEMP, SUPPORT_EFFECT, Light)
from homeassistant.const import CONF_PLATFORM, CONF_NAME, DEVICE_DEFAULT_NAME, CONF_HOST
from homeassistant.util.color import (
    color_temperature_mired_to_kelvin as mired_to_kelvin,
    color_temperature_to_rgb,
    color_rgb_to_rgbw,
    color_RGB_to_xy)
from sunix_ledstrip_controller_client import LEDStripControllerClient
from sunix_ledstrip_controller_client.controller import Controller
from sunix_ledstrip_controller_client.functions import FunctionId

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = []
REQUIREMENTS = ['sunix-ledstrip-controller-client==1.1.1']

CONF_PORT = 'port'
CONF_CALIBRATION_OFFSET = 'calibration_offset'
CONF_EFFECT_SPEED = 'effect_speed'

DEFAULT_EFFECT_SPEED = 250

# define configuration parameters
PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_PLATFORM): 'sunix_rgbw_led',
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=None):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    vol.Optional(CONF_NAME, default=DEVICE_DEFAULT_NAME): cv.string,
    vol.Optional(CONF_CALIBRATION_OFFSET, default=None):
        vol.All({cv.string: vol.All(vol.Coerce(int), vol.Range(min=-255, max=255))}),
    vol.Optional(CONF_EFFECT_SPEED, default=DEFAULT_EFFECT_SPEED):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=255))
}, extra=vol.ALLOW_EXTRA)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the light controller"""

    # read config
    name = config.get(CONF_NAME, None)
    host = config.get(CONF_HOST, None)
    port = config.get(CONF_PORT, None)

    color_offset = config.get(CONF_CALIBRATION_OFFSET, None)
    color_offset = [color_offset["red"], color_offset["green"], color_offset["blue"]]

    effect_speed = config.get(CONF_EFFECT_SPEED, DEFAULT_EFFECT_SPEED)

    # Create api client and device
    controller_client = LEDStripControllerClient()
    device = Controller(host, port, None, None)

    add_devices([SunixController(controller_client, device, name, color_offset, effect_speed)])


class ColorMode(Enum):
    RGB = 0
    COLOR_TEMPERATURE = 1
    EFFECT = 2


class SunixController(Light):
    """Representation of a Sunix controller device."""

    def __init__(self, api: LEDStripControllerClient, device: Controller, name: str, color_offset: [],
                 effect_speed: int):
        self._name = name
        self._api = api
        self._device = device

        self.update()

        self._rgb = self._device.get_rgbww()  # initial color
        self._brightness = self._device.get_brightness()  # initial brightness
        self._color_temp = 154  # initial color temp (most blueish)
        self._effect = None
        # self._effect = self._device.get_effect()
        self._effect_speed = effect_speed
        self._color_mode = ColorMode.RGB  # rgb color
        self._color_offset = color_offset  # calibration offset

    def get_rgbww_with_brightness(self, rgb) -> [int, int, int, int, int]:
        _LOGGER.debug("rgb: %s", rgb)

        if self._color_mode == ColorMode.COLOR_TEMPERATURE:  # color temperature
            _LOGGER.debug("temp: %s", self._color_temp)
            rgb = color_temperature_to_rgb(mired_to_kelvin(self._color_temp))
            _LOGGER.debug("rgb color_temp: %s", rgb)

            # apply color offset if any
            if self._color_offset:
                rgb = [
                    min(rgb[0] + self._color_offset[0], 255),
                    min(rgb[1] + self._color_offset[1], 255),
                    min(rgb[2] + self._color_offset[2], 255)
                ]
                _LOGGER.debug("rgb after offset: %s", rgb)

        rgbw = list(color_rgb_to_rgbw(rgb[0], rgb[1], rgb[2]))
        rgbw.append(rgbw[3])  # duplicate warm_white value for cold_white

        # _LOGGER.debug("RGBWW: %s", rgbw)

        # calculate color based on brightness since
        # the controller doesn't support it natively
        calculated_color = []
        for color in rgbw:
            calculated_color.append(int(color * (self._brightness / 255)))

        _LOGGER.debug("RGBWW after Brightness: %s", calculated_color)

        return calculated_color

    def check_args(self, turn_on, **kwargs):
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp = kwargs.get(ATTR_COLOR_TEMP)
        effect = kwargs.get(ATTR_EFFECT)

        if rgb:
            _LOGGER.debug("rgb: %s", rgb)
            self._rgb = rgb
            self._color_mode = ColorMode.RGB
        elif color_temp:
            _LOGGER.debug("color_temp: %s", color_temp)
            self._color_temp = color_temp
            self._color_mode = ColorMode.COLOR_TEMPERATURE
        elif effect:
            _LOGGER.debug("effect: %s", effect)
            self._effect = effect
            self._color_mode = ColorMode.EFFECT

        _LOGGER.debug("color_mode: %s", self._color_mode)

        if brightness:
            _LOGGER.debug("brightness: %s", brightness)
            self._brightness = brightness

        if self._color_mode != ColorMode.EFFECT:
            c = self.get_rgbww_with_brightness(self._rgb)
            _LOGGER.debug("setting color %s on %s", c, self._name)
            self._api.set_rgbww(self._device, c[0], c[1], c[2], c[3], c[4])
        else:
            _LOGGER.debug("setting function %s on %s", self._effect, self._name)
            self._api.set_function(self._device, FunctionId[self._effect], self._effect_speed)

        if turn_on:
            if not self.is_on:
                _LOGGER.debug("turning on %s", self._name)
                self._api.turn_on(self._device)
        else:
            if self.is_on:
                _LOGGER.debug("turning off %s", self._name)
                self._api.turn_off(self._device)

    @property
    def unique_id(self):
        """Return the ID of this light."""
        return "{}.{}".format(self.__class__, self._device.get_hardware_id())

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def brightness(self):
        """Return the brightness of the device."""
        return self._brightness

    @property
    def xy_color(self):
        """Return the XY color value [float, float]."""
        return color_RGB_to_xy(self._rgb[0], self._rgb[1], self._rgb[2])

    @property
    def rgb_color(self):
        """Return the RGB color value [int, int, int]."""
        return self._rgb

    @property
    def color_temp(self) -> int:
        """Return the color temperature."""
        return self._color_temp

    @property
    def effect_list(self) -> list:
        """Return the list of supported effects."""
        effect_list = []

        for effect in self._api.get_function_list():
            effect_list.append(effect.name)

        return effect_list

    @property
    def effect(self) -> str:
        """Return the current effect."""
        return self._effect

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_RGB_COLOR | SUPPORT_BRIGHTNESS | SUPPORT_COLOR_TEMP | SUPPORT_EFFECT

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._device.is_on()

    def turn_on(self, **kwargs):
        """Turn the light on"""
        self.check_args(True, **kwargs)

    def turn_off(self, **kwargs):
        """Turn the light off"""
        self.check_args(False, **kwargs)

    def update(self):
        """Update the state of this light."""
        self._api.update_state(self._device)
