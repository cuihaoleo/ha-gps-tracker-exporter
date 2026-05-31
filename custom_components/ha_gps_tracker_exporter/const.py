"""Constants for ha_gps_tracker_exporter."""

from __future__ import annotations

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "ha_gps_tracker_exporter"

# HTTP endpoint that serves the Prometheus exposition.
ENDPOINT_PATH = "/api/gps_prometheus"
ENDPOINT_NAME = "api:gps_prometheus"

# Config / options keys.
CONF_NAMESPACE = "namespace"
DEFAULT_NAMESPACE = "homeassistant"

# Domain whose coordinate attributes we export.
TRACKER_DOMAIN = "device_tracker"

# Only trackers reporting this source_type are exported; router/bluetooth/ping
# trackers are excluded even when they carry latitude/longitude attributes.
SOURCE_TYPE_GPS = "gps"
