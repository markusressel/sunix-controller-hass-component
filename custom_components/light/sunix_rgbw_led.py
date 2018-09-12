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
    ATTR_BRIGHTNESS, ATTR_HS_COLOR, ATTR_RGB_COLOR, ATTR_WHITE_VALUE, ATTR_EFFECT, ATTR_COLOR_TEMP, SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR, SUPPORT_COLOR_TEMP, SUPPORT_EFFECT, SUPPORT_WHITE_VALUE, Light)
from homeassistant.const import CONF_PLATFORM, CONF_NAME, CONF_HOST
import homeassistant.util.color as color_util

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = []
REQUIREMENTS = ['sunix-ledstrip-controller-client==2.0.3']

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


def retry(tries: int = 4, delay: int = 3, backoff: float = 2, logger=None):
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

    import sys

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                # noinspection PyBroadException
                try:
                    return f(*args, **kwargs)
                except:
                    e = sys.exc_info()[0]

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

    if DATA_SUNIX not in hass.data:
        hass.data[DATA_SUNIX] = []

    from sunix_ledstrip_controller_client import LEDStripControllerClient

    # read config
    devices = config.get(CONF_DEVICES, None)

    api_client = LEDStripControllerClient()

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
            device = create_device(api_client, host, port, name)

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


@retry(tries=5, delay=1, backoff=1)
def create_device(api_client, host, port, name):
    from sunix_ledstrip_controller_client.controller import Controller

    # _LOGGER.debug("ADDING DEVICE: %s:%s" % (host, port))

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
        self._name: str = name
        self._device: Controller = device

        self._rgb: tuple[int, int, int] = [255, 255, 255]  # initial color
        self._brightness: int = device.get_brightness()  # initial brightness
        self._color_temp: int = 154  # initial color temp (most blueish)
        self._effect: str = None
        # self._effect = self._device.get_effect()
        self._effect_speed: int = effect_speed
        self._max_brightness: int = max_brightness
        self._use_custom_white_value: bool = False
        self._custom_white_value: int = None
        self._color_mode: ColorMode = ColorMode.RGB  # rgb color
        self._color_offset: float = color_offset  # calibration offset
        self._color_factor: float = color_factor  # calibration color channel factor

    def get_rgbww_with_brightness(self, rgb) -> [int, int, int, int, int]:
        """
        Converts an RGB color (3ch) to a RGBWWCW color (5ch)
        and applies calibration offset, color factors, brightness
        and calculates the white value if there it is not provided
        :param rgb: 3 channel RGB color
        :return: 5 channel RGBWWCW color
        """

        if self._color_mode == ColorMode.COLOR_TEMPERATURE:  # color temperature
            rgb = color_util.color_temperature_to_rgb(color_util.color_temperature_mired_to_kelvin(self._color_temp))

            # apply color offset if any
            if self._color_offset:
                rgb = [
                    min(rgb[0] + self._color_offset[0], 255),
                    min(rgb[1] + self._color_offset[1], 255),
                    min(rgb[2] + self._color_offset[2], 255)
                ]

            if self._use_custom_white_value:
                rgbwwcw = [rgb[0], rgb[1], rgb[2], self._custom_white_value]
            else:
                rgbwwcw = list(color_util.color_rgb_to_rgbw(rgb[0], rgb[1], rgb[2]))

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
            if self._use_custom_white_value:
                rgbwwcw = [rgb[0], rgb[1], rgb[2], self._custom_white_value]
            else:
                rgbwwcw = list(color_util.color_rgb_to_rgbw(rgb[0], rgb[1], rgb[2]))
            rgbwwcw.append(rgbwwcw[3])  # duplicate warm_white value for cold_white

        # calculate color based on brightness since
        # the controller doesn't support brightness natively
        brightness_included = self.apply_brightness_to_color(rgbwwcw)

        return brightness_included

    def apply_brightness_to_color(self, color: ()) -> ():
        """
        Applies a brightness factor to a given color and returns the modified version.
        Note that this method is not idempotent if the brightness is a value other than 0 or 255
        :param color: the color to apply the brightness to
        :return: a color with the applied brightness
        """

        brightness_included = []
        for color_channel in color:
            brightness_included.append(int(
                color_channel *
                (self._brightness * (self._max_brightness / 255) / 255)
            ))

        return tuple(brightness_included)

    @retry(tries=5, delay=0, backoff=1)
    def check_args(self, turn_on, **kwargs):
        """
        Analyzes the arguments coming from hass and creates a new state from it

        :param turn_on: True, if this is called in "turn_on" method, false otherwise
        :param kwargs: Argumtns passed in from hass
        """
        from sunix_ledstrip_controller_client import FunctionId

        hs_color = kwargs.get(ATTR_HS_COLOR)
        rgb = color_util.color_hs_to_RGB(*hs_color) if hs_color else kwargs.get(ATTR_RGB_COLOR)
        white_value = kwargs.get(ATTR_WHITE_VALUE)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp = kwargs.get(ATTR_COLOR_TEMP)
        effect = kwargs.get(ATTR_EFFECT)

        # check for new custom white value
        if white_value is not None:
            self._use_custom_white_value = True
            self._custom_white_value = white_value

        # check for new brightness value
        if brightness is not None:
            _LOGGER.debug("Brightness Input: %s", brightness)
            self._brightness = brightness

        # check if the user selected a specific color on the palette
        if rgb is not None:
            _LOGGER.debug("RGB Color Input: %s", rgb)
            self._color_mode = ColorMode.RGB
            self._rgb = rgb

        # or if the user selected a color temperature
        elif color_temp is not None:
            _LOGGER.debug("Color Temperature Input: %s", color_temp)
            self._color_mode = ColorMode.COLOR_TEMPERATURE
            # disable custom white value in color temperature mode
            # (could allow both, include ww automatically or allow custom control of ww
            # even when selecting a color temperature)
            self._color_temp = color_temp
            self._use_custom_white_value = False

        # or if the user activated an effect
        # note: the white value is unaffected by the selection of an effect
        elif effect is not None:
            _LOGGER.debug("Effect Input: %s", effect)
            self._color_mode = ColorMode.EFFECT
            self._effect = effect

        c = self.get_rgbww_with_brightness(self._rgb)
        if self._color_mode != ColorMode.EFFECT:
            _LOGGER.debug("setting color %s on %s", c, self._name)
            self._device.set_rgbww(c[0], c[1], c[2], c[3], c[4])
        else:
            _LOGGER.debug("setting function %s on %s", self._effect, self._name)
            self._device.set_ww(c[3], c[4])
            self._device.set_function(FunctionId[self._effect], self._effect_speed)

        if turn_on:
            if not self.is_on:
                _LOGGER.debug("turning on %s", self._name)
                self._device.turn_on()
        else:
            if self.is_on:
                _LOGGER.debug("turning off %s", self._name)
                self._device.turn_off()

    @retry(tries=5, delay=0, backoff=1)
    def _update_controller_state(self):
        self._device.update_state()

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
        return color_util.color_RGB_to_xy(self._rgb[0], self._rgb[1], self._rgb[2])

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
    async def async_turn_on(self, **kwargs):
        """Turn the light on"""
        self.check_args(True, **kwargs)

    @asyncio.coroutine
    async def async_turn_off(self, **kwargs):
        """Turn the light off"""
        self.check_args(False, **kwargs)

    @retry(tries=5, delay=0, backoff=1)
    def update(self):
        """Update the state of this light."""
        self._update_controller_state()
