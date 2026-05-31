# PRD — HA GPS Tracker Prometheus Exporter

**Status:** Draft for implementation
**Date:** 2026-05-28
**Owner:** @cuihao
**Domain:** `ha_gps_tracker_exporter`
**Display name:** HA GPS Tracker Exporter

---

## 1. Problem

Home Assistant's official [`prometheus`](https://www.home-assistant.io/integrations/prometheus/)
integration exports entity **state** to Prometheus, but it does **not** export
entity **attributes**. For `device_tracker` entities (e.g. those created by
[hass-FindMy](https://github.com/malmeloo/hass-FindMy)), the GPS coordinates live
in the `latitude` / `longitude` attributes — so they never reach Prometheus and
cannot be graphed or mapped in Grafana.

Example state that contains the data we want but which is invisible to the
official exporter:

```json
{
  "entity_id": "device_tracker.findmy_corolla_key",
  "state": "home",
  "attributes": {
    "source_type": "gps",
    "latitude": 49.3435825,
    "longitude": -123.0599443,
    "gps_accuracy": 0,
    "friendly_name": "Corolla Key"
  },
  "last_reported": "2026-05-29T03:10:11.566676+00:00"
}
```

## 2. Goal

Ship a custom HA integration that runs **alongside** the official prometheus
integration and exposes a **second** Prometheus-format endpoint serving the GPS
coordinate metrics that the official exporter omits.

### Non-goals

- Not a bridge to a remote HA instance. Data is read from the **local** state
  machine.
- Does **not** create any HA entities (no `device_tracker`, no `sensor`). It only
  serves an HTTP scrape endpoint.
- Does **not** replace or patch the official prometheus integration.
- No long-term storage, no push gateway, no remote-write.

## 3. Users & use case

A self-hoster who already scrapes HA via `/api/prometheus` into Prometheus +
Grafana, and wants tracker coordinates available as metrics (e.g. to plot a
device's position over time, alert on distance from home, or render on a Grafana
geomap). They add one extra scrape job pointing at the new endpoint.

## 4. Decisions (locked)

| Area | Decision |
|---|---|
| Serving model | **New separate endpoint**, default `/api/gps_prometheus`. Added as a second scrape job in `prometheus.yml`. Does not touch `/api/prometheus`. |
| Metrics exported | `latitude`, `longitude`, `gps_accuracy`, `last_reported` (as a unix timestamp). |
| Entity scope | **All** `device_tracker` entities that currently have `latitude` + `longitude` attributes. No per-entity config. |
| Scrape model | **Pull-based** — metrics generated fresh from current state on each scrape. No polling interval. |
| Authentication | **Required bearer token** (`requires_auth = True`). Scraper supplies a long-lived access token. |
| Metric naming | **Configurable namespace**, default `homeassistant` (so metrics read `homeassistant_device_tracker_latitude_degrees`). |
| Config method | UI **config flow** (single step) + **options flow** to change the namespace later. |
| Library | `prometheus_client` (same dependency the official integration uses). |

## 5. Functional requirements

### 5.1 HTTP endpoint

- **FR-1** Register a single `HomeAssistantView` at `/api/gps_prometheus`
  (default; see Open Questions on configurability) on integration setup.
- **FR-2** The view requires authentication (`requires_auth = True`). Requests
  without a valid HA token receive `401`.
- **FR-3** `GET` returns HTTP `200` with Prometheus text exposition format,
  `Content-Type: text/plain; version=0.0.4; charset=utf-8`.
- **FR-4** The endpoint is registered exactly once. The integration is a
  **single-instance** config entry (`single_config_entry: true`) to avoid double
  registration.

### 5.2 Metric generation

On each scrape, enumerate `hass.states.async_all("device_tracker")` and, for each
state that has numeric `latitude` and `longitude` attributes, emit:

| Metric (with default namespace) | Type | Source | Notes |
|---|---|---|---|
| `homeassistant_device_tracker_latitude_degrees` | gauge | `attributes.latitude` | |
| `homeassistant_device_tracker_longitude_degrees` | gauge | `attributes.longitude` | |
| `homeassistant_device_tracker_gps_accuracy_meters` | gauge | `attributes.gps_accuracy` | omitted for a given entity if attribute missing |
| `homeassistant_device_tracker_last_reported_timestamp_seconds` | gauge | `state.last_reported` | converted to unix epoch **seconds** (Prometheus convention) |

- **FR-5** Every sample carries labels `entity` (entity_id) and `friendly_name`.
  (`source_type` may be added as a label — see Open Questions.)
- **FR-6** Entities lacking `latitude`/`longitude`, or whose values are
  non-numeric / `None`, are **skipped silently** (not exported as `NaN`).
- **FR-7** Label values are properly escaped (handled by `prometheus_client`).
- **FR-8** Metric name prefix uses the configured **namespace**
  (`<namespace>_device_tracker_<field>`). Default namespace `homeassistant`.

### 5.3 Configuration

- **FR-9** Config flow: a single setup step. Field(s):
  - `namespace` (string, default `homeassistant`).
  - Since auth is always required and the path is fixed by default, no other
    fields are mandatory.
- **FR-10** Options flow: allow editing `namespace` after setup; changes take
  effect on the next scrape (re-read from the config entry).
- **FR-11** Only one config entry allowed (`single_config_entry`).

## 6. Technical design

### 6.1 Project changes (from the `integration_blueprint` template)

The blueprint is coordinator/entity oriented and ships demo platforms; most of it
is removed.

```
custom_components/ha_gps_tracker_exporter/
  __init__.py        # async_setup_entry: register the HTTP view; async_unload_entry
  manifest.json      # domain, name, requirements: [prometheus_client], single_config_entry, dependencies: [http]
  const.py           # DOMAIN, DEFAULT_NAMESPACE, ENDPOINT_PATH, metric/label names
  config_flow.py     # single-step config flow + options flow (namespace)
  view.py            # GpsPrometheusView(HomeAssistantView) + metric collector
  translations/en.json
```

Files removed/not used from the template: `api.py`, `coordinator.py`, `data.py`,
`entity.py`, `sensor.py`, `binary_sensor.py`, `switch.py` (no entities/platforms
are created).

### 6.2 Endpoint implementation

- `view.py` defines `GpsPrometheusView(HomeAssistantView)` with
  `url = "/api/gps_prometheus"`, `name = "api:gps_prometheus"`,
  `requires_auth = True`.
- `async def get(self, request)`:
  1. Resolve `hass` and the current `namespace` from the config entry / `hass.data`.
  2. Build a fresh `prometheus_client.CollectorRegistry()` and register a
     stateless collector whose `collect()` yields `GaugeMetricFamily` objects
     (one per metric) populated from current `device_tracker` states.
  3. Return `web.Response(body=generate_latest(registry), content_type=...)`.
- Stateless/pull design means **no** event listeners, no coordinator, no stored
  metric state — each scrape reflects live values and trackers appearing/
  disappearing are handled automatically.

### 6.3 `manifest.json`

```json
{
  "domain": "ha_gps_tracker_exporter",
  "name": "HA GPS Tracker Exporter",
  "config_flow": true,
  "single_config_entry": true,
  "dependencies": ["http"],
  "requirements": ["prometheus_client==0.21.0"],
  "iot_class": "local_polling",
  "version": "0.1.0"
}
```
(Pin `prometheus_client` to a version compatible with the target HA release.)

### 6.4 `__init__.py`

- `async_setup_entry`: store namespace in `hass.data[DOMAIN]`, register the view
  via `hass.http.register_view(...)` (guarded so it registers once), add an
  options-update listener.
- `async_unload_entry`: HA does not support unregistering an HTTP view at
  runtime; on unload we leave the view registered but make it return empty/`404`
  if the entry is gone, **or** simply require a restart to fully remove. (See
  Open Questions.)

## 7. Prometheus / Grafana usage (docs to ship in README)

`prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "hass_gps"
    scrape_interval: 60s
    metrics_path: /api/gps_prometheus
    scheme: https            # or http for a local instance
    authorization:
      credentials: "<LONG_LIVED_ACCESS_TOKEN>"
    static_configs:
      - targets: ["homeassistant.local:8123"]
```

Example resulting metrics:

```
homeassistant_device_tracker_latitude_degrees{entity="device_tracker.findmy_corolla_key",friendly_name="Corolla Key"} 49.3435825
homeassistant_device_tracker_longitude_degrees{entity="device_tracker.findmy_corolla_key",friendly_name="Corolla Key"} -123.0599443
homeassistant_device_tracker_gps_accuracy_meters{entity="device_tracker.findmy_corolla_key",friendly_name="Corolla Key"} 0
homeassistant_device_tracker_last_reported_timestamp_seconds{entity="device_tracker.findmy_corolla_key",friendly_name="Corolla Key"} 1.748488211566676e+09
```

## 8. Edge cases

- Entity has `state` `unknown`/`unavailable` but still has last-known lat/long
  attributes → exported (we read attributes, not state).
- Entity missing `gps_accuracy` → that one metric is omitted for that entity;
  lat/long still exported.
- `last_reported` parse failure → omit the timestamp metric for that entity.
- No `device_tracker` entities at all → endpoint returns `200` with empty body.
- Two integration instances → prevented by `single_config_entry`.
- Friendly names with quotes/backslashes/unicode → escaped by `prometheus_client`.

## 9. Testing

- Unit: collector produces expected metric families/labels for a synthetic state
  set (including the skip/edge cases above), using
  `pytest-homeassistant-custom-component`.
- Integration: config flow happy path + single-instance abort; `GET` returns
  `401` without token and `200` with a valid token; namespace change via options
  reflected on next scrape.
- Manual: `scripts/develop` to launch HA, add a fake `device_tracker`, `curl`
  the endpoint with a bearer token, scrape from a local Prometheus.

## 10. Open questions

1. **Endpoint path configurability** — keep fixed at `/api/gps_prometheus`, or
   expose it in the config flow? (Default: fixed.)
2. **`source_type` label** — include it as a label, or keep labels to
   `entity` + `friendly_name` only? (Default: omit.)
3. **Other tracker domains** — only `device_tracker`, or also `person` /
   `zone` entities that carry coordinates? (Default: `device_tracker` only.)
4. **Unload behavior** — accept "restart required to fully remove the endpoint",
   or have the view self-disable when the entry is unloaded? (Default:
   self-disable / return 404 when no active entry.)
5. **`prometheus_client` version pin** — confirm against the user's HA version to
   avoid a conflicting dependency with the official integration.

## 11. Milestones

1. **M1 — Scaffold:** rename blueprint → `ha_gps_tracker_exporter`, strip unused
   platform files, update `manifest.json`/`const.py`.
2. **M2 — Endpoint:** `view.py` with the collector + view; register in
   `__init__.py`; verify with `curl`.
3. **M3 — Config:** single-step config flow + options flow (namespace);
   `single_config_entry`.
4. **M4 — Tests + docs:** unit/integration tests; rewrite `README.md` with the
   Prometheus/Grafana setup.
5. **M5 — Release:** version bump, HACS metadata, tag.
