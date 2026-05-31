# HA GPS Tracker Exporter

A Home Assistant custom integration that exposes `device_tracker` **GPS
coordinates** to Prometheus.

## Why?

Home Assistant's official [`prometheus`](https://www.home-assistant.io/integrations/prometheus/)
integration exports entity **state**, but not entity **attributes**. For
`device_tracker` entities — such as those created by
[hass-FindMy](https://github.com/malmeloo/hass-FindMy) — the coordinates live in
the `latitude` / `longitude` attributes, so they never reach Prometheus and can't
be graphed in Grafana.

This integration runs **alongside** the official one and serves a second,
authenticated Prometheus endpoint that exports exactly those coordinate metrics.

It creates **no entities**. It only adds an HTTP scrape endpoint, generated fresh
from the current state on every scrape (pull-based, no polling interval).

## Installation

1. Copy `custom_components/ha_gps_tracker_exporter` into your Home Assistant
   `config/custom_components/` directory (or install via HACS as a custom
   repository).
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and add
   **HA GPS Tracker Exporter**.
4. Optionally set the **metric namespace** (default `homeassistant`).

## Exported metrics

For every `device_tracker` that currently has `latitude` and `longitude`
attributes (entities missing coordinates are skipped):

| Metric (default namespace) | Type | Source attribute |
| --- | --- | --- |
| `homeassistant_device_tracker_latitude_degrees` | gauge | `latitude` |
| `homeassistant_device_tracker_longitude_degrees` | gauge | `longitude` |
| `homeassistant_device_tracker_gps_accuracy_meters` | gauge | `gps_accuracy` (omitted if absent) |
| `homeassistant_device_tracker_last_reported_timestamp_seconds` | gauge | state `last_reported` (unix seconds) |

Each sample carries the labels `entity` and `friendly_name`.

Example output:

```text
# HELP homeassistant_device_tracker_latitude_degrees Latitude reported by the device tracker, in degrees.
# TYPE homeassistant_device_tracker_latitude_degrees gauge
homeassistant_device_tracker_latitude_degrees{entity="device_tracker.findmy_corolla_key",friendly_name="Corolla Key"} 49.3435825
homeassistant_device_tracker_longitude_degrees{entity="device_tracker.findmy_corolla_key",friendly_name="Corolla Key"} -123.0599443
homeassistant_device_tracker_gps_accuracy_meters{entity="device_tracker.findmy_corolla_key",friendly_name="Corolla Key"} 0.0
homeassistant_device_tracker_last_reported_timestamp_seconds{entity="device_tracker.findmy_corolla_key",friendly_name="Corolla Key"} 1748488211.566676
```

## Endpoint & authentication

- **Path:** `/api/gps_prometheus`
- **Auth:** requires a Home Assistant **long-lived access token** (create one
  under your profile). Pass it as a bearer token, exactly like the official
  prometheus integration.

## Prometheus configuration

Add a second scrape job pointing at this endpoint:

```yaml
scrape_configs:
  - job_name: "hass_gps"
    scrape_interval: 60s
    metrics_path: /api/gps_prometheus
    scheme: https            # use http for a plain local instance
    authorization:
      credentials: "YOUR_LONG_LIVED_ACCESS_TOKEN"
    static_configs:
      - targets: ["homeassistant.local:8123"]
```

## Grafana

With the coordinates in Prometheus you can, for example:

- Plot a tracker's position over time, or distance from home.
- Render current positions on a Grafana **Geomap** panel using the
  `_latitude_degrees` and `_longitude_degrees` metrics.

## Development

Run a local Home Assistant with this integration loaded:

```bash
scripts/develop
```

Then add the integration via the UI and scrape the endpoint:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8123/api/gps_prometheus
```

## Configuration reference

| Option | Default | Description |
| --- | --- | --- |
| Metric namespace | `homeassistant` | Prefix for every exported metric name. Editable later via the integration's options. |
