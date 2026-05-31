"""Config and options flow for HA GPS Tracker Exporter."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_NAMESPACE, DEFAULT_NAMESPACE, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

# A Prometheus metric name must match [a-zA-Z_:][a-zA-Z0-9_:]*. The namespace is
# used as the leading segment of every metric name, so it must satisfy the same
# rule (and not end in a separator we already append).
_NAMESPACE_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")

_NAMESPACE_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
)


def _validate_namespace(raw: str, errors: dict[str, str]) -> str | None:
    """Return a cleaned namespace, or None and populate errors if invalid."""
    namespace = raw.strip().rstrip("_")
    if not namespace or not _NAMESPACE_RE.match(namespace):
        errors[CONF_NAMESPACE] = "invalid_namespace"
        return None
    return namespace


class GpsTrackerExporterFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> ConfigFlowResult:
        """Handle the user setup step."""
        # Belt and suspenders alongside single_config_entry in the manifest.
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            namespace = _validate_namespace(user_input[CONF_NAMESPACE], errors)
            if namespace is not None:
                return self.async_create_entry(
                    title="HA GPS Tracker Exporter",
                    data={CONF_NAMESPACE: namespace},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAMESPACE,
                        default=(user_input or {}).get(
                            CONF_NAMESPACE, DEFAULT_NAMESPACE
                        ),
                    ): _NAMESPACE_SELECTOR,
                },
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,  # noqa: ARG004
    ) -> GpsTrackerExporterOptionsFlow:
        """Return the options flow."""
        return GpsTrackerExporterOptionsFlow()


class GpsTrackerExporterOptionsFlow(OptionsFlow):
    """Allow changing the metric namespace after setup."""

    async def async_step_init(
        self,
        user_input: dict | None = None,
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            namespace = _validate_namespace(user_input[CONF_NAMESPACE], errors)
            if namespace is not None:
                return self.async_create_entry(data={CONF_NAMESPACE: namespace})

        current = self.config_entry.options.get(
            CONF_NAMESPACE,
            self.config_entry.data.get(CONF_NAMESPACE, DEFAULT_NAMESPACE),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAMESPACE, default=current): _NAMESPACE_SELECTOR,
                },
            ),
            errors=errors,
        )
