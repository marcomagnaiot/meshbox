"""Mediciones contra los presupuestos de la sección 5.5 (etapas E2 y E5).

Reproducción (memoria y CPU del pipeline a máxima velocidad):

    python3 scripts/pi-bench.py replay backend/tests/fixtures/sim-24h.jsonl

Carga (50 clientes SSE y 20 peticiones/s durante 10 min contra un servidor en marcha):

    python3 scripts/pi-bench.py load --url http://127.0.0.1:8091 --sse 50 --rps 20 --duration 600
    python3 scripts/pi-bench.py load --url http://192.168.0.10:8090 --ssh mipi   # + memoria y CPU en la Pi

Presupuestos: RSS de meshbox 180 MB en régimen; CPU promedio 25 % con 2 paquetes/s y
50 clientes SSE; latencia paquete → SSE p95 1 s.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import psutil

BUDGET_RSS_MB = 180
BUDGET_CPU_PCT = 25
PUBLIC_PATHS = ["/api/v1/site", "/api/v1/nodes", "/api/v1/messages", "/api/v1/stats/summary",
                "/api/v1/links", "/api/v1/alerts", "/api/v1/waypoints"]  # fmt: skip


# --------------------------------------------------------------------------- reproducción


def bench_replay(recording: Path, keep: bool) -> int:
    work = Path(tempfile.mkdtemp(prefix="meshbox-bench-"))
    cfg = work / "config.toml"
    cfg.write_text(
        '[paths]\ndb = "bench.db"\nbackups = "b"\ntmp = "t"\ntiles = "tiles"\nrecordings = "rec"\n'
        'plugins = "p"\nsecrets = "secrets.toml"\n[logging]\njson_output = false\n[system]\nprivd = "fake"\n',
        encoding="utf-8",
    )
    py = sys.executable
    subprocess.run([py, "-m", "meshbox", "channel", "add", "--config", str(cfg), "--name", "MediumFast",
                    "--key", "AQ==", "--public"], check=True, capture_output=True)  # fmt: skip
    t0 = time.time()
    proc = subprocess.Popen([py, "-m", "meshbox", "replay", str(recording.resolve()), "--config", str(cfg),
                             "--speed", "max"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)  # fmt: skip
    ps = psutil.Process(proc.pid)
    rss: list[float] = []
    cpu: list[float] = []
    ps.cpu_percent(None)
    while proc.poll() is None:
        # En Windows el python del venv es un lanzador: el intérprete real es un proceso hijo.
        try:
            procs = [ps, *ps.children(recursive=True)]
            rss.append(sum(p.memory_info().rss for p in procs) / 1_048_576)
            cpu.append(sum(p.cpu_percent(None) for p in procs))
        except psutil.NoSuchProcess:
            pass
        time.sleep(0.5)
    out = proc.stdout.read() if proc.stdout else ""
    elapsed = time.time() - t0
    db = work / "bench.db"
    result = {
        "recording": str(recording),
        "seconds": round(elapsed, 1),
        "rss_peak_mb": round(max(rss), 1) if rss else None,
        "rss_avg_mb": round(statistics.mean(rss), 1) if rss else None,
        "cpu_avg_pct": round(statistics.mean(cpu), 1) if cpu else None,
        "db_mb": round(db.stat().st_size / 1_048_576, 2) if db.exists() else None,
        "summary": out.strip().splitlines()[-1] if out.strip() else "",
        "cores": psutil.cpu_count(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok = result["rss_peak_mb"] is not None and result["rss_peak_mb"] <= BUDGET_RSS_MB
    print(
        f"\nRSS pico {result['rss_peak_mb']} MB (presupuesto {BUDGET_RSS_MB} MB): {'OK' if ok else 'EXCEDIDO'}"
    )
    if not keep:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
    return 0 if ok else 1


# --------------------------------------------------------------------------- carga


async def sse_client(
    client: httpx.AsyncClient, url: str, stop: asyncio.Event, stats: dict[str, int]
) -> None:
    while not stop.is_set():
        try:
            async with client.stream("GET", url + "/api/v1/stream?activity=1", timeout=None) as r:
                if r.status_code != 200:
                    stats["sse_rejected"] += 1
                    await asyncio.sleep(5)
                    continue
                stats["sse_open"] += 1
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        stats["sse_events"] += 1
                    if stop.is_set():
                        break
        except httpx.HTTPError:
            stats["sse_errors"] += 1
            await asyncio.sleep(2)


async def requester(client: httpx.AsyncClient, url: str, rps: float, stop: asyncio.Event,
                    lat: list[float], stats: dict[str, int]) -> None:  # fmt: skip
    interval = 1.0 / rps
    while not stop.is_set():
        t = time.perf_counter()
        try:
            r = await client.get(url + random.choice(PUBLIC_PATHS), timeout=10)
            stats[f"http_{r.status_code}"] += 1
            lat.append((time.perf_counter() - t) * 1000)
        except httpx.HTTPError:
            stats["http_errors"] += 1
        await asyncio.sleep(max(0.0, interval - (time.perf_counter() - t)))


def ssh_sample(host: str) -> tuple[float, float] | None:
    cmd = "ps -C python3 -o rss=,pcpu=,args= | grep 'meshbox run' | grep -v grep | head -1"
    try:
        out = subprocess.run(
            ["ssh", host, cmd], capture_output=True, text=True, timeout=15
        ).stdout.split()
        return float(out[0]) / 1024, float(out[1])
    except (subprocess.SubprocessError, IndexError, ValueError):
        return None


async def bench_load(url: str, sse: int, rps: float, duration: float, ssh: str | None) -> int:
    from collections import Counter

    stats: Counter[str] = Counter()
    lat: list[float] = []
    stop = asyncio.Event()
    remote: list[tuple[float, float]] = []
    limits = httpx.Limits(max_connections=sse + 20, max_keepalive_connections=sse + 20)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [asyncio.create_task(sse_client(client, url, stop, stats)) for _ in range(sse)]
        tasks.append(asyncio.create_task(requester(client, url, rps, stop, lat, stats)))
        t0 = time.time()
        while time.time() - t0 < duration:
            await asyncio.sleep(5)
            if ssh:
                sample = await asyncio.to_thread(ssh_sample, ssh)
                if sample:
                    remote.append(sample)
            print(f"{time.time() - t0:5.0f} s  sse={stats['sse_open']}  eventos={stats['sse_events']}  "
                  f"http={sum(v for k, v in stats.items() if k.startswith('http_2'))}  "
                  f"errores={stats['http_errors'] + stats['sse_errors']}"
                  + (f"  rss={remote[-1][0]:.0f}MB cpu={remote[-1][1]:.0f}%" if remote else ""), flush=True)  # fmt: skip
        stop.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    lat.sort()

    def pct(p: float) -> float | None:
        return round(lat[min(len(lat) - 1, int(len(lat) * p))], 1) if lat else None

    result = {"url": url, "duration_s": duration, "sse_clients": sse, "rps": rps, "stats": dict(stats),
              "latency_ms": {"p50": pct(0.5), "p95": pct(0.95), "p99": pct(0.99)}}  # fmt: skip
    if remote:
        result["remote"] = {"rss_max_mb": round(max(r[0] for r in remote), 1),
                            "cpu_avg_pct": round(statistics.mean(r[1] for r in remote), 1)}  # fmt: skip
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("recording", type=Path)
    r.add_argument("--keep", action="store_true", help="no borrar la carpeta temporal")
    lo = sub.add_parser("load")
    lo.add_argument("--url", default="http://127.0.0.1:8091")
    lo.add_argument("--sse", type=int, default=50)
    lo.add_argument("--rps", type=float, default=20)
    lo.add_argument("--duration", type=float, default=600)
    lo.add_argument("--ssh", help="alias ssh de la Pi para medir memoria y CPU del servicio")
    args = p.parse_args()
    if args.cmd == "replay":
        return bench_replay(args.recording, args.keep)
    loop_factory = asyncio.SelectorEventLoop if os.name == "nt" else None
    return asyncio.run(
        bench_load(args.url, args.sse, args.rps, args.duration, args.ssh), loop_factory=loop_factory
    )


if __name__ == "__main__":
    sys.exit(main())
