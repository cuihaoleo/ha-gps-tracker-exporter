"""
The HA GPS Tracker Exporter integration.

Serves device_tracker GPS coordinates (which Home Assistant's official Prometheus
integration omits, since they live in entity attributes) on a dedicated,
authenticated Prometheus scrape endpoint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import CONF_NAMESPACE, DEFAULT_NAMESPACE, DOMAIN
from .view import GpsPrometheusView

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

# hass.data flag recording that the (un-removable) HTTP view is registered.
_VIEW_REGISTERED = f"{DOMAIN}_view_registered"


def _resolve_namespace(entry: ConfigEntry) -> str:
    """Resolve the metric namespace, preferring options over initial data."""
    return entry.options.get(
        CONF_NAMESPACE,
        entry.data.get(CONF_NAMESPACE, DEFAULT_NAMESPACE),
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the exporter from a config entry."""
    # The endpoint reads this on every scrape; presence also signals "active".
    hass.data[DOMAIN] = _resolve_namespace(entry)

    # The view can only be registered once per HA run (aiohttp rejects duplicate
    # routes, and views cannot be unregistered at runtime).
    if not hass.data.get(_VIEW_REGISTERED):
        hass.http.register_view(GpsPrometheusView())
        hass.data[_VIEW_REGISTERED] = True

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply namespace changes from the options flow without a reload."""
    hass.data[DOMAIN] = _resolve_namespace(entry)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,  # noqa: ARG001
) -> bool:
    """Unload a config entry, disabling the endpoint."""
    # Dropping the namespace makes the (still-registered) view return 404.
    hass.data.pop(DOMAIN, None)
    return True
