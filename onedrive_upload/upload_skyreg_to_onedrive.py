#!/usr/bin/env python3
"""Package SkyReg upload units and send them to OneDrive with rclone.

The script is intentionally small and resumable:

  1. `plan` discovers upload units and writes one JSON manifest per unit.
  2. `run` processes units sequentially: tar/copy, hash, upload, verify, clean.
  3. `status` summarizes manifest state.

Run this on the CRCV cluster after cloning this repository there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATASET_ROOT = Path("/home/qi940700/SkyReg")
TEMP_DIR = Path("/home/da625117/skyreg-dataset/onedrive_upload/onedrive_upload_tmp")
STATE_DIR = Path("/home/da625117/skyreg-dataset/onedrive_upload/onedrive_upload_state")
REMOTE_ROOT = "onedrive_eccv2026:SkyReg"

METADATA_DIRS = {".git", ".agents"}
IGNORED_FILE_NAMES = {".DS_Store"}

FINAL_STATUSES = {"complete"}
RETRYABLE_STATUSES = {
    "planned",
    "packing",
    "packed",
    "hashing",
    "uploading",
    "verifying",
    "uploaded",
    "cleaning",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def remote_join(*parts: str) -> str:
    cleaned = [part.strip("/") for part in parts if part and part.strip("/")]
    if not cleaned:
        return REMOTE_ROOT
    return REMOTE_ROOT.rstrip("/") + "/" + "/".join(cleaned)


def run_command(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    logging.debug("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def is_metadata_path(path: Path) -> bool:
    return any(part in METADATA_DIRS for part in path.parts) or path.name in IGNORED_FILE_NAMES


def list_dirs(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(
        child
        for child in path.iterdir()
        if child.is_dir() and child.name not in METADATA_DIRS
    )


def list_files_recursive(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        child
        for child in path.rglob("*")
        if child.is_file() and not is_metadata_path(child)
    )


def ensure_dirs() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "units").mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "logs").mkdir(parents=True, exist_ok=True)


def unit_path(unit_id: str) -> Path:
    return STATE_DIR / "units" / f"{unit_id}.json"


def base_unit(unit_id: str, mode: str, source_paths: list[str], remote_path: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "unit_id": unit_id,
        "mode": mode,
        "dataset_root": str(DATASET_ROOT),
        "temp_dir": str(TEMP_DIR),
        "remote_root": REMOTE_ROOT,
        "source_paths": source_paths,
        "remote_path": remote_path,
        "status": "planned",
        "attempts": 0,
        "local_bytes": None,
        "remote_bytes": None,
        "sha256": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "started_at": None,
        "completed_at": None,
        "last_error": None,
    }


def tar_unit(unit_id: str, archive_name: str, source_paths: list[str], remote_dir: str) -> dict[str, Any]:
    unit = base_unit(
        unit_id=unit_id,
        mode="tar",
        source_paths=source_paths,
        remote_path=remote_join(remote_dir, archive_name),
    )
    unit["archive_name"] = archive_name
    unit["local_archive_path"] = str(TEMP_DIR / archive_name)
    return unit


def copy_unit(unit_id: str, rel_path: str) -> dict[str, Any]:
    return base_unit(
        unit_id=unit_id,
        mode="copy",
        source_paths=[rel_path],
        remote_path=remote_join(rel_path),
    )


def merge_existing_unit(new_unit: dict[str, Any]) -> dict[str, Any]:
    path = unit_path(new_unit["unit_id"])
    if not path.exists():
        return new_unit

    old = load_json(path)
    preserved_keys = {
        "status",
        "attempts",
        "local_bytes",
        "remote_bytes",
        "sha256",
        "created_at",
        "started_at",
        "completed_at",
        "last_error",
    }
    for key in preserved_keys:
        if key in old:
            new_unit[key] = old[key]
    new_unit["updated_at"] = utc_now()
    return new_unit


def discover_landmark_units() -> list[dict[str, Any]]:
    root = DATASET_ROOT / "SkyReg-Landmark"
    modality_dirs = [
        child for child in list_dirs(root)
        if child.name.startswith("GT_")
    ]
    scene_ids = sorted({scene.name for modality in modality_dirs for scene in list_dirs(modality)})

    units = []
    for scene_id in scene_ids:
        source_paths = []
        for modality in modality_dirs:
            rel = Path("SkyReg-Landmark") / modality.name / scene_id
            if (DATASET_ROOT / rel).is_dir():
                source_paths.append(rel.as_posix())

        unit_id = f"landmark_scene_{slug(scene_id)}"
        archive_name = f"SkyReg-Landmark_scene-{scene_id}.tar"
        units.append(tar_unit(unit_id, archive_name, source_paths, "archives/SkyReg-Landmark"))
    return units


def discover_suburban_units() -> list[dict[str, Any]]:
    root = DATASET_ROOT / "SkyReg-Suburban"
    modality_dirs = [
        child for child in list_dirs(root)
        if child.name.startswith("GT_")
    ]
    city_names = sorted({city.name for modality in modality_dirs for city in list_dirs(modality)})

    units = []
    for city in city_names:
        source_paths = []
        for modality in modality_dirs:
            rel = Path("SkyReg-Suburban") / modality.name / city
            if (DATASET_ROOT / rel).is_dir():
                source_paths.append(rel.as_posix())

        unit_id = f"suburban_{slug(city)}"
        archive_name = f"SkyReg-Suburban_{city}.tar"
        units.append(tar_unit(unit_id, archive_name, source_paths, "archives/SkyReg-Suburban"))
    return units


def discover_urban_units() -> list[dict[str, Any]]:
    root = DATASET_ROOT / "SkyReg-Urban"
    units = []

    for city_dir in list_dirs(root):
        for modality_dir in list_dirs(city_dir):
            if not modality_dir.name.startswith("GT_"):
                continue
            for frame_dir in list_dirs(modality_dir):
                rel = Path("SkyReg-Urban") / city_dir.name / modality_dir.name / frame_dir.name
                unit_id = "urban_" + slug(f"{city_dir.name}_{modality_dir.name}_{frame_dir.name}")
                archive_name = f"SkyReg-Urban_{city_dir.name}_{modality_dir.name}_{frame_dir.name}.tar"
                remote_dir = f"archives/SkyReg-Urban/{city_dir.name}/{modality_dir.name}"
                units.append(tar_unit(unit_id, archive_name, [rel.as_posix()], remote_dir))
    return units


def discover_helper_units() -> list[dict[str, Any]]:
    units = []

    lib = DATASET_ROOT / "SkyReg_Lib.py"
    if lib.is_file():
        units.append(copy_unit("helper_skyreg_lib_py", "SkyReg_Lib.py"))

    demo_root = DATASET_ROOT / "demo"
    for file_path in list_files_recursive(demo_root):
        rel = file_path.relative_to(DATASET_ROOT).as_posix()
        units.append(copy_unit("helper_" + slug(rel), rel))

    return units


def write_plan() -> list[dict[str, Any]]:
    ensure_dirs()
    if not DATASET_ROOT.is_dir():
        raise FileNotFoundError(f"Dataset root does not exist: {DATASET_ROOT}")

    units = (
        discover_landmark_units()
        + discover_suburban_units()
        + discover_urban_units()
        + discover_helper_units()
    )

    for unit in units:
        atomic_write_json(unit_path(unit["unit_id"]), merge_existing_unit(unit))

    summary = {
        "dataset_root": str(DATASET_ROOT),
        "remote_root": REMOTE_ROOT,
        "temp_dir": str(TEMP_DIR),
        "state_dir": str(STATE_DIR),
        "unit_count": len(units),
        "updated_at": utc_now(),
    }
    atomic_write_json(STATE_DIR / "summary.json", summary)
    return units


def setup_logging(verbose: bool) -> None:
    ensure_dirs()
    log_path = STATE_DIR / "logs" / f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    logging.info("Writing log to %s", log_path)


def save_unit(unit: dict[str, Any]) -> None:
    unit["updated_at"] = utc_now()
    atomic_write_json(unit_path(unit["unit_id"]), unit)


def set_status(unit: dict[str, Any], status: str) -> None:
    unit["status"] = status
    save_unit(unit)


def fail_unit(unit: dict[str, Any], error: BaseException) -> None:
    unit["status"] = "failed"
    unit["last_error"] = str(error)
    unit["updated_at"] = utc_now()
    save_unit(unit)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote_size(remote_path: str) -> int | None:
    try:
        result = run_command(["rclone", "size", "--json", remote_path], capture=True)
        data = json.loads(result.stdout)
        if data.get("count") == 1:
            return int(data["bytes"])
    except Exception as error:
        logging.debug("rclone size --json failed for %s: %s", remote_path, error)

    try:
        result = run_command(["rclone", "lsl", remote_path], capture=True)
        line = result.stdout.strip().splitlines()[0]
        return int(line.split(maxsplit=1)[0])
    except Exception as error:
        logging.debug("rclone lsl failed for %s: %s", remote_path, error)
        return None


def upload_file(local_path: Path, remote_path: str) -> None:
    run_command([
        "rclone",
        "copyto",
        str(local_path),
        remote_path,
        "--progress",
        "--stats",
        "30s",
        "--transfers",
        "1",
        "--checkers",
        "4",
    ])


def write_sidecars(unit: dict[str, Any], payload_path: Path) -> tuple[Path, Path]:
    sha_path = payload_path.with_name(payload_path.name + ".sha256")
    manifest_path = payload_path.with_name(payload_path.name + ".manifest.json")

    sha_path.write_text(f"{unit['sha256']}  {payload_path.name}\n", encoding="utf-8")
    atomic_write_json(manifest_path, unit)
    return sha_path, manifest_path


def sidecar_remote_paths(payload_remote_path: str) -> tuple[str, str]:
    return payload_remote_path + ".sha256", payload_remote_path + ".manifest.json"


def should_skip_completed_remote(unit: dict[str, Any]) -> bool:
    expected_size = unit.get("local_bytes")
    if expected_size is None:
        return False
    actual_size = remote_size(unit["remote_path"])
    if actual_size == expected_size:
        unit["remote_bytes"] = actual_size
        unit["status"] = "complete"
        unit["completed_at"] = unit.get("completed_at") or utc_now()
        unit["last_error"] = None
        save_unit(unit)
        logging.info("Skipping complete remote: %s", unit["unit_id"])
        return True
    return False


def create_tar(unit: dict[str, Any]) -> Path:
    archive_path = Path(unit["local_archive_path"])
    partial_path = archive_path.with_suffix(archive_path.suffix + ".partial")

    for path in (archive_path, partial_path):
        if path.exists():
            path.unlink()

    cmd = [
        "tar",
        "--exclude=.git",
        "--exclude=.agents",
        "--exclude=.DS_Store",
        "-cf",
        str(partial_path),
        "-C",
        str(DATASET_ROOT),
    ] + unit["source_paths"]

    if not unit["source_paths"]:
        raise RuntimeError(f"No source paths for {unit['unit_id']}")

    set_status(unit, "packing")
    run_command(cmd)
    os.replace(partial_path, archive_path)
    unit["local_bytes"] = archive_path.stat().st_size
    set_status(unit, "packed")
    return archive_path


def process_tar_unit(unit: dict[str, Any]) -> None:
    if should_skip_completed_remote(unit):
        return

    archive_path = Path(unit["local_archive_path"])
    if unit["status"] in {"packed", "hashing", "uploading", "verifying", "uploaded", "cleaning"}:
        if not archive_path.exists():
            logging.info("Local archive missing; repacking %s", unit["unit_id"])
            archive_path = create_tar(unit)
    else:
        archive_path = create_tar(unit)

    set_status(unit, "hashing")
    unit["sha256"] = sha256_file(archive_path)
    unit["local_bytes"] = archive_path.stat().st_size
    save_unit(unit)

    sha_path, manifest_path = write_sidecars(unit, archive_path)
    sha_remote, manifest_remote = sidecar_remote_paths(unit["remote_path"])

    actual_size = remote_size(unit["remote_path"])
    if actual_size == unit["local_bytes"]:
        logging.info("Remote archive already matches local size: %s", unit["unit_id"])
        unit["remote_bytes"] = actual_size
        save_unit(unit)
        upload_file(sha_path, sha_remote)
        upload_file(manifest_path, manifest_remote)
        set_status(unit, "cleaning")
        for path in (archive_path, sha_path, manifest_path):
            if path.exists():
                path.unlink()
        unit["completed_at"] = utc_now()
        unit["last_error"] = None
        set_status(unit, "complete")
        return

    set_status(unit, "uploading")
    upload_file(archive_path, unit["remote_path"])

    set_status(unit, "verifying")
    actual_size = remote_size(unit["remote_path"])
    unit["remote_bytes"] = actual_size
    save_unit(unit)
    if actual_size != unit["local_bytes"]:
        raise RuntimeError(
            f"Remote size mismatch for {unit['unit_id']}: "
            f"local={unit['local_bytes']} remote={actual_size}"
        )

    upload_file(sha_path, sha_remote)
    upload_file(manifest_path, manifest_remote)

    set_status(unit, "uploaded")
    set_status(unit, "cleaning")
    for path in (archive_path, sha_path, manifest_path):
        if path.exists():
            path.unlink()

    unit["completed_at"] = utc_now()
    unit["last_error"] = None
    set_status(unit, "complete")


def process_copy_unit(unit: dict[str, Any]) -> None:
    source_path = DATASET_ROOT / unit["source_paths"][0]
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    unit["local_bytes"] = source_path.stat().st_size
    save_unit(unit)
    if should_skip_completed_remote(unit):
        return

    set_status(unit, "hashing")
    unit["sha256"] = sha256_file(source_path)
    save_unit(unit)

    set_status(unit, "uploading")
    upload_file(source_path, unit["remote_path"])

    set_status(unit, "verifying")
    actual_size = remote_size(unit["remote_path"])
    unit["remote_bytes"] = actual_size
    save_unit(unit)
    if actual_size != unit["local_bytes"]:
        raise RuntimeError(
            f"Remote size mismatch for {unit['unit_id']}: "
            f"local={unit['local_bytes']} remote={actual_size}"
        )

    set_status(unit, "complete")
    unit["completed_at"] = utc_now()
    unit["last_error"] = None
    save_unit(unit)


def iter_units(unit_filter: str | None = None) -> list[dict[str, Any]]:
    unit_files = sorted((STATE_DIR / "units").glob("*.json"))
    units = [load_json(path) for path in unit_files]
    if unit_filter:
        units = [unit for unit in units if unit["unit_id"] == unit_filter]
    return units


def run_uploads(args: argparse.Namespace) -> int:
    setup_logging(args.verbose)
    if args.plan:
        units = write_plan()
        logging.info("Planned %d units", len(units))

    units = iter_units(args.unit)
    if not units:
        logging.error("No units found. Run `plan` first.")
        return 1

    processed = 0
    for unit in units:
        status = unit.get("status", "planned")
        if status in FINAL_STATUSES:
            continue
        if status == "failed" and not args.retry_failed:
            continue
        if status not in RETRYABLE_STATUSES and status != "failed":
            logging.warning("Skipping unknown status %s for %s", status, unit["unit_id"])
            continue
        if args.limit is not None and processed >= args.limit:
            break

        logging.info("Processing %s (%s)", unit["unit_id"], unit["mode"])
        unit["attempts"] = int(unit.get("attempts") or 0) + 1
        unit["started_at"] = unit.get("started_at") or utc_now()
        unit["last_error"] = None
        save_unit(unit)

        try:
            if unit["mode"] == "tar":
                process_tar_unit(unit)
            elif unit["mode"] == "copy":
                process_copy_unit(unit)
            else:
                raise ValueError(f"Unknown unit mode: {unit['mode']}")
        except Exception as error:
            fail_unit(unit, error)
            logging.exception("Failed %s", unit["unit_id"])
            if not args.keep_going:
                return 1

        processed += 1

    logging.info("Processed %d unit(s)", processed)
    return 0


def print_status() -> int:
    units = iter_units()
    counts: dict[str, int] = {}
    total_bytes = 0
    for unit in units:
        counts[unit.get("status", "unknown")] = counts.get(unit.get("status", "unknown"), 0) + 1
        if unit.get("status") == "complete" and unit.get("local_bytes"):
            total_bytes += int(unit["local_bytes"])

    print(f"units: {len(units)}")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")
    print(f"completed_payload_bytes: {total_bytes}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="discover units and write JSON manifests")
    plan.set_defaults(func=lambda _args: print(f"planned {len(write_plan())} units"))

    run = subparsers.add_parser("run", help="upload units sequentially")
    run.add_argument("--plan", action="store_true", help="refresh the plan before running")
    run.add_argument("--unit", help="process only one unit_id")
    run.add_argument("--limit", type=int, help="process at most N units")
    run.add_argument("--retry-failed", action="store_true", help="retry units with failed status")
    run.add_argument("--keep-going", action="store_true", help="continue after a unit fails")
    run.add_argument("--verbose", action="store_true", help="enable debug logging")
    run.set_defaults(func=run_uploads)

    status = subparsers.add_parser("status", help="summarize manifest statuses")
    status.set_defaults(func=lambda _args: print_status())

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    if isinstance(result, int):
        return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
