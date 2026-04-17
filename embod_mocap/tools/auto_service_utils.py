from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence


def now_ts() -> float:
    return time.time()


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def safe_mkdir(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "posix":
        return Path(f"/proc/{pid}").exists()
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


@dataclass(frozen=True)
class SceneLockMeta:
    scene: str
    holder: str
    pid: int
    hostname: str
    started_at: str
    started_ts: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "scene": self.scene,
            "holder": self.holder,
            "pid": int(self.pid),
            "hostname": self.hostname,
            "started_at": self.started_at,
            "started_ts": float(self.started_ts),
        }


class SceneLock:
    """
    Scene-level cooperative lock implemented as an atomic mkdir lock.

    Layout:
      <lock_root>/<scene>.lock/            (directory; creation is atomic)
        meta.json
    """

    def __init__(
        self,
        lock_root: Path,
        scene: str,
        holder: str,
        stale_seconds: Optional[float] = None,
    ) -> None:
        self.lock_root = lock_root
        self.scene = scene
        self.holder = holder
        self.stale_seconds = stale_seconds

        self.lock_dir = lock_root / f"{scene}.lock"
        self.meta_path = self.lock_dir / "meta.json"

    def _write_meta(self) -> None:
        meta = SceneLockMeta(
            scene=self.scene,
            holder=self.holder,
            pid=os.getpid(),
            hostname=socket.gethostname(),
            started_at=now_str(),
            started_ts=now_ts(),
        )
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.meta_path)

    def read_meta_text(self) -> str:
        try:
            return self.meta_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
        except Exception:
            return ""

    def _is_stale(self) -> bool:
        if self.stale_seconds is None:
            return False
        try:
            st = self.lock_dir.stat()
            age = now_ts() - st.st_mtime
        except FileNotFoundError:
            return False
        except Exception:
            return False
        if age < self.stale_seconds:
            return False

        # Extra safety: only auto-break if pid is gone (same host only).
        meta_txt = self.read_meta_text()
        if not meta_txt:
            return True
        try:
            meta = json.loads(meta_txt)
            pid = int(meta.get("pid", -1))
            hostname = str(meta.get("hostname", ""))
        except Exception:
            return True

        if hostname and hostname != socket.gethostname():
            # Another host: don't guess. Treat as not stale.
            return False
        return not _pid_exists(pid)

    def try_acquire(self) -> bool:
        safe_mkdir(self.lock_root)
        try:
            self.lock_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            if self._is_stale():
                shutil.rmtree(self.lock_dir, ignore_errors=True)
                try:
                    self.lock_dir.mkdir(parents=False, exist_ok=False)
                except Exception:
                    return False
            else:
                return False
        except Exception:
            return False

        try:
            self._write_meta()
        except Exception:
            # If meta writing fails, release the lock to avoid a deadlock.
            shutil.rmtree(self.lock_dir, ignore_errors=True)
            return False
        return True

    def acquire(self, wait_seconds: float = 0.0, poll_seconds: float = 2.0) -> bool:
        deadline = now_ts() + max(0.0, float(wait_seconds))
        while True:
            if self.try_acquire():
                return True
            if wait_seconds <= 0 or now_ts() >= deadline:
                return False
            time.sleep(max(0.1, float(poll_seconds)))

    def release(self) -> None:
        shutil.rmtree(self.lock_dir, ignore_errors=True)

    def __enter__(self) -> "SceneLock":
        ok = self.acquire(wait_seconds=0.0)
        if not ok:
            meta = self.read_meta_text().strip()
            raise RuntimeError(f"Scene lock busy: {self.scene}. Meta: {meta or '<missing>'}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.release()


def run_logged(
    cmd: Sequence[str],
    cwd: Path,
    log_path: Path,
) -> int:
    """
    Run a command and tee stdout+stderr into:
      - current stdout (systemd journal)
      - log_path
    """

    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd_str = " ".join(map(str, cmd))
    header = f"\n===== {now_str()} START =====\n[CWD] {cwd}\n[CMD] {cmd_str}\n"
    footer_tpl = "\n===== {end} END rc={rc} =====\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(header)
        f.flush()

        try:
            proc = subprocess.Popen(
                list(cmd),
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError:
            msg = f"[ERROR] command not found: {cmd[0]}\n"
            print(msg, end="", flush=True)
            f.write(msg)
            f.write(footer_tpl.format(end=now_str(), rc=127))
            f.flush()
            return 127

        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            f.write(line)
        rc = int(proc.wait())

        f.write(footer_tpl.format(end=now_str(), rc=rc))
        f.flush()
    return rc

