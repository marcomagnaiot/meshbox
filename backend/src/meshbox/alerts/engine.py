"""Motor de alertas (sección 19).

Reglas de evento (palabra clave, nodo nuevo, nodo que vuelve) disparan una vez; reglas de
condición (umbral de telemetría, nodo caído, gateway caído, sistema) pasan a `firing` y se
resuelven solas cuando la condición desaparece. Cada regla respeta su tiempo de espera entre
avisos y notifica por sus canales. Las alertas nunca se transmiten por la radio (v1).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import orjson
from sqlalchemy import Connection, text

from ..models import (
    AlertFired,
    AlertResolved,
    ConnectorStatusChanged,
    MessageAdded,
    NodeUpserted,
    SystemStatus,
    TelemetryAdded,
    node_id,
    node_num,
)
from ..settings import put_setting
from .channels.outbound import ChannelError, send_telegram, send_webhook, webhook_body
from .channels.webpush import WebPush
from .rules import DEFAULT_RULES, PARAMS, KeywordParams, RuleIn, Scope

if TYPE_CHECKING:
    from ..app import Service

log = logging.getLogger(__name__)
CHANNELS_KEY = "alerts.channels"
DEFAULT_CHANNELS: dict[str, Any] = {
    "webpush": {"enabled": True},
    "telegram": {"enabled": False, "chat_id": ""},
    "webhooks": [],  # [{"id","url","enabled","events":["alert"]}]
    "mqtt": {"enabled": True},
}


@dataclass(slots=True)
class Rule:
    id: int
    name: str
    kind: str
    params: Any
    enabled: bool
    cooldown_s: int
    channels: list[str]
    severity: str
    is_public: bool
    matcher: Any = None


@dataclass(slots=True)
class Track:
    firing: bool = False
    since: float | None = None  # inicio de la condición (para duraciones mínimas)
    last_notified: float = 0.0
    event_id: int | None = None


@dataclass
class EngineStats:
    fired: int = 0
    resolved: int = 0
    notifications_ok: int = 0
    notifications_failed: int = 0
    by_channel: dict[str, int] = field(default_factory=dict)


class AlertEngine:
    def __init__(self, service: Service) -> None:
        self.service = service
        self.rules: list[Rule] = []
        self.tracks: dict[tuple[int, str], Track] = {}
        self.push = WebPush(service)
        self.stats = EngineStats()
        self._sub: Any = None
        self._tasks: list[asyncio.Task[None]] = []
        self._gateway_last: dict[str, float] = {}
        self._notify_tasks: set[asyncio.Task[Any]] = set()

    # ---------------------------------------------------------------- ciclo de vida

    async def start(self) -> None:
        await self.ensure_defaults()
        await self.reload()
        self._sub = self.service.bus.subscribe(
            "alerts",
            maxsize=5000,
            types=(
                MessageAdded,
                TelemetryAdded,
                NodeUpserted,
                ConnectorStatusChanged,
                SystemStatus,
            ),
        )
        self._tasks = [asyncio.create_task(self._consume()), asyncio.create_task(self._ticker())]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        if self._sub is not None:
            self._sub.close()
        if self._notify_tasks:
            await asyncio.wait(self._notify_tasks, timeout=5)

    async def ensure_defaults(self) -> None:
        def q(conn: Connection) -> None:
            if conn.execute(text("SELECT count(*) FROM alert_rules")).scalar_one():
                return
            now = time.time()
            for r in DEFAULT_RULES:
                conn.execute(
                    text(
                        "INSERT INTO alert_rules (name, kind, params, enabled, cooldown_s, channels, severity, "
                        "is_public, created_at, updated_at) VALUES (:n, :k, :p, 1, :c, :ch, :s, :pub, :t, :t)"
                    ),
                    {
                        "n": r["name"],
                        "k": r["kind"],
                        "p": orjson.dumps(r["params"]).decode(),
                        "c": r["cooldown_s"],
                        "ch": orjson.dumps(r["channels"]).decode(),
                        "s": r["severity"],
                        "pub": int(r["is_public"]),
                        "t": now,
                    },
                )

        await self.service.writer.run(q)

    async def reload(self) -> None:
        def q(conn: Connection) -> list[dict[str, Any]]:
            return [
                dict(r)
                for r in conn.execute(text("SELECT * FROM alert_rules ORDER BY id"))
                .mappings()
                .all()
            ]

        rules = []
        for row in await self.service.db.read(q):
            try:
                params = PARAMS[row["kind"]](**orjson.loads(row["params"]))
            except Exception as e:
                log.warning("regla %s con parámetros no válidos: %s", row["id"], e)
                continue
            rule = Rule(
                id=row["id"],
                name=row["name"],
                kind=row["kind"],
                params=params,
                enabled=bool(row["enabled"]),
                cooldown_s=row["cooldown_s"],
                channels=orjson.loads(row["channels"]),
                severity=row["severity"],
                is_public=bool(row["is_public"]),
            )
            if isinstance(params, KeywordParams):
                rule.matcher = params.matcher()
            rules.append(rule)
        self.rules = rules

    # ---------------------------------------------------------------- canales

    @property
    def channels_cfg(self) -> dict[str, Any]:
        raw = self.service.state.settings.get(CHANNELS_KEY)
        merged = {**DEFAULT_CHANNELS, **(raw if isinstance(raw, dict) else {})}
        return merged

    async def save_channels(self, cfg: dict[str, Any]) -> None:
        await put_setting(self.service.writer, self.service.state.settings, CHANNELS_KEY, cfg)

    # ---------------------------------------------------------------- consumo de eventos

    async def _consume(self) -> None:
        while True:
            ev = await self._sub.get()
            try:
                match ev:
                    case MessageAdded():
                        await self._on_message(ev)
                    case TelemetryAdded():
                        await self._on_telemetry(ev)
                    case NodeUpserted():
                        await self._on_node(ev)
                    case ConnectorStatusChanged():
                        if ev.status.get("last_packet_at"):
                            self._gateway_last[ev.status["id"]] = ev.status["last_packet_at"]
            except Exception:
                log.exception("error evaluando alertas")

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await self.evaluate_periodic(time.time())
            except Exception:
                log.exception("evaluación periódica de alertas falló")

    def _rules(self, kind: str) -> list[Rule]:
        return [r for r in self.rules if r.enabled and r.kind == kind]

    def _in_scope(self, scope: Scope, num: int) -> bool:
        rec = self.service.state.nodes.get(num)
        if rec is None or rec.hidden:
            return False
        match scope.mode:
            case "nodes":
                return node_id(num) in scope.nodes
            case "fixed":
                return bool(rec.is_fixed)
            case "infra":
                return rec.is_infra
            case _:
                return True

    async def _on_message(self, ev: MessageAdded) -> None:
        msg = ev.message
        for rule in self._rules("keyword"):
            params: KeywordParams = rule.params
            if params.channels and msg.get("channel") not in params.channels:
                continue
            if not ev.is_alert and not rule.matcher.search(msg.get("text") or ""):
                continue
            who = msg.get("from_name") or msg.get("from")
            prefix = "Alerta" if ev.is_alert else "SOS"
            await self.fire(
                rule,
                key=f"msg:{msg['pk']}",
                node=msg.get("from"),
                title=f"{prefix} desde {who}",
                body=(msg.get("text") or "")[:500],
                one_shot=True,
            )

    async def _on_telemetry(self, ev: TelemetryAdded) -> None:
        num = node_num(ev.node_id)
        now = ev.tel_ts
        for rule in self._rules("telemetry_threshold"):
            p = rule.params
            if p.kind != ev.kind or p.metric not in ev.values or not self._in_scope(p.scope, num):
                continue
            value = ev.values[p.metric]
            if value is None:
                continue
            track = self.tracks.setdefault((rule.id, ev.node_id), Track())
            if p.test(float(value)):
                track.since = track.since or now
                if not track.firing and now - track.since >= p.duration_s:
                    name = self.service.state.display_name(num) or ev.node_id
                    await self.fire(
                        rule,
                        key=ev.node_id,
                        node=ev.node_id,
                        title=f"{name}: {p.metric} {p.op} {p.value:g}",
                        body=f"Valor actual: {value}",
                    )
            else:
                track.since = None
                if track.firing:
                    await self.resolve(
                        rule, ev.node_id, f"{p.metric} volvió a la normalidad ({value})"
                    )

    async def _on_node(self, ev: NodeUpserted) -> None:
        nid = ev.node["id"]
        num = node_num(nid)
        if ev.is_new:
            for rule in self._rules("new_node"):
                name = ev.node.get("long_name") or ev.node.get("short_name") or nid
                await self.fire(
                    rule, key=nid, node=nid, title=f"Nodo nuevo: {name}", body=None, one_shot=True
                )
        # nodo que vuelve: resuelve "nodo caído" y dispara "nodo en línea"
        for rule in self._rules("node_offline"):
            track = self.tracks.get((rule.id, nid))
            if track and track.firing:
                await self.resolve(rule, nid, "El nodo volvió a escucharse")
                for online in self._rules("node_online"):
                    if self._in_scope(online.params.scope, num):
                        name = self.service.state.display_name(num) or nid
                        await self.fire(
                            online,
                            key=nid,
                            node=nid,
                            title=f"{name} volvió",
                            body=None,
                            one_shot=True,
                        )

    async def evaluate_periodic(self, now: float) -> None:
        state = self.service.state
        for rule in self._rules("node_offline"):
            limit = rule.params.hours * 3600
            for num, rec in state.nodes.items():
                if not self._in_scope(rule.params.scope, num):
                    continue
                track = self.tracks.setdefault((rule.id, rec.id), Track())
                if now - rec.last_heard > limit and not track.firing:
                    name = rec.long_name or rec.short_name or rec.id
                    hours = (now - rec.last_heard) / 3600
                    await self.fire(
                        rule,
                        key=rec.id,
                        node=rec.id,
                        title=f"{name} sin escucharse",
                        body=f"Sin paquetes hace {hours:.1f} h",
                    )
        for rule in self._rules("gateway_down"):
            limit = rule.params.minutes * 60
            for st in self.service.connectors.statuses():
                if not st.get("enabled") or (
                    rule.params.connector and st["id"] != rule.params.connector
                ):
                    continue
                if st["kind"] == "replay":
                    continue
                last = st.get("last_packet_at") or self.service.started_at
                track = self.tracks.setdefault((rule.id, st["id"]), Track())
                down = now - last > limit
                if down and not track.firing:
                    await self.fire(
                        rule,
                        key=st["id"],
                        node=None,
                        title=f"Conector {st['id']} sin paquetes",
                        body=f"Último paquete hace {(now - last) / 60:.0f} min (estado: {st['state']})",
                    )
                elif not down and track.firing:
                    await self.resolve(rule, st["id"], "Volvieron a llegar paquetes")
        snap = self.service.last_system
        for rule in self._rules("system"):
            if not snap:
                continue
            p = rule.params
            checks = {
                "cpu": (p.cpu_pct, snap.get("cpu_system"), "CPU %"),
                "ram": (p.ram_pct, snap.get("mem_percent"), "RAM %"),
                "temp": (p.temp_c, snap.get("temperature"), "temperatura °C"),
                "disk": (p.disk_pct, (snap.get("disk") or {}).get("percent"), "disco %"),
                "queue": (
                    p.writer_queue,
                    (snap.get("writer") or {}).get("queue"),
                    "cola de escritura",
                ),
                "rss": (p.rss_mb, snap.get("rss_mb"), "memoria del servicio MB"),
            }
            for key, (limit, value, label) in checks.items():
                if limit is None or value is None:
                    continue
                track = self.tracks.setdefault((rule.id, key), Track())
                if value >= limit and not track.firing:
                    await self.fire(
                        rule,
                        key=key,
                        node=None,
                        title=f"Sistema: {label} alto",
                        body=f"{value} (límite {limit})",
                    )
                elif value < limit * 0.95 and track.firing:
                    await self.resolve(rule, key, f"{label} normal ({value})")

    # ---------------------------------------------------------------- disparo y resolución

    def _public(
        self,
        event_id: int,
        rule: Rule,
        state: str,
        node: str | None,
        title: str,
        body: str | None,
        ts: float,
    ) -> dict[str, Any]:
        return {
            "id": event_id,
            "state": state,
            "severity": rule.severity,
            "kind": rule.kind,
            "node": node,
            "title": title,
            "body": body,
            "ts": ts,
        }

    async def _insert_event(
        self,
        rule: Rule | None,
        state: str,
        node: str | None,
        title: str,
        body: str | None,
        severity: str,
        is_public: bool,
    ) -> tuple[int, float]:
        event_id = self.service.writer.ids.next("alert_events")
        ts = time.time()
        row = {
            "id": event_id,
            "rule_id": rule.id if rule else None,
            "ts": ts,
            "state": state,
            "node_num": node_num(node) if node else None,
            "title": title[:200],
            "body": (body or "")[:1000] or None,
            "severity": severity,
            "is_public": int(is_public),
        }
        await self.service.writer.run(
            lambda c: c.execute(
                text(
                    "INSERT INTO alert_events (id, rule_id, ts, state, node_num, title, body, severity, is_public) "
                    "VALUES (:id, :rule_id, :ts, :state, :node_num, :title, :body, :severity, :is_public)"
                ),
                row,
            )
        )
        return event_id, ts

    async def fire(
        self,
        rule: Rule,
        *,
        key: str,
        node: str | None,
        title: str,
        body: str | None,
        one_shot: bool = False,
    ) -> int | None:
        now = time.time()
        track = self.tracks.setdefault((rule.id, key), Track())
        if not one_shot:
            track.firing = True
        cooled = now - track.last_notified >= rule.cooldown_s
        if one_shot:
            # Un mismo tipo de evento repetido (p. ej. varios SOS seguidos) respeta la espera por regla.
            group = self.tracks.setdefault((rule.id, f"group:{node}"), Track())
            cooled = now - group.last_notified >= rule.cooldown_s
            if cooled:
                group.last_notified = now
        event_id, ts = await self._insert_event(
            rule, "firing", node, title, body, rule.severity, rule.is_public
        )
        track.event_id = event_id
        alert = self._public(event_id, rule, "firing", node, title, body, ts)
        self.service.bus.publish(
            AlertFired(
                alert=alert,
                is_public=rule.is_public,
                rule_id=rule.id,
                channels=tuple(rule.channels),
            )
        )
        self.stats.fired += 1
        if cooled:
            track.last_notified = now
            self._spawn_notify(rule.channels, alert, rule.is_public)
        return event_id

    async def resolve(self, rule: Rule, key: str, body: str | None = None) -> None:
        track = self.tracks.get((rule.id, key))
        if track is None or not track.firing:
            return
        track.firing = False
        track.since = None
        node = key if key.startswith("!") else None
        title = f"Resuelto: {rule.name}"
        event_id, ts = await self._insert_event(
            rule, "resolved", node, title, body, rule.severity, rule.is_public
        )
        alert = self._public(event_id, rule, "resolved", node, title, body, ts)
        self.service.bus.publish(
            AlertResolved(
                alert=alert,
                is_public=rule.is_public,
                rule_id=rule.id,
                channels=tuple(rule.channels),
            )
        )
        self.stats.resolved += 1

    def _spawn_notify(self, channels: list[str], alert: dict[str, Any], is_public: bool) -> None:
        task = asyncio.create_task(self.notify(channels, alert, is_public))
        self._notify_tasks.add(task)
        task.add_done_callback(self._notify_tasks.discard)

    async def notify(
        self, channels: list[str], alert: dict[str, Any], is_public: bool
    ) -> dict[str, str | None]:
        cfg = self.channels_cfg
        results: dict[str, str | None] = {}

        async def run(name: str, coro: Any) -> None:
            try:
                await coro
                results[name] = None
                self.stats.notifications_ok += 1
            except Exception as e:
                results[name] = str(e)[:300]
                self.stats.notifications_failed += 1
            self.stats.by_channel[name] = self.stats.by_channel.get(name, 0) + 1

        jobs = []
        if "webpush" in channels and cfg["webpush"].get("enabled", True):
            jobs.append(run("webpush", self.push.send(alert, is_public)))
        if "telegram" in channels and cfg["telegram"].get("enabled"):
            text_msg = (
                f"[{alert['severity'].upper()}] {alert['title']}\n{alert.get('body') or ''}".strip()
            )
            jobs.append(
                run(
                    "telegram",
                    send_telegram(
                        self.service.secrets.data.telegram.bot_token,
                        cfg["telegram"].get("chat_id")
                        or self.service.secrets.data.telegram.chat_id,
                        text_msg,
                    ),
                )
            )
        if "webhook" in channels:
            for hook in cfg.get("webhooks") or []:
                if hook.get("enabled", True) and hook.get("url"):
                    secret = self.service.secrets.data.webhooks.get(hook.get("id", ""), "")
                    jobs.append(
                        run(
                            f"webhook:{hook.get('id')}",
                            send_webhook(hook["url"], secret, webhook_body("alert", alert)),
                        )
                    )
        if "mqtt" in channels and cfg["mqtt"].get("enabled", True):
            out = self.service.extensions.get("mqtt_out")
            if out is not None:
                out.publish_now("alert", {**alert, "is_public": is_public})
                results["mqtt"] = None
        await asyncio.gather(*jobs)
        now = time.time()
        rows = [
            {"a": alert["id"], "c": ch, "t": now, "ok": int(err is None), "e": err}
            for ch, err in results.items()
        ]
        if rows:
            await self.service.writer.run(
                lambda c: c.execute(
                    text(
                        "INSERT INTO notification_log (alert_event_id, channel, ts, ok, error) VALUES (:a, :c, :t, :ok, :e)"
                    ),
                    rows,
                )
            )
        return results

    async def test_rule(self, rule_id: int) -> dict[str, Any]:
        rule = next((r for r in self.rules if r.id == rule_id), None)
        if rule is None:
            raise KeyError(rule_id)
        alert = {
            "id": 0,
            "state": "firing",
            "severity": rule.severity,
            "kind": rule.kind,
            "node": None,
            "title": f"Prueba: {rule.name}",
            "body": "Aviso de prueba enviado desde el panel",
            "ts": time.time(),
        }
        results = await self.notify(rule.channels, alert, is_public=False)
        return {"results": results}

    async def test_channel(self, channel: str) -> str | None:
        alert = {
            "id": 0,
            "state": "firing",
            "severity": "info",
            "kind": "test",
            "node": None,
            "title": "Prueba de notificación",
            "body": f"Canal {channel} funcionando",
            "ts": time.time(),
        }
        try:
            if channel == "telegram":
                cfg = self.channels_cfg["telegram"]
                await send_telegram(
                    self.service.secrets.data.telegram.bot_token,
                    str(cfg.get("chat_id") or self.service.secrets.data.telegram.chat_id),
                    str(alert["title"]),
                )
            elif channel.startswith("webhook"):
                hook_id = channel.split(":", 1)[1] if ":" in channel else ""
                hooks = [
                    h
                    for h in self.channels_cfg.get("webhooks") or []
                    if not hook_id or h.get("id") == hook_id
                ]
                if not hooks:
                    raise ChannelError("no hay webhooks configurados")
                for h in hooks:
                    await send_webhook(
                        h["url"],
                        self.service.secrets.data.webhooks.get(h.get("id", ""), ""),
                        webhook_body("alert", alert),
                        retries=0,
                    )
            elif channel == "webpush":
                ok, fail = await self.push.send(alert, is_public=False)
                if ok == 0 and fail == 0:
                    raise ChannelError("no hay suscripciones de administración")
                if fail and not ok:
                    raise ChannelError(f"{fail} envíos fallaron")
            elif channel == "mqtt":
                out = self.service.extensions.get("mqtt_out")
                if out is None:
                    raise ChannelError("salida MQTT no disponible")
                out.publish_now("alert", alert)
            else:
                raise ChannelError("canal desconocido")
        except ChannelError as e:
            return str(e)
        return None

    def rule_from_in(self, body: RuleIn) -> dict[str, Any]:
        params = body.parsed_params()
        return {
            "name": body.name,
            "kind": body.kind,
            "params": orjson.dumps(params.model_dump()).decode(),
            "enabled": int(body.enabled),
            "cooldown_s": body.cooldown_s,
            "channels": orjson.dumps(body.channels).decode(),
            "severity": body.severity,
            "is_public": int(body.is_public),
        }


def make_engine(service: Service) -> AlertEngine:
    return AlertEngine(service)
