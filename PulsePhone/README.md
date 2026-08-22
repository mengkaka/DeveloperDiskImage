# PulsePhone release catalog

This directory is the controlled source consumed by PulsePhone's Developer
Support preparation workflow. The `release` branch, this canonical catalog,
and the exact raw GitHub URLs are the trust boundary for that workflow.

## Published Assets

`developer-image-catalog.v1.json` has one BaseImage default candidate built
from the selected Xcode iOS DDI `Restore` payload. It contains no device
identity, pairing records, ECID, nonce, TSS ticket, or device logs.

`developer-image-catalog.v1.json` also lists one deterministic USTAR archive
per supported iOS 14--16 classic DDI. Those archives live in `archives/DDI/`;
each contains exactly `DeveloperDiskImage.dmg` and
`DeveloperDiskImage.dmg.signature`. The JSON field remains
`developerDiskImages` even though the remote directory is named `DDI`.
`ddiVersion` is the logical iOS matching key and archive label.
`xcodeDDIVersion` is the separately declared selected Xcode `DeviceSupport/`
directory that supplied the hash-pinned bytes. It is not a nearest-version
fallback. A non-identical mapping is added only with documented device proof.

An exact iOS 17+ `catalogEntry` is published only after a maintainer records
real remote-asset acquisition, TSS, mount, service probe, cleanup, and retry
evidence for that build. It is not inferred from an Xcode-mounted reuse or a
local candidate observation.

## Maintainer procedure

1. Refresh the generic `PersonalizedImages/Xcode_iOS_DDI_Personalized/`
   payload from an approved local Xcode with `update_ddi.py` when publishing a
   new BaseImage.
2. Run `PulsePhone/scripts/build-pulsephone-assets.py --catalog-revision
   YYYY-MM-DD.N`. It creates deterministic USTAR archives for all supported
   classic DDI inputs and writes canonical JSON with no trailing newline. For
   an approved cross-directory candidate, declare it explicitly, for example
   `--xcode-ddi-version 16.2=16.1 --xcode-ddi-version 16.3=16.1`.
3. Run `PulsePhone/scripts/verify-pulsephone-assets.py`. It verifies catalog
   canonicality, ordering, references, archive hashes, archive sizes, USTAR
   members, and content-manifest hashes.
4. Add an exact `catalogEntry` only after exact-device acceptance; the entry
   contains only `iosVersion`, `buildID`, and `baseAssetID`.
5. Commit the catalog, every newly referenced archive, README, and scripts in
   one `release` commit, then run the exact-device TSS/mount/probe/cleanup
   acceptance before declaring that entry verified.

PulsePhone deliberately fetches the direct catalog and archive URLs. It does
not call the GitHub Tree API or infer a nearest OS/build match. A cached valid
catalog and verified asset remain usable when this source is unavailable.
