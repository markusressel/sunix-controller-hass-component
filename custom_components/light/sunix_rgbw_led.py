"""
Support for the Sunix RGB / RGBWWCW WiFi LED Strip controller

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/light.sunix/
"""

import asyncio
import logging
from builtins import float
from enum import Enum

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_WHITE_VALUE, ATTR_EFFECT, ATTR_COLOR_TEMP, SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR, SUPPORT_COLOR_TEMP, SUPPORT_EFFECT, SUPPORT_WHITE_VALUE, Light)
from homeassistant.const import CONF_PLATFORM, CONF_NAME, CONF_HOST
from homeassistant.util.color import (
    color_temperature_mired_to_kelvin as mired_to_kelvin,
    color_temperature_to_rgb,
    color_rgb_to_rgbw,
    color_RGB_to_xy)

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = []
REQUIREMENTS = ['sunix-ledstrip-controller-client==2.0.2']

CONF_DEVICES = 'devices'
CONF_PORT = 'port'
CONF_CALIBRATION_OFFSET = 'calibration_offset'
CONF_CALIBRATION_FACTOR = 'calibration_factor'
CONF_EFFECT_SPEED = 'effect_speed'
CONF_MAX_BRIGHTNESS = 'max_brightness'

DEFAULT_EFFECT_SPEED = 250
DEFAULT_MAX_BRIGHTNESS = 255

DATA_SUNIX = 'sunix_rgbw_led'

# define configuration parameters
PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_PLATFORM): 'sunix_rgbw_led',
    vol.Required(CONF_DEVICES): cv.match_all

    #        vol.Optional(CONF_PORT, default=None):
    #        vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    #    vol.Optional(CONF_NAME, default=DEVICE_DEFAULT_NAME): cv.string,
    #    vol.Optional(CONF_CALIBRATION_OFFSET, default=None):
    #        vol.All({cv.string: vol.All(vol.Coerce(int), vol.Range(min=-255, max=255))}),
    #    vol.Optional(CONF_EFFECT_SPEED, default=DEFAULT_EFFECT_SPEED):
    #        vol.All(vol.Coerce(int), vol.Range(min=1, max=255))
    #    ),
}, extra=vol.ALLOW_EXTRA)

# retry decorator

import time
from functools import wraps


def retry(exceptions: (), tries: int = 4, delay: int = 3, backoff: float = 2, logger=None):
    """
    Retry calling the decorated function using an exponential backoff.

    Args:
        exceptions: The exception to check. may be a tuple of
            exceptions to check.
        tries: Number of times to try (not retry) before giving up.
        delay: Initial delay between retries in seconds.
        backoff: Backoff multiplier (e.g. value of 2 will double the delay
            each retry).
        logger: Logger to use. If None, print.
    """

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    msg = '{}, Retrying in {} seconds...'.format(e, mdelay)
                    if _LOGGER:
                        _LOGGER.warning(msg)
                    else:
                        print(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


@asyncio.coroutine
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the light controller"""

    # _LOGGER.error("ASYNC_SETUP_PLATFORM")

    if DATA_SUNIX not in hass.data:
        hass.data[DATA_SUNIX] = []

    from sunix_ledstrip_controller_client import LEDStripControllerClient

    # read config
    devices = config.get(CONF_DEVICES, None)

    devices_to_add = []
    for name, entry in devices.items():
        if CONF_NAME in entry:
            name = entry[CONF_NAME]

        host = entry[CONF_HOST]

        port = None
        if CONF_PORT in entry:
            port = entry[CONF_PORT]

        color_offset = None
        if CONF_CALIBRATION_OFFSET in entry:
            color_offset = entry[CONF_CALIBRATION_OFFSET]
            color_offset = [
                color_offset["red"],
                color_offset["green"],
                color_offset["blue"],
                color_offset["warmwhite"],
                color_offset["coldwhite"]
            ]

        color_factor = None
        if CONF_CALIBRATION_FACTOR in entry:
            color_factor = entry[CONF_CALIBRATION_FACTOR]
            color_factor = [
                color_factor["red"],
                color_factor["green"],
                color_factor["blue"],
                color_factor["warmwhite"],
                color_factor["coldwhite"]
            ]

        effect_speed = DEFAULT_EFFECT_SPEED
        if CONF_EFFECT_SPEED in entry:
            effect_speed = entry[CONF_EFFECT_SPEED]

        max_brightness = DEFAULT_MAX_BRIGHTNESS
        if CONF_MAX_BRIGHTNESS in entry:
            max_brightness = entry[CONF_MAX_BRIGHTNESS]

        try:
            api_client = LEDStripControllerClient()

            device = createDevice(api_client, host, port, name)

            # skip this device if it's already configured
            if device.get_hardware_id() in [x.unique_id for x in hass.data[DATA_SUNIX]]:
                continue

            # add to the list of devices to add
            devices_to_add.append(
                SunixController(device, name, color_offset, color_factor, effect_speed, max_brightness))

        except Exception as e:
            _LOGGER.error("Couldn't add device: %s:%s - %s" % (host, port, str(e)))
            _LOGGER.error(e)

    async_add_entities(devices_to_add, True)
    # remember in config
    hass.data[DATA_SUNIX].append(devices)

    return True


@retry(Exception, tries=5, delay=1, backoff=1)
def createDevice(api_client, host, port, name):
    from sunix_ledstrip_controller_client.controller import Controller

    # _LOGGER.error("ADDING DEVICE: %s:%s" % (host, port))

    # TODO: use auto discovery to get the real hardware id
    # use fake id for now
    hardware_id = name
    # Create api client and device
    device = Controller(api_client, host, port, hardware_id, None)
    return device


class ColorMode(Enum):
    RGB = 0
    COLOR_TEMPERATURE = 1
    EFFECT = 2


class SunixController(Light):
    """Representation of a Sunix controller device."""

    from sunix_ledstrip_controller_client.controller import Controller

    def __init__(self, device: Controller, name: str, color_offset: [int, int, int, int, int],
                 color_factor: [float, float, float, float, float],
                 effect_speed: int, max_brightness: int):
        self._name = name
        self._device = device

        self._rgb = [255, 255, 255]  # initial color
        self._brightness = device.get_brightness()  # initial brightness
        self._color_temp = 154  # initial color temp (most blueish)
        self._effect = None
        # self._effect = self._device.get_effect()
        self._effect_speed = effect_speed
        self._max_brightness = max_brightness
        self._color_mode = ColorMode.RGB  # rgb color
        self._color_offset = color_offset  # calibration offset
        self._color_factor = color_factor  # calibration color channel factor

        # _LOGGER.error("INIT Name: %s, Host: %s, Port: %s (
        #    self._name, self._device.get_host(), self._device.get_port()))

    def get_rgbww_with_brightness(self, rgb) -> [int, int, int, int, int]:
        """
        Converts an RGB color (3ch) to a RGBWWCW color (5ch)
        and applies calibration offset, color factors and brightness
        :param rgb: 3 channel RGB color
        :return: 5 channel RGBWWCW color
        """

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

            rgbwwcw = list(color_rgb_to_rgbw(rgb[0], rgb[1], rgb[2]))
            rgbwwcw.append(rgbwwcw[3])  # duplicate warm_white value for cold_white

            # apply color factors
            if self._color_factor:
                color_factors_included = []
                for idx, color in enumerate(rgbwwcw):
                    color_factors_included.append(int(
                        color * self._color_factor[idx]
                    ))

                rgbwwcw = color_factors_included

        else:
            rgbwwcw = list(color_rgb_to_rgbw(rgb[0], rgb[1], rgb[2]))
            rgbwwcw.append(rgbwwcw[3])  # duplicate warm_white value for cold_white

        # _LOGGER.debug("RGBWW: %s", rgbwwcw)

        # calculate color based on brightness since
        # the controller doesn't support brightness natively

        brightness_included = []
        for color in rgbwwcw:
            brightness_included.append(int(
                color *
                (self._brightness * (self._max_brightness / 255) / 255)
            ))

        _LOGGER.debug("RGBWWCW after Brightness: %s", brightness_included)

        return brightness_included

    def check_args(self, turn_on, **kwargs):
        from sunix_ledstrip_controller_client import FunctionId

        rgb = kwargs.get(ATTR_RGB_COLOR)
        white_value = kwargs.get(ATTR_WHITE_VALUE)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp = kwargs.get(ATTR_COLOR_TEMP)
        effect = kwargs.get(ATTR_EFFECT)

        if rgb:
            _LOGGER.debug("rgb: %s", rgb)
            self._rgb = rgb
            self._color_mode = ColorMode.RGB
        elif color_temp:
            _LOGGER.error("color_temp: %s", color_temp)
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
            self._device.set_rgbww(c[0], c[1], c[2], c[3], c[4])
        else:
            _LOGGER.debug("setting function %s on %s", self._effect, self._name)
            self._device.set_function(FunctionId[self._effect], self._effect_speed)

        if turn_on:
            if not self.is_on:
                _LOGGER.debug("turning on %s", self._name)
                self._device.turn_on()
        else:
            if self.is_on:
                _LOGGER.debug("turning off %s", self._name)
                self._device.turn_off()

    def try_multiple_times(self, command: callable, max_tries: int = 3):
        import time

        success = False
        try_count = 0
        while (not success) and (try_count < max_tries):
            try:
                command()
                success = True
            except Exception as e:
                _LOGGER.warning("Error executing command: %s", e)
                time.sleep(0.5)
                try_count += 1

        if not success:
            _LOGGER.error("Couldn't execute command even after %s retries", max_tries)

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

        from sunix_ledstrip_controller_client import FunctionId

        for effect in list(FunctionId):
            effect_list.append(effect.name)

        return effect_list

    @property
    def effect(self) -> str:
        """Return the current effect."""
        return self._effect

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_COLOR | SUPPORT_BRIGHTNESS | SUPPORT_COLOR_TEMP | SUPPORT_EFFECT | SUPPORT_WHITE_VALUE

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._device.is_on()

    @asyncio.coroutine
    @retry(Exception, tries=5, delay=1, backoff=1)
    async def async_turn_on(self, **kwargs):
        """Turn the light on"""
        await self.check_args(True, **kwargs)

    @asyncio.coroutine
    @retry(Exception, tries=5, delay=1, backoff=1)
    async def async_turn_off(self, **kwargs):
        """Turn the light off"""
        await self.check_args(False, **kwargs)

    @retry(Exception, tries=5, delay=1, backoff=1)
    def update(self):
        """Update the state of this light."""
        self._device.update_state()
