#!/usr/bin/env python3
"""Verify every PulsePhone release catalog archive and reference."""

from __future__ import annotations

import argparse
from pathlib import Path

from pulsephone_asset_catalog import CATALOG_NAME, CatalogError, read_catalog, validate_catalog


def main() -> None:
    default_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=default_root)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    catalog_path = root / "PulsePhone" / CATALOG_NAME
    payload = catalog_path.read_bytes()
    catalog = read_catalog(catalog_path)
    validate_catalog(root, catalog, payload)
    print(
        f"verified {catalog_path}: {len(catalog['baseAssets'])} BaseImage asset(s), "
        f"{len(catalog['developerDiskImages'])} classic DDI asset(s), "
        f"{len(catalog['catalogEntry'])} exact mapping(s)"
    )


if __name__ == "__main__":
    try:
        main()
    except (CatalogError, OSError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error
