"""Puente de eventos hacia otro sistema (sección 21.2): eventos elegidos por MQTT o webhook firmado."""

from __future__ import annotations

from typing import Any

from ....alerts.channels.outbound import ChannelError, send_webhook, webhook_body
from ....api.stream import public_event
from ....models import AlertFired, AlertResolved, Event
from ...api import PluginBase, PluginContext


class Plugin(PluginBase):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)
        self.sent = 0
        self.failed = 0

    def _translate(self, ev: Event) -> tuple[str, dict[str, Any]] | None:
        if isinstance(ev, AlertFired | AlertResolved):
            return "alert", {**ev.alert, "is_public": ev.is_public}
        return public_event(ev, activity=False)

    async def on_event(self, event: Event) -> None:
        out = self._translate(event)
        if out is None:
            return
        name, data = out
        if name not in (self.ctx.settings.get("events") or []):
            return
        if self.ctx.settings.get("mode", "mqtt") == "mqtt":
            self.ctx.publish_mqtt(name, data)
            self.sent += 1
            return
        url = self.ctx.settings.get("webhook_url") or ""
        if not url:
            return
        try:
            await send_webhook(
                url,
                self.ctx.secrets.get("webhook_secret", ""),
                webhook_body(name, data),
                client=self.ctx.http,
                retries=2,
            )
            self.sent += 1
        except ChannelError as e:
            self.failed += 1
            self.ctx.log.warning("webhook del puente falló: %s", e)
