from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ErrorCode, PlasmaError
from .models import JobResult, iso_now, legacy_channel_id_from_site, validate_job_id


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise PlasmaError(
            ErrorCode.OUTPUT_WRITE_FAILED,
            f"failed to write output file: {path}",
            original_exception=exc,
        ) from exc


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write_bytes(path, data)


class ServerEventLogger:
    def __init__(self, root: Path) -> None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.path = root / date / "server.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def event(self, level: str, event: str, **fields: Any) -> None:
        values = " ".join(f"{key}={value!r}" for key, value in fields.items() if value is not None)
        line = f"{iso_now()} {level.upper():<5} {event} {values}".rstrip() + "\n"
        try:
            with self._lock:
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(line)
        except OSError as exc:
            raise PlasmaError(
                ErrorCode.OUTPUT_WRITE_FAILED,
                f"failed to write server log: {self.path}",
                original_exception=exc,
            ) from exc


class JobEventLogger:
    def __init__(self, root: Path, site_id: int, job_id: str) -> None:
        validate_job_id(job_id)
        channel_id = legacy_channel_id_from_site(site_id)
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        directory = root / date / f"SITE{site_id}"
        legacy_directory = root / date / f"CH{channel_id}"
        directory.mkdir(parents=True, exist_ok=True)
        legacy_directory.mkdir(parents=True, exist_ok=True)
        self.text_path = directory / f"{job_id}.log"
        self.jsonl_path = directory / f"{job_id}.jsonl"
        # Temporary filesystem/schema compatibility for v3.1-era tools.
        self.legacy_text_path = legacy_directory / f"{job_id}.log"
        self.legacy_jsonl_path = legacy_directory / f"{job_id}.jsonl"
        self.site_id = site_id
        self.job_id = job_id
        self._lock = threading.Lock()

    @property
    def channel_id(self) -> int:
        """Legacy v3.1 identity derived from the canonical one-based Site ID."""
        return legacy_channel_id_from_site(self.site_id)

    @staticmethod
    def _text_line(record: dict[str, Any]) -> str:
        human_fields = " ".join(
            f"{key}={value!r}"
            for key, value in record.items()
            if key not in {"timestamp", "level", "event"}
        )
        return (
            f"{record['timestamp']} {record['level']:<5} {record['event']} {human_fields}"
            .rstrip()
            + "\n"
        )

    def event(self, event: str, *, level: str = "INFO", **fields: Any) -> None:
        timestamp = iso_now()
        common = {
            "timestamp": timestamp,
            "level": level.upper(),
            "event": event,
            "job_id": self.job_id,
            **{key: value for key, value in fields.items() if value is not None},
        }
        canonical_record = {
            **common,
            "site_id": self.site_id,
        }
        legacy_record = {
            **common,
            "channel_id": self.channel_id,
        }
        canonical_text = self._text_line(canonical_record)
        legacy_text = self._text_line(legacy_record)
        canonical_json = json.dumps(canonical_record, ensure_ascii=False, separators=(",", ":")) + "\n"
        legacy_json = json.dumps(legacy_record, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            with self._lock:
                with self.text_path.open("a", encoding="utf-8") as stream:
                    stream.write(canonical_text)
                with self.jsonl_path.open("a", encoding="utf-8") as stream:
                    stream.write(canonical_json)
                with self.legacy_text_path.open("a", encoding="utf-8") as stream:
                    stream.write(legacy_text)
                with self.legacy_jsonl_path.open("a", encoding="utf-8") as stream:
                    stream.write(legacy_json)
        except OSError as exc:
            raise PlasmaError(
                ErrorCode.OUTPUT_WRITE_FAILED,
                f"failed to write job log for {self.job_id}",
                original_exception=exc,
            ) from exc


@dataclass(slots=True)
class OutputManager:
    root: Path

    def job_directory(self, job_id: str) -> Path:
        validate_job_id(job_id)
        return self.root / job_id

    def write_state(self, job_id: str, data: dict[str, Any]) -> Path:
        path = self.job_directory(job_id) / "job_state.json"
        atomic_write_json(path, data)
        return path

    def write_result(self, result: JobResult) -> Path:
        path = self.job_directory(result.job_id) / "result.json"
        atomic_write_json(path, result.to_dict())
        return path

    def write_read_sections(
        self,
        job_id: str,
        site_id: int,
        sections: dict[str, bytes],
    ) -> list[Path]:
        directory = self.job_directory(job_id)
        used_names: set[str] = set()
        prepared: list[tuple[Path, bytes]] = []
        for raw_name, data in sections.items():
            safe_name = "".join(
                char if char.isascii() and (char.isalnum() or char in "-_") else "_"
                for char in raw_name
            )
            if not safe_name or len(safe_name) > 128:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "read section name is empty or too long")
            if safe_name in used_names:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "read section names collide after filename sanitization",
                    context={"section_name": raw_name, "safe_name": safe_name},
                )
            used_names.add(safe_name)
            path = directory / f"read_SITE{site_id}_{safe_name}.bin"
            prepared.append((path, data))

        paths: list[Path] = []
        for path, data in prepared:
            atomic_write_bytes(path, data)
            paths.append(path)
        return paths

    def recover_incomplete(self) -> list[str]:
        recovered: list[str] = []
        if not self.root.exists():
            return recovered
        for state_path in self.root.glob("*/job_state.json"):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if state.get("state") not in {"queued", "running"}:
                continue
            state["state"] = "aborted"
            state["finished_at"] = iso_now()
            state["error"] = {
                "error_code": ErrorCode.JOB_ABORTED.value,
                "error_type": "JOB_ABORTED",
                "message": "job was incomplete when the server restarted",
                "recoverable": False,
            }
            atomic_write_json(state_path, state)
            recovered.append(str(state.get("job_id", state_path.parent.name)))
        return recovered
