# PulsePhone release catalog

This directory is the controlled source consumed by PulsePhone's Developer
Support preparation workflow. The `release` branch, this canonical catalog,
and the exact raw GitHub URLs are the trust boundary for that workflow.

## Published iOS 26 BaseImage candidate

`developer-image-catalog.v1.json` has one BaseImage default candidate built
from the selected Xcode iOS DDI `Restore` payload. It contains no device
identity, pairing records, ECID, nonce, TSS ticket, or device logs.

There is intentionally no `catalogEntry` for iOS 26.5.2 build `23F84` yet.
The BaseImage can be selected as the default candidate, but an exact-build
mapping is only published after a maintainer records real TSS, mount, service
probe, cleanup, and retry evidence for that build.

## Maintainer procedure

1. Refresh the generic `PersonalizedImages/Xcode_iOS_DDI_Personalized/`
   payload from an approved local Xcode with `update_ddi.py`.
2. Build a USTAR tar containing only `BuildManifest.plist`, `Image.dmg`, and
   `Image.dmg.trustcache` at the archive root. On macOS, use
   `COPYFILE_DISABLE=1 tar --format ustar --no-mac-metadata` so that neither
   PAX nor hidden AppleDouble `._*` entries are emitted. Do not include
   folders, links, tickets, logs, or device-specific files.
3. Compute SHA-256 and exact byte sizes for the tar and every member.
4. Add the BaseAsset with those values and its direct raw archive URL. Add a
   `catalogEntry` only after exact-device acceptance; keep JSON canonical:
   sorted object keys, sorted arrays, and no whitespace.
5. Verify the catalog with PulsePhone's canonical decoder and verify the tar
   listing and hashes before committing to `release`.
6. Run the exact-device TSS/mount/probe/cleanup acceptance. Only then change
   that entry's `evidenceState` from `target` to `verified` in a new revision.

PulsePhone deliberately fetches the direct catalog and archive URLs. It does
not call the GitHub Tree API or infer a nearest OS/build match. A cached valid
catalog and verified asset remain usable when this source is unavailable.
