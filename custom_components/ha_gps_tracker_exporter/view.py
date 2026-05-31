"""HTTP view that serves device_tracker coordinates in Prometheus format."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .const import (
    DOMAIN,
    ENDPOINT_NAME,
    ENDPOINT_PATH,
    LOGGER,
    SOURCE_TYPE_GPS,
    TRACKER_DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _format_value(value: object) -> str | None:
    """Return a Prometheus-safe float repr, or None if not a finite number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    # repr() yields the shortest string that round-trips, preserving the full
    # precision of GPS coordinates.
    return repr(number)


def _escape_label(value: str) -> str:
    """Escape a label value per the Prometheus exposition format."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_labels(labels: dict[str, str]) -> str:
    return ",".join(f'{key}="{_escape_label(str(val))}"' for key, val in labels.items())


def render_metrics(hass: HomeAssistant, namespace: str) -> str:
    """Render the current GPS device_tracker coordinates as Prometheus text."""
    prefix = f"{namespace}_device_tracker_"

    latitude: list[tuple[dict[str, str], str]] = []
    longitude: list[tuple[dict[str, str], str]] = []
    accuracy: list[tuple[dict[str, str], str]] = []
    last_reported: list[tuple[dict[str, str], str]] = []

    for state in hass.states.async_all(TRACKER_DOMAIN):
        attrs = state.attributes
        # Only export GPS-based trackers. Router/bluetooth/ping trackers may
        # still carry latitude/longitude (e.g. the home-zone position), so
        # filtering on coordinates alone is not enough to exclude them.
        if attrs.get("source_type") != SOURCE_TYPE_GPS:
            continue

        lat = _format_value(attrs.get("latitude"))
        lon = _format_value(attrs.get("longitude"))
        # Coordinates are the whole point; skip entities that lack them.
        if lat is None or lon is None:
            continue

        labels = {"entity": state.entity_id, "friendly_name": state.name}
        latitude.append((labels, lat))
        longitude.append((labels, lon))

        acc = _format_value(attrs.get("gps_accuracy"))
        if acc is not None:
            accuracy.append((labels, acc))

        if state.last_reported is not None:
            last_reported.append((labels, repr(state.last_reported.timestamp())))

    families = (
        (
            f"{prefix}latitude_degrees",
            "Latitude reported by the device tracker, in degrees.",
            latitude,
        ),
        (
            f"{prefix}longitude_degrees",
            "Longitude reported by the device tracker, in degrees.",
            longitude,
        ),
        (
            f"{prefix}gps_accuracy_meters",
            "Reported GPS accuracy radius, in meters.",
            accuracy,
        ),
        (
            f"{prefix}last_reported_timestamp_seconds",
            "Unix timestamp of when the tracker state was last reported.",
            last_reported,
        ),
    )

    lines: list[str] = []
    for name, help_text, samples in families:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        for labels, value in samples:
            lines.append(f"{name}{{{_format_labels(labels)}}} {value}")

    return "\n".join(lines) + "\n"


class GpsPrometheusView(HomeAssistantView):
    """Serve device_tracker coordinates for Prometheus to scrape."""

    url = ENDPOINT_PATH
    name = ENDPOINT_NAME
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return the Prometheus exposition for all device_trackers."""
        hass: HomeAssistant = request.app["hass"]
        namespace = hass.data.get(DOMAIN)

        # The integration registers this view once; it can't be unregistered at
        # runtime. When the config entry is unloaded we drop the namespace, so a
        # missing namespace means "no active entry" -> behave as if disabled.
        if namespace is None:
            return web.Response(status=404)

        try:
            body = render_metrics(hass, namespace)
        except Exception:  # noqa: BLE001 - never 500 a scrape endpoint
            LOGGER.exception("Failed to render GPS tracker metrics")
            return web.Response(status=500)

        return web.Response(body=body.encode("utf-8"), content_type="text/plain")
