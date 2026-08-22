#!/usr/bin/env python3
"""Build deterministic PulsePhone classic DDI archives and canonical catalog."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from pulsephone_asset_catalog import (
    CATALOG_NAME,
    CLASSIC_MEMBERS,
    CatalogError,
    canonical_bytes,
    content_manifest,
    expected_archive_path,
    expected_url,
    read_catalog,
    sha256_file,
    validate_catalog,
    version_key,
    write_ustar,
)


def parse_entry(value: str) -> dict[str, str]:
    pieces = value.split(",")
    if len(pieces) != 3 or any(not piece for piece in pieces):
        raise argparse.ArgumentTypeError(
            "catalog entry must be iosVersion,buildID,baseAssetID"
        )
    return {"iosVersion": pieces[0], "buildID": pieces[1], "baseAssetID": pieces[2]}


def parse_xcode_ddi_version(value: str) -> tuple[str, str]:
    logical, separator, xcode = value.partition("=")
    if separator != "=" or not logical or not xcode:
        raise argparse.ArgumentTypeError(
            "Xcode DDI mapping must be LOGICAL_VERSION=XCODE_DIRECTORY_VERSION"
        )
    return logical, xcode


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=root)
    parser.add_argument("--catalog-revision", required=True)
    parser.add_argument(
      "--catalog-entry",
        action="append",
        default=[],
        type=parse_entry,
        metavar="IOS_VERSION,BUILD_ID,BASE_ASSET_ID",
      help="replace or add an exact verified iOS 17+ mapping",
    )
    parser.add_argument(
        "--xcode-ddi-version",
        action="append",
        default=[],
        type=parse_xcode_ddi_version,
        metavar="LOGICAL_VERSION=XCODE_DIRECTORY_VERSION",
        help="declare the selected Xcode DeviceSupport directory for one classic DDI",
    )
    return parser.parse_args()


def build_classic_archive(
    root: Path, version: str, xcode_ddi_version: str
) -> dict[str, object]:
    source_directory = root / "DeveloperDiskImages" / version
    files = [(source_directory / name, name) for name in CLASSIC_MEMBERS]
    _, manifest_hash = content_manifest(files)
    destination_directory = root / "PulsePhone" / "archives" / "DDI"
    destination_directory.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{version}.", suffix=".tar", dir=destination_directory)
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        write_ustar(temporary, files)
        archive_hash = sha256_file(temporary)
        destination = destination_directory / f"{version}-{archive_hash}.tar"
        if destination.exists():
            if sha256_file(destination) != archive_hash:
                raise CatalogError(f"existing archive hash differs: {destination}")
            temporary.unlink()
        else:
            temporary.replace(destination)
        return {
            "ddiVersion": version,
            "contentManifestSHA256": manifest_hash,
            "archiveSHA256": archive_hash,
            "archiveSize": destination.stat().st_size,
            "sourceURL": expected_url(
                expected_archive_path(
                    {"ddiVersion": version, "archiveSHA256": archive_hash}, "classic"
                )
            ),
            "xcodeDDIVersion": xcode_ddi_version,
        }
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    root = args.repo_root.resolve()
    catalog_path = root / "PulsePhone" / CATALOG_NAME
    existing = read_catalog(catalog_path)
    versions = sorted(
        (
            directory.name
            for directory in (root / "DeveloperDiskImages").iterdir()
            if directory.is_dir() and directory.name.startswith(("14.", "15.", "16."))
        ),
        key=version_key,
    )
    xcode_versions = {version: version for version in versions}
    for logical, xcode in args.xcode_ddi_version:
        if logical not in xcode_versions:
            raise CatalogError(f"unknown logical classic DDI version: {logical}")
        if xcode not in xcode_versions:
            raise CatalogError(f"Xcode DDI directory is not a published classic version: {xcode}")
        xcode_versions[logical] = xcode
    classic_assets = [
        build_classic_archive(root, version, xcode_versions[version]) for version in versions
    ]

    replacements = {entry["buildID"]: entry for entry in args.catalog_entry}
    entries = {
        entry["buildID"]: entry
        for entry in existing.get("catalogEntry", [])
        if isinstance(entry, dict) and isinstance(entry.get("buildID"), str)
    }
    entries.update(replacements)
    catalog = {
        "schemaVersion": 1,
        "catalogRevision": args.catalog_revision,
        "defaultCandidateBaseAssetID": existing["defaultCandidateBaseAssetID"],
        "baseAssets": sorted(existing["baseAssets"], key=lambda entry: entry["baseAssetID"].encode("utf-8")),
        "developerDiskImages": classic_assets,
        "catalogEntry": sorted(entries.values(), key=lambda entry: entry["buildID"].encode("utf-8")),
    }
    payload = canonical_bytes(catalog)
    validate_catalog(root, catalog, payload)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".catalog.", dir=catalog_path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        Path(temporary_name).replace(catalog_path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    print(f"wrote {catalog_path} with {len(classic_assets)} classic DDI archives")


if __name__ == "__main__":
    try:
        main()
    except (CatalogError, OSError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error
