"""Trabajos en segundo plano de privd (actualizaciones, cambio de WiFi, apagado).

Cada trabajo corre en un hilo propio y deja su estado en `<state_dir>/jobs/<id>.json` para que
`update.status` lo encuentre aunque privd se haya reiniciado (lo hace al final de cada
actualización).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .core import CommandError, fsync_dir

log = logging.getLogger("privd.jobs")

JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")
FINAL_STATES = ("succeeded", "failed", "rolled_back", "interrupted")
KEEP_JOB_FILES = 30


class Job:
    """Estado de un trabajo. Se modifica solo desde su hilo (con el candado del gestor)."""

    def __init__(self, manager: JobManager, kind: str, group: str, meta: dict[str, Any]) -> None:
        self.manager = manager
        self.id = secrets.token_hex(6)
        self.kind = kind
        self.group = group
        self.state = "running"
        self.step = "queued"
        self.progress: float | None = None
        self.message = ""
        self.error_code: str | None = None
        self.started_at = manager.clock()
        self.finished_at: float | None = None
        self.result: dict[str, Any] = {}
        self.meta = meta

    def update(self, **fields: Any) -> None:
        self.manager.update(self, **fields)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.id,
            "kind": self.kind,
            "state": self.state,
            "step": self.step,
            "progress": self.progress,
            "message": self.message,
            "error_code": self.error_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "meta": self.meta,
            "result": self.result,
        }


class JobManager:
    def __init__(
        self,
        state_dir: Path | None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.state_dir = state_dir
        self.clock = clock
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._finished_callbacks: list[Callable[[Job], None]] = []

    # -- persistencia ------------------------------------------------------------------------

    @property
    def jobs_dir(self) -> Path | None:
        return self.state_dir / "jobs" if self.state_dir is not None else None

    def _persist(self, job: Job) -> None:
        directory = self.jobs_dir
        if directory is None:
            return
        try:
            directory.mkdir(parents=True, exist_ok=True)
            data = json.dumps(job.to_dict(), ensure_ascii=False, sort_keys=True).encode()
            fd, tmp = tempfile.mkstemp(prefix=f".{job.id}.", dir=str(directory))
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            Path(tmp).replace(directory / f"{job.id}.json")
            fsync_dir(directory)
        except OSError as exc:
            log.warning("no se pudo guardar el estado del trabajo %s: %s", job.id, exc)

    def _prune_files(self) -> None:
        directory = self.jobs_dir
        if directory is None or not directory.is_dir():
            return
        files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[KEEP_JOB_FILES:]:
            with contextlib.suppress(OSError):
                old.unlink()

    def load_persisted(self) -> None:
        """Al arrancar: los trabajos que quedaron `running` se marcan como interrumpidos."""
        directory = self.jobs_dir
        if directory is None or not directory.is_dir():
            return
        for path in directory.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict) or data.get("state") != "running":
                continue
            data["state"] = "interrupted"
            data["message"] = "privd se detuvo mientras el trabajo estaba en curso"
            data["finished_at"] = self.clock()
            try:
                path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), "utf-8")
            except OSError:
                pass
        self._prune_files()

    def _read_persisted(self, job_id: str) -> dict[str, Any] | None:
        directory = self.jobs_dir
        if directory is None:
            return None
        path = directory / f"{job_id}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    # -- ciclo de vida -------------------------------------------------------------------------

    def on_finished(self, callback: Callable[[Job], None]) -> None:
        self._finished_callbacks.append(callback)

    def running(self, group: str) -> Job | None:
        with self._lock:
            for job in self._jobs.values():
                if job.group == group and job.state == "running":
                    return job
        return None

    def active(self) -> bool:
        with self._lock:
            return any(job.state == "running" for job in self._jobs.values())

    def start(
        self,
        kind: str,
        fn: Callable[[Job], dict[str, Any] | None],
        *,
        group: str,
        meta: dict[str, Any] | None = None,
    ) -> Job:
        with self._lock:
            busy = self.running(group)
            if busy is not None:
                raise CommandError("busy", f"ya hay un trabajo en curso ({busy.kind} {busy.id})")
            job = Job(self, kind, group, dict(meta or {}))
            self._jobs[job.id] = job
            self._persist(job)
            thread = threading.Thread(
                target=self._run, args=(job, fn), name=f"job-{kind}-{job.id}", daemon=True
            )
            self._threads[job.id] = thread
        log.info("trabajo %s (%s) iniciado", job.id, kind)
        thread.start()
        return job

    def _run(self, job: Job, fn: Callable[[Job], dict[str, Any] | None]) -> None:
        try:
            result = fn(job)
            with self._lock:
                if job.state == "running":
                    job.state = "succeeded"
                if result:
                    job.result.update(result)
        except CommandError as exc:
            with self._lock:
                job.state = "failed"
                job.error_code = exc.code
                job.message = exc.message
        except Exception:
            log.exception("error interno en el trabajo %s", job.id)
            with self._lock:
                job.state = "failed"
                job.error_code = "command_failed"
                job.message = "error interno de privd (ver el registro)"
        finally:
            with self._lock:
                job.finished_at = self.clock()
                if job.state == "running":
                    job.state = "failed"
                self._persist(job)
            self._prune_files()
            log.info("trabajo %s (%s) terminó: %s %s", job.id, job.kind, job.state, job.message)
            for callback in self._finished_callbacks:
                try:
                    callback(job)
                except Exception:
                    log.exception("error en el aviso de fin del trabajo %s", job.id)

    def update(self, job: Job, **fields: Any) -> None:
        with self._lock:
            for key, value in fields.items():
                if key not in {"state", "step", "progress", "message", "result", "error_code"}:
                    raise ValueError(key)
                if key == "result":
                    job.result.update(value)
                else:
                    setattr(job, key, value)
            self._persist(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return job.to_dict()
        return self._read_persisted(job_id)

    def latest(self, kind: str) -> dict[str, Any] | None:
        with self._lock:
            candidates = [j for j in self._jobs.values() if j.kind == kind]
            if candidates:
                return max(candidates, key=lambda j: j.started_at).to_dict()
        directory = self.jobs_dir
        if directory is None or not directory.is_dir():
            return None
        best: dict[str, Any] | None = None
        for path in directory.glob("*.json"):
            data = self._read_persisted(path.stem)
            if not data or data.get("kind") != kind:
                continue
            if best is None or float(data.get("started_at") or 0) > float(
                best.get("started_at") or 0
            ):
                best = data
        return best

    def wait(self, job_id: str, timeout: float | None = None) -> None:
        thread = self._threads.get(job_id)
        if thread is not None:
            thread.join(timeout)

    def wait_all(self, timeout: float | None = None) -> None:
        end = None if timeout is None else time.monotonic() + timeout
        for thread in list(self._threads.values()):
            remaining = None if end is None else max(0.0, end - time.monotonic())
            thread.join(remaining)
