#!/usr/bin/env python3
"""Shared deterministic archive and catalog validation helpers."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import tarfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


CATALOG_NAME = "developer-image-catalog.v1.json"
URL_PREFIX = "https://raw.githubusercontent.com/mengkaka/DeveloperDiskImage/release/"
REVISION_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[1-9][0-9]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^(14|15|16)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?$")

BASE_MEMBERS = (
    "BuildManifest.plist",
    "Image.dmg",
    "Image.dmg.trustcache",
)
CLASSIC_MEMBERS = (
    "DeveloperDiskImage.dmg",
    "DeveloperDiskImage.dmg.signature",
)


class CatalogError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, archive_name: str) -> dict[str, Any]:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise CatalogError(f"asset input must be a regular non-symlink file: {path}")
    return {
        "path": archive_name,
        "sha256": sha256_file(path),
        "size": metadata.st_size,
    }


def content_manifest(files: Iterable[tuple[Path, str]]) -> tuple[list[dict[str, Any]], str]:
    records = sorted(
        (file_record(path, archive_name) for path, archive_name in files),
        key=lambda item: item["path"].encode("utf-8"),
    )
    return records, hashlib.sha256(canonical_bytes(records)).hexdigest()


def write_ustar(destination: Path, files: Iterable[tuple[Path, str]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for source, archive_name in files:
            metadata = source.stat()
            if not stat.S_ISREG(metadata.st_mode) or source.is_symlink():
                raise CatalogError(f"asset input must be a regular non-symlink file: {source}")
            info = tarfile.TarInfo(archive_name)
            info.size = metadata.st_size
            info.mode = 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with source.open("rb") as input_file:
                archive.addfile(info, input_file)


def version_key(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(version)
    if match is None:
        raise CatalogError(f"unsupported classic DDI version: {version}")
    return tuple(int(component or 0) for component in match.groups())


def expected_url(relative_path: str) -> str:
    return URL_PREFIX + relative_path


def expected_archive_path(entry: dict[str, Any], kind: str) -> str:
    archive_hash = required_sha256(entry, "archiveSHA256")
    if kind == "base":
        asset_id = required_string(entry, "baseAssetID")
        return f"PulsePhone/archives/baseAssets/{asset_id}-{archive_hash}.tar"
    if kind == "classic":
        version = required_string(entry, "ddiVersion")
        return f"PulsePhone/archives/DDI/{version}-{archive_hash}.tar"
    raise CatalogError(f"unknown archive kind: {kind}")


def required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise CatalogError(f"{key} must be a non-empty string")
    return result


def required_sha256(value: dict[str, Any], key: str) -> str:
    result = required_string(value, key)
    if SHA256_RE.fullmatch(result) is None:
        raise CatalogError(f"{key} must be a lowercase SHA-256")
    return result


def required_positive_integer(value: dict[str, Any], key: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or isinstance(result, bool) or result <= 0:
        raise CatalogError(f"{key} must be a positive integer")
    return result


def read_catalog(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"unable to read catalog {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise CatalogError("catalog root must be an object")
    return parsed


def archive_manifest(path: Path, expected_members: tuple[str, ...]) -> tuple[list[dict[str, Any]], str]:
    with path.open("rb") as raw:
        header = raw.read(512)
    if len(header) != 512 or header[257:263] != b"ustar\x00":
        raise CatalogError(f"archive is not USTAR: {path}")

    try:
        with tarfile.open(path, mode="r:") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if names != list(expected_members):
                raise CatalogError(
                    f"archive members differ from required order/content: {path}: {names}"
                )
            records: list[dict[str, Any]] = []
            for member in members:
                if not member.isfile() or member.islnk() or member.issym() or member.pax_headers:
                    raise CatalogError(f"archive member is not a plain USTAR file: {path}:{member.name}")
                source = archive.extractfile(member)
                if source is None:
                    raise CatalogError(f"archive member cannot be read: {path}:{member.name}")
                digest = hashlib.sha256()
                remaining = member.size
                with source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                        remaining -= len(chunk)
                if remaining != 0:
                    raise CatalogError(f"archive member length changed while reading: {path}:{member.name}")
                records.append({"path": member.name, "sha256": digest.hexdigest(), "size": member.size})
    except (OSError, tarfile.TarError) as error:
        raise CatalogError(f"unable to inspect archive {path}: {error}") from error

    records.sort(key=lambda item: item["path"].encode("utf-8"))
    return records, hashlib.sha256(canonical_bytes(records)).hexdigest()


def verify_archive(root: Path, entry: dict[str, Any], kind: str) -> None:
    relative_path = expected_archive_path(entry, kind)
    expected_source_url = expected_url(relative_path)
    if entry.get("sourceURL") != expected_source_url:
        raise CatalogError(f"sourceURL must be exactly {expected_source_url}")

    parsed_url = urlparse(expected_source_url)
    if parsed_url.scheme != "https" or parsed_url.netloc != "raw.githubusercontent.com":
        raise CatalogError("sourceURL must use the approved raw GitHub HTTPS host")

    archive = root / relative_path
    if not archive.is_file() or archive.is_symlink():
        raise CatalogError(f"referenced archive missing or unsafe: {archive}")
    if archive.stat().st_size != required_positive_integer(entry, "archiveSize"):
        raise CatalogError(f"archiveSize mismatch: {archive}")
    if sha256_file(archive) != required_sha256(entry, "archiveSHA256"):
        raise CatalogError(f"archiveSHA256 mismatch: {archive}")

    expected_members = BASE_MEMBERS if kind == "base" else CLASSIC_MEMBERS
    _, manifest_hash = archive_manifest(archive, expected_members)
    if manifest_hash != required_sha256(entry, "contentManifestSHA256"):
        raise CatalogError(f"contentManifestSHA256 mismatch: {archive}")


def validate_catalog(root: Path, catalog: dict[str, Any], catalog_bytes: bytes | None = None) -> None:
    required_root_keys = {
        "schemaVersion",
        "catalogRevision",
        "defaultCandidateBaseAssetID",
        "baseAssets",
        "developerDiskImages",
        "catalogEntry",
    }
    if set(catalog) != required_root_keys:
        raise CatalogError(f"catalog keys must be exactly {sorted(required_root_keys)}")
    if catalog.get("schemaVersion") != 1:
        raise CatalogError("schemaVersion must be 1")
    revision = required_string(catalog, "catalogRevision")
    if REVISION_RE.fullmatch(revision) is None:
        raise CatalogError("catalogRevision must be YYYY-MM-DD.<positive sequence>")
    if catalog_bytes is not None and catalog_bytes != canonical_bytes(catalog):
        raise CatalogError("catalog is not canonical JSON or contains a trailing newline")

    base_assets = catalog.get("baseAssets")
    classic_assets = catalog.get("developerDiskImages")
    exact_entries = catalog.get("catalogEntry")
    if not all(isinstance(items, list) for items in (base_assets, classic_assets, exact_entries)):
        raise CatalogError("asset and entry collections must be arrays")
    if not base_assets:
        raise CatalogError("baseAssets cannot be empty")

    base_ids: set[str] = set()
    ordered_base_ids: list[str] = []
    for entry in base_assets:
        if not isinstance(entry, dict) or set(entry) != {
            "baseAssetID", "contentManifestSHA256", "archiveSHA256", "archiveSize", "sourceURL"
        }:
            raise CatalogError("baseAssets entry has an invalid shape")
        base_id = required_string(entry, "baseAssetID")
        if base_id in base_ids:
            raise CatalogError(f"duplicate baseAssetID: {base_id}")
        base_ids.add(base_id)
        ordered_base_ids.append(base_id)
        verify_archive(root, entry, "base")
    if ordered_base_ids != sorted(ordered_base_ids, key=lambda item: item.encode("utf-8")):
        raise CatalogError("baseAssets must be sorted by baseAssetID")
    if required_string(catalog, "defaultCandidateBaseAssetID") not in base_ids:
        raise CatalogError("defaultCandidateBaseAssetID must refer to baseAssets")

    classic_versions: set[str] = set()
    ordered_versions: list[tuple[int, int, int]] = []
    for entry in classic_assets:
        if not isinstance(entry, dict) or set(entry) != {
            "ddiVersion", "contentManifestSHA256", "archiveSHA256", "archiveSize", "sourceURL",
            "xcodeDDIVersion",
        }:
            raise CatalogError("developerDiskImages entry has an invalid shape")
        version = required_string(entry, "ddiVersion")
        if version in classic_versions:
            raise CatalogError(f"duplicate ddiVersion: {version}")
        classic_versions.add(version)
        ordered_versions.append(version_key(version))
        version_key(required_string(entry, "xcodeDDIVersion"))
        verify_archive(root, entry, "classic")
    if ordered_versions != sorted(ordered_versions):
        raise CatalogError("developerDiskImages must be sorted by parsed version")
    for entry in classic_assets:
        xcode_version = required_string(entry, "xcodeDDIVersion")
        if xcode_version not in classic_versions:
            raise CatalogError(
                f"xcodeDDIVersion must refer to a published classic DDI: {xcode_version}"
            )

    build_ids: set[str] = set()
    ordered_build_ids: list[str] = []
    for entry in exact_entries:
        if not isinstance(entry, dict) or set(entry) != {"iosVersion", "buildID", "baseAssetID"}:
            raise CatalogError("catalogEntry has an invalid shape")
        build_id = required_string(entry, "buildID")
        if build_id in build_ids:
            raise CatalogError(f"duplicate buildID: {build_id}")
        build_ids.add(build_id)
        ordered_build_ids.append(build_id)
        if required_string(entry, "iosVersion") == "":
            raise CatalogError("iosVersion cannot be empty")
        if required_string(entry, "baseAssetID") not in base_ids:
            raise CatalogError(f"catalogEntry refers to unknown baseAssetID: {build_id}")
    if ordered_build_ids != sorted(ordered_build_ids, key=lambda item: item.encode("utf-8")):
        raise CatalogError("catalogEntry must be sorted by buildID")
