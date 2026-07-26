"""Sensor for Midea Lan."""

import time
from datetime import timedelta
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_SENSORS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import StateType
from midealocal.device import MideaDevice

from .const import DEVICES, DOMAIN
from .midea_devices import MIDEA_DEVICES
from .midea_entity import MideaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for device."""
    device_id = config_entry.data.get(CONF_DEVICE_ID)
    device = hass.data[DOMAIN][DEVICES].get(device_id)
    extra_sensors = config_entry.options.get(CONF_SENSORS, [])
    sensors = []
    for entity_key, config in cast(
        "dict",
        MIDEA_DEVICES[device.device_type]["entities"],
    ).items():
        if config["type"] == Platform.SENSOR and entity_key in extra_sensors:
            sensor = MideaSensor(device, entity_key)
            sensors.append(sensor)
    async_add_entities(sensors)


class MideaSensor(MideaEntity, SensorEntity):
    """Represent a Midea sensor."""

    def __init__(self, device: MideaDevice, entity_key: str) -> None:
        """Initialize Midea sensor."""
        super().__init__(device, entity_key)
        # Timer configuration: "down" for countdown, "up" for countup
        self._timer = self._config.get("timer")
        self._timer_base_value: int | None = None
        self._timer_last_update: float | None = None
        self._timer_listener = None

    @property
    def native_value(self) -> StateType:
        """Return entity value."""
        value = self._device.get_attribute(self._entity_key)
        # If options mapping exists, return mapped key instead of raw value
        options = self._config.get("options")
        if options is not None and isinstance(value, int) and value in options:
            return cast("StateType", options[value])

        # Timer mode: calculate elapsed time
        if self._timer and isinstance(value, int):
            now = time.time()
            if self._timer_last_update is not None:
                elapsed = int(now - self._timer_last_update)
                if self._timer == "down":
                    # Countdown: value decreases by elapsed seconds
                    return cast("StateType", max(0, value - elapsed))
                if self._timer == "up":
                    # Countup: value increases by elapsed seconds
                    return cast("StateType", value + elapsed)
            return cast("StateType", value)

        return cast("StateType", value)

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return device class."""
        return cast("SensorDeviceClass", self._config.get("device_class"))

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return state state."""
        return cast("SensorStateClass | None", self._config.get("state_class"))

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurement."""
        return cast("str | None", self._config.get("unit"))

    @property
    def capability_attributes(self) -> dict[str, Any] | None:
        """Return capabilities."""
        return {"state_class": self.state_class} if self.state_class else {}

    async def async_added_to_hass(self) -> None:
        """Subscribe to device updates and start timer tracking."""
        await super().async_added_to_hass()
        # Start timer tracking if configured
        if self._timer:
            value = self._device.get_attribute(self._entity_key)
            if isinstance(value, int):
                self._timer_base_value = value
                self._timer_last_update = time.time()
            # Register 1-second interval update
            self._timer_listener = async_track_time_interval(
                self.hass,
                self._async_timer_update,
                timedelta(seconds=1),
            )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from device updates and stop timer tracking."""
        await super().async_will_remove_from_hass()
        if self._timer_listener:
            self._timer_listener()
            self._timer_listener = None

    @callback
    def update_state(self, status: Any) -> None:  # noqa: ANN401
        """Update entity state."""
        if self._timer and self._entity_key in status:
            value = self._device.get_attribute(self._entity_key)
            if isinstance(value, int):
                self._timer_base_value = value
                self._timer_last_update = time.time()
        super().update_state(status)

    @callback
    def _async_timer_update(self, _now: Any) -> None:  # noqa: ANN401
        """Update timer state every second."""
        self.schedule_update_ha_state()
