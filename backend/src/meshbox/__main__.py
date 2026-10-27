"""Línea de comandos: meshbox run|dev|record|replay|inspect|migrate|user|backup|bootstrap|simulate|health."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__

log = logging.getLogger("meshbox")


def default_config_path() -> Path | None:
    env = os.environ.get("MESHBOX_CONFIG")
    if env:
        return Path(env)
    for candidate in (Path("/etc/meshbox/config.toml"), Path("dev/config.toml")):
        if candidate.exists():
            return candidate
    return None


def run_async(coro: Any) -> Any:
    """En Windows aiomqtt necesita SelectorEventLoop; en Linux, uvloop si está."""
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)
    try:
        import uvloop

        return asyncio.run(coro, loop_factory=uvloop.new_event_loop)
    except ImportError:
        return asyncio.run(coro)


def _load(args: argparse.Namespace) -> tuple[Any, Path | None]:
    from .config import load_config

    path = Path(args.config) if getattr(args, "config", None) else default_config_path()
    return load_config(path), path


def _setup_logging(cfg: Any, json_default: bool | None = None) -> None:
    from .config import SecretStore
    from .system.logs import setup_logging

    def secrets_provider() -> list[str]:
        try:
            return SecretStore(cfg.paths.secrets).values()
        except Exception:
            return []

    json_output = cfg.logging.json_output if json_default is None else json_default
    setup_logging(cfg.logging.level, json_output, secrets_provider)


# --------------------------------------------------------------------------- comandos


def cmd_run(args: argparse.Namespace) -> int:
    cfg, path = _load(args)
    dev = args.cmd == "dev"
    if dev:
        cfg.logging.json_output = False
        if cfg.system.privd == "auto":
            cfg.system.privd = "fake"
    _setup_logging(cfg)
    from .app import serve

    return int(run_async(serve(cfg, path, dev=dev)) or 0)


def cmd_migrate(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    _setup_logging(cfg, json_default=False)
    from .store.migrate import migrate

    result = migrate(cfg.paths.db, cfg.paths.backups, __version__, cfg.paths.tmp)
    print(f"migraciones: {result}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    _setup_logging(cfg, json_default=False)
    ccfg = cfg.connector(args.connector)
    if ccfg is None:
        print(f"no existe el conector {args.connector!r} en la configuración", file=sys.stderr)
        return 2

    async def main() -> int:
        from .bus import EventBus
        from .config import SecretStore
        from .connectors.manager import ConnectorManager
        from .connectors.replay import Recorder

        out = Path(args.out) if args.out else cfg.paths.recordings
        recorder = Recorder(out)
        bus = EventBus()
        mgr = ConnectorManager(cfg, SecretStore(cfg.paths.secrets), bus, recorder)
        ccfg.enabled = True
        await mgr.start_one(ccfg)
        mgr._consumer = asyncio.create_task(mgr._consume())
        print(f"grabando {ccfg.id} en {recorder.path} (Ctrl+C para terminar)")
        try:
            done = asyncio.Event()  # nadie lo activa: se espera la duración o Ctrl+C
            await asyncio.wait_for(done.wait(), args.duration if args.duration > 0 else None)
        except (TimeoutError, asyncio.CancelledError):
            pass
        finally:
            await mgr.stop()
            recorder.close()
            print(f"{recorder.count} paquetes grabados")
        return 0

    try:
        return int(run_async(main()))
    except KeyboardInterrupt:
        return 0


def _inspect_keys(cfg: Any, extra: list[str]) -> list[Any]:
    from .config import SecretStore
    from .connectors.serial import PRESET_NAMES
    from .pipeline.crypto import ChannelKey, decode_psk

    keys = [ChannelKey.from_psk(name, bytes([1])) for name in PRESET_NAMES.values()]
    try:
        secrets = SecretStore(cfg.paths.secrets)
        for name, psk in secrets.data.channels.items():
            keys.append(ChannelKey.from_psk(name, decode_psk(psk)))
    except Exception:  # noqa: S110
        pass
    for item in extra:
        name, _, b64 = item.partition("=")
        keys.append(ChannelKey.from_psk(name, decode_psk(b64)))
    return keys


def cmd_inspect(args: argparse.Namespace) -> int:
    import orjson

    from .connectors.replay import read_recording, record_to_packet
    from .models import BROADCAST, node_id
    from .pipeline.crypto import try_decrypt
    from .pipeline.decode import decode_data, decoded_to_json

    cfg, _ = _load(args)
    keys = _inspect_keys(cfg, args.key or [])
    n = 0
    for rec in read_recording(Path(args.file)):
        pkt = record_to_packet(rec)
        n += 1
        if args.limit and n > args.limit:
            break
        if pkt is None:
            print(f"#{n} paquete ilegible")
            continue
        which = pkt.WhichOneof("payload_variant")
        data, channel = None, rec.get("channel_id")
        if which == "decoded":
            data = pkt.decoded
        elif which == "encrypted":
            res = try_decrypt(pkt, keys)
            if res is not None:
                data, ck = res
                channel = f"{ck.name} (descifrado)"
        content: Any = None
        port = "CIFRADO" if pkt.pki_encrypted or (which == "encrypted" and data is None) else "?"
        if data is not None:
            dec = decode_data(data)
            port = dec.portnum
            content = decoded_to_json(dec) if dec.ok else {"error": dec.error}
        hops = pkt.hop_start - pkt.hop_limit if pkt.hop_start else None
        item = {
            "n": n,
            "rx_time": rec.get("rx_time"),
            "gateway": rec.get("gateway_id"),
            "channel": channel,
            "from": node_id(getattr(pkt, "from")),
            "to": "^all" if pkt.to == BROADCAST else node_id(pkt.to),
            "id": pkt.id,
            "portnum": port,
            "hops": hops,
            "snr": pkt.rx_snr,
            "rssi": pkt.rx_rssi,
            "via_mqtt": pkt.via_mqtt,
            "pki": pkt.pki_encrypted,
            "content": content,
        }
        if args.json:
            print(orjson.dumps(item).decode())
        else:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["rx_time"] or 0))
            text = orjson.dumps(content).decode() if content is not None else ""
            print(
                f"{ts} {item['gateway'] or '-':10} {item['from']} -> {item['to']:10} "
                f"{port:20} hops={hops} snr={pkt.rx_snr} {channel or ''!s:12} {text[:160]}"
            )
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    """Alimenta el pipeline con una grabación (sin servidores salvo --serve)."""
    from .config import ReplayConnectorCfg

    cfg, path = _load(args)
    speed = 0.0 if args.speed == "max" else float(args.speed)
    cfg.connectors = [
        ReplayConnectorCfg(
            id="replay", file=Path(args.file).resolve(), speed=speed, rebase_time=not args.keep_time
        )
    ]
    if args.db:
        cfg.paths.db = Path(args.db)
    _setup_logging(cfg, json_default=False)
    from .app import replay_only, serve

    if args.serve:
        if cfg.system.privd == "auto" and sys.platform == "win32":
            cfg.system.privd = "fake"
        return int(run_async(serve(cfg, path, dev=True)) or 0)
    return int(run_async(replay_only(cfg, path)) or 0)


def cmd_backup(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    _setup_logging(cfg, json_default=False)
    from .store import backup

    if args.action == "create":
        info = backup.create_backup(cfg.paths.db, cfg.paths.backups, args.suffix, cfg.paths.tmp)
        print(f"respaldo: {cfg.paths.backups / info.name} ({info.size} bytes)")
    elif args.action == "list":
        for b in backup.list_backups(cfg.paths.backups):
            print(f"{b.name}\t{b.size}\t{time.strftime('%Y-%m-%d %H:%M', time.localtime(b.mtime))}")
    elif args.action == "restore":
        if not args.file:
            print("falta --file", file=sys.stderr)
            return 2
        f = Path(args.file)
        if not f.is_absolute() and not f.exists():
            f = cfg.paths.backups / f
        backup.restore_backup(f, cfg.paths.db, cfg.paths.tmp)
        print(f"base restaurada desde {f}")
    return 0


def _read_password(args: argparse.Namespace, prompt: str = "Contraseña: ") -> str:
    if getattr(args, "password_stdin", False):
        return sys.stdin.readline().rstrip("\r\n")
    p1 = getpass.getpass(prompt)
    p2 = getpass.getpass("Repetir: ")
    if p1 != p2:
        raise SystemExit("las contraseñas no coinciden")
    return p1


def cmd_user(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    _setup_logging(cfg, json_default=False)
    from .auth.users import cli_user

    password = _read_password(args) if args.action in ("create", "passwd") else None
    return run_async(cli_user(cfg, args.action, args.username, args.role, password))  # type: ignore[no-any-return]


def cmd_channel(args: argparse.Namespace) -> int:
    cfg, _ = _load(args)
    _setup_logging(cfg, json_default=False)
    from .channels_cli import channel_cli

    return int(run_async(channel_cli(cfg, args.action, args.name, args.key, args.public)))


def cmd_bootstrap(args: argparse.Namespace) -> int:
    from .bootstrap import bootstrap

    path = Path(args.config) if args.config else Path("/etc/meshbox/config.toml")
    result = bootstrap(
        path,
        mode=args.mode,
        site_slug=args.site_slug,
        mqtt_root=args.mqtt_root,
        secrets_path=Path(args.secrets) if args.secrets else None,
    )
    if args.json:
        import orjson

        print(orjson.dumps(result).decode())
    else:
        for k, v in result.items():
            print(f"{k}: {v}")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    from .devtools import sim

    if args.action == "generate":
        n = sim.generate(Path(args.out), hours=args.hours, seed=args.seed)
        print(f"{n} registros en {args.out}")
        return 0
    password = os.environ.get(args.password_env) if args.password_env else None
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    sent = run_async(
        sim.publish(
            Path(args.file),
            host=args.host,
            port=args.port,
            root=args.root,
            username=args.username,
            password=password,
            speed=args.speed,
            limit=args.limit,
        )
    )
    print(f"{sent} envelopes publicados")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    import httpx

    deadline = time.time() + args.timeout
    while True:
        try:
            r = httpx.get(args.url, timeout=3)
            if r.status_code == 200 and r.json().get("status") == "ok":
                print(r.text)
                return 0
        except Exception:  # noqa: S110
            pass
        if time.time() > deadline:
            print(f"sin respuesta de {args.url}", file=sys.stderr)
            return 1
        time.sleep(1)


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", help="ruta de config.toml (por defecto /etc/meshbox/config.toml)"
    )
    p = argparse.ArgumentParser(prog="meshbox", description="Gateway, mapa y panel Meshtastic")
    p.add_argument("--version", action="version", version=f"meshbox {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run", parents=[common], help="servicio completo")
    sub.add_parser(
        "dev", parents=[common], help="servicio en modo desarrollo (privd falso, logs legibles)"
    )
    sub.add_parser("migrate", parents=[common], help="aplica migraciones pendientes (con respaldo)")

    r = sub.add_parser("record", parents=[common], help="graba paquetes de un conector en JSONL")
    r.add_argument("--connector", required=True)
    r.add_argument("--out", help="carpeta de salida (por defecto paths.recordings)")
    r.add_argument("--duration", type=float, default=0, help="segundos (0 = hasta Ctrl+C)")

    rp = sub.add_parser("replay", parents=[common], help="reproduce una grabación en el pipeline")
    rp.add_argument("file")
    rp.add_argument("--speed", default="max", help="1, 10, ... o max")
    rp.add_argument("--serve", action="store_true", help="levanta también los servidores")
    rp.add_argument("--db", help="base a usar (por defecto la del config)")
    rp.add_argument("--keep-time", action="store_true", help="no correr las horas al presente")

    i = sub.add_parser("inspect", parents=[common], help="imprime cada paquete decodificado")
    i.add_argument("file")
    i.add_argument("--limit", type=int, default=0)
    i.add_argument("--json", action="store_true")
    i.add_argument("--key", action="append", help="canal=clave_base64 adicional para descifrar")

    u = sub.add_parser("user", parents=[common], help="usuarios del panel")
    u.add_argument("action", choices=["create", "passwd", "list", "disable", "enable"])
    u.add_argument("username", nargs="?")
    u.add_argument("--role", choices=["admin", "operator"], default="admin")
    u.add_argument("--password-stdin", action="store_true")

    b = sub.add_parser("backup", parents=[common], help="respaldos de la base")
    b.add_argument("action", choices=["create", "list", "restore"])
    b.add_argument("--suffix")
    b.add_argument("--file")

    ch = sub.add_parser("channel", parents=[common], help="canales y claves")
    ch.add_argument("action", choices=["list", "add", "remove"])
    ch.add_argument("--name")
    ch.add_argument("--key", help="clave en base64 (por defecto AQ==, la clave por defecto)")
    ch.add_argument("--public", action="store_true", help="publicar el canal en el sitio")

    bs = sub.add_parser("bootstrap", parents=[common], help="config, secretos y cuentas iniciales")
    bs.add_argument("--mode", choices=["appliance", "shared"], default="appliance")
    bs.add_argument("--site-slug")
    bs.add_argument("--mqtt-root")
    bs.add_argument("--secrets", help="ruta de secrets.toml (por defecto, la del config)")
    bs.add_argument("--json", action="store_true")

    s = sub.add_parser("simulate", parents=[common], help="red simulada (desarrollo y pruebas)")
    s.add_argument("action", choices=["generate", "publish"])
    s.add_argument("--out", default="backend/tests/fixtures/sim-24h.jsonl")
    s.add_argument("--hours", type=float, default=24)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--file", default="backend/tests/fixtures/sim-24h.jsonl")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=1883)
    s.add_argument("--root", default="msh/AR/ejemplo")
    s.add_argument("--username")
    s.add_argument("--password-env")
    s.add_argument("--password-stdin", action="store_true")
    s.add_argument("--speed", type=float, default=10.0)
    s.add_argument("--limit", type=int)

    h = sub.add_parser("health", help="espera a que el servidor responda /api/v1/health")
    h.add_argument("--url", default="http://127.0.0.1:8081/api/v1/health")
    h.add_argument("--timeout", type=float, default=90)
    return p


COMMANDS = {
    "run": cmd_run,
    "dev": cmd_run,
    "migrate": cmd_migrate,
    "record": cmd_record,
    "replay": cmd_replay,
    "inspect": cmd_inspect,
    "user": cmd_user,
    "backup": cmd_backup,
    "channel": cmd_channel,
    "bootstrap": cmd_bootstrap,
    "simulate": cmd_simulate,
    "health": cmd_health,
}


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:  # consola de Windows en cp1252: textos de la radio con emojis
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    sys.exit(COMMANDS[args.cmd](args))


if __name__ == "__main__":
    main()
