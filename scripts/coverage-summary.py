"""Cobertura por paquete (sección 27: mínimo 85 % en pipeline, store, auth, alerts y privd).

uv run pytest --cov=meshbox --cov-report=json:coverage.json
uv run python scripts/coverage-summary.py coverage.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED = {"pipeline", "store", "auth", "alerts"}


def main(path: str) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    groups: dict[str, list[int]] = {}
    for fname, v in data["files"].items():
        rel = fname.replace("\\", "/").split("meshbox/")[-1]
        top = rel.split("/")[0] if "/" in rel else "(raíz)"
        s = v["summary"]
        g = groups.setdefault(top, [0, 0])
        g[0] += s["covered_lines"]
        g[1] += s["num_statements"]
    failed = False
    for name in sorted(groups):
        covered, total = groups[name]
        pct = 100 * covered / max(total, 1)
        mark = ""
        if name in REQUIRED:
            mark = "  OK" if pct >= 85 else "  < 85 %"
            failed |= pct < 85
        print(f"{name:14} {pct:5.1f} %  ({covered}/{total}){mark}")
    print(f"TOTAL          {data['totals']['percent_covered']:5.1f} %")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "coverage.json"))
