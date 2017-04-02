"""
Support for the Sunix RGB / RGBWWCW WiFi LED Strip controller

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/light.sunix/
"""

import colorsys
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_RGB_COLOR, SUPPORT_BRIGHTNESS,
    SUPPORT_RGB_COLOR, SUPPORT_COLOR_TEMP, ATTR_COLOR_TEMP, Light)
from homeassistant.const import CONF_PLATFORM, CONF_NAME, DEVICE_DEFAULT_NAME, CONF_HOST
from homeassistant.util.color import (
    color_temperature_mired_to_kelvin as mired_to_kelvin,
    color_temperature_kelvin_to_mired as kelvin_to_mired,
    color_temperature_to_rgb,
    color_rgb_to_rgbw,
    color_rgbw_to_rgb,
    color_RGB_to_xy)
from sunix_ledstrip_controller_client import LEDStripControllerClient
from sunix_ledstrip_controller_client.controller import Controller

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = []
REQUIREMENTS = ['sunix-ledstrip-controller-client==1.0.0']

CONF_PORT = 'port'

# define configuration parameters
PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_PLATFORM): 'sunix_rgbw_led',
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=None):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    vol.Optional(CONF_NAME, default=DEVICE_DEFAULT_NAME): cv.string,
}, extra=vol.ALLOW_EXTRA)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the light controller"""

    # read config
    name = config.get(CONF_NAME, None)
    host = config.get(CONF_HOST, None)
    port = config.get(CONF_PORT, None)

    # Create api client and device
    controller_client = LEDStripControllerClient()
    device = Controller(host, port, None, None)

    add_devices([SunixController(controller_client, device, name)])


class SunixController(Light):
    """Representation of a Sunix controller device."""

    def __init__(self, api: LEDStripControllerClient, device: Controller, name: str):
        self._name = name
        self._api = api
        self._device = device

        self._rgb = [255, 255, 255]  # initial color
        self._brightness = 255  # initial brightness
        self._color_temp = 154  # initial color temp (most blueish)
        self._color_mode = 0  # rgb color

    def get_rgbww_with_brightness(self, rgb) -> [int, int, int, int, int]:
        _LOGGER.debug("rgb: %s", rgb)

        color_mode = int(self._color_mode)
        if color_mode == 1:  # color temperature
            _LOGGER.debug("temp: %s", self._color_temp)
            shifted_temp = (self._color_temp + (self._color_temp - 154) * 1.5)
            _LOGGER.error("shifted_temp: %s", shifted_temp)

            rgb = color_temperature_to_rgb(mired_to_kelvin(shifted_temp))
            _LOGGER.debug("rgb color_temp: %s", rgb)

        rgbw = color_rgb_to_rgbw(rgb[0], rgb[1], rgb[2])
        rgbw = list(rgbw)
        rgbw.append(rgbw[3])

        _LOGGER.debug("RGBWW: %s", rgbw)

        calculated_color = []

        for color in rgbw:
            calculated_color.append(int(color * (self._brightness / 255)))

        _LOGGER.debug("RGBW after Brightness: %s", calculated_color)

        return calculated_color

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
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_RGB_COLOR | SUPPORT_BRIGHTNESS | SUPPORT_COLOR_TEMP

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._device.is_on()

    def turn_on(self, **kwargs):
        """Turn the light on"""
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        colortemp = kwargs.get(ATTR_COLOR_TEMP)

        if rgb:
            _LOGGER.debug("rgb: %s", rgb)
            self._rgb = rgb
            self._color_mode = 0

        elif brightness:
            _LOGGER.debug("brightness: %s", brightness)
            self._brightness = brightness

        elif colortemp:
            _LOGGER.debug("colortemp: %s", colortemp)
            self._color_temp = colortemp
            self._color_mode = 1

        c = self.get_rgbww_with_brightness(self._rgb)
        self._api.set_rgbww(self._device, c[0], c[1], c[2], c[3], c[4])

        if not self._device.is_on():
            self._api.turn_on(self._device)

    def turn_off(self, **kwargs):
        """Turn the light off"""
        self._api.turn_off(self._device)

    def update(self):
        """Update the state of this light."""
        self._api.update_state(self._device)
