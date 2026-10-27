"""Resume la estructura real de cada portnum en grabaciones JSONL (para docs/paquetes.md).

No imprime valores identificables (ids, nombres, posiciones): solo cantidades, campos
presentes y distribuciones.

    uv run python scripts/gen-paquetes-doc.py data/rec/real-*.jsonl > salida.md
"""

from __future__ import annotations

import glob
import sys
from collections import Counter, defaultdict
from pathlib import Path

from meshbox.connectors.replay import read_recording, record_to_packet
from meshbox.models import BROADCAST
from meshbox.pipeline.crypto import ChannelKey, try_decrypt
from meshbox.pipeline.decode import decode_data, message_to_dict


def main(paths: list[str]) -> None:
    files = [Path(p) for pat in paths for p in glob.glob(pat)]
    keys = [ChannelKey.from_psk(n, b"\x01") for n in ("LongFast", "MediumFast")]
    count: Counter[str] = Counter()
    fields: dict[str, Counter[str]] = defaultdict(Counter)
    directed: Counter[str] = Counter()
    hops: Counter[str] = Counter()
    precision: Counter[int] = Counter()
    variants: Counter[str] = Counter()
    gateways: set[str] = set()
    total = encrypted = 0
    for f in files:
        for rec in read_recording(f):
            pkt = record_to_packet(rec)
            if pkt is None:
                continue
            total += 1
            gateways.add(str(rec.get("gateway_id")))
            data = pkt.decoded if pkt.HasField("decoded") else None
            if data is None:
                encrypted += 1
                res = try_decrypt(pkt, keys)
                data = res[0] if res else None
            if data is None:
                count["(cifrado sin clave)"] += 1
                continue
            dec = decode_data(data)
            count[dec.portnum] += 1
            if pkt.to != BROADCAST:
                directed[dec.portnum] += 1
            if pkt.hop_start:
                hops[str(pkt.hop_start - pkt.hop_limit)] += 1
            if dec.ok and hasattr(dec.obj, "ListFields"):
                d = message_to_dict(dec.obj)
                for k in d:
                    fields[dec.portnum][k] += 1
                if dec.kind == "telemetry":
                    variants[dec.extra.get("variant") or "?"] += 1
                if dec.kind == "position":
                    precision[int(d.get("precision_bits", 0))] += 1
    print(
        f"Grabaciones: {len(files)} archivo(s), {total} paquetes, {len(gateways)} gateway(s), {encrypted} cifrados.\n"
    )
    print("| portnum | paquetes | dirigidos | campos observados (veces) |\n|---|---|---|---|")
    for port, n in count.most_common():
        fs = ", ".join(f"`{k}` ({v})" for k, v in fields[port].most_common(14))
        print(f"| `{port}` | {n} | {directed[port]} | {fs} |")
    if variants:
        print(
            "\nVariantes de telemetría: "
            + ", ".join(f"`{k}` {v}" for k, v in variants.most_common())
        )
    if precision:
        print(
            "\nPrecisión de posición (`precision_bits`): "
            + ", ".join(f"{k}: {v}" for k, v in sorted(precision.items()))
        )
    if hops:
        print(
            "\nSaltos recorridos al llegar al gateway: "
            + ", ".join(f"{k}: {v}" for k, v in sorted(hops.items()))
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main(sys.argv[1:])
