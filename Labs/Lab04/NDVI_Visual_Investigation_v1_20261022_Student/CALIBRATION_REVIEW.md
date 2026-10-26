# Calibration review for the preserved Lab 3 example

The bundled data are actual Sentinel-2 L2A subsets for
`S2C_34UDA_20250605_0_L2A`, AOI [19.91, 50.04, 19.94, 50.06]. They retain their
original Lab 3 bytes and checksums. No input file or historical metadata is changed.

The captured STAC item contains `earthsearch:boa_offset_applied: true`, while its
COG asset records declare scale 0.0001 and offset -0.1. Lab 3 copied those asset
values into the subset headers. Those statements deserve investigation together.

The provider's issue tracker describes metadata
inconsistencies in this legacy collection, including 2025 examples (See sources below). 
Its general collection notes still advise using nonzero asset offsets, so those notes 
alone do not resolve the conflicting evidence for these particular files.

The generated configuration therefore says `scaling: reviewed_calibration` and
stores the scale, offset, evidence statement and exact SHA-256 for each band.
The original asset metadata and raster headers remain in the input records. Both
the original values and the explicit interpretation enter request identity. An
attempt using the known conflicting `asset_metadata` interpretation fails with a
useful error. The recorded review cannot be applied to a different input hash.

For other scenes, `configure` initially uses `asset_metadata` and does not invent a
calibration review. Verify the representation you actually acquired. If evidence
conflicts, stop, retain it, and document a justified review before processing.
Do not assume this example establishes offset 0 for all Sentinel-2 data.

This makes a useful discussion: the program can run exactly as written and still
be scientifically wrong. Checksums establish which bytes you used; source metadata
and an explicit calibration interpretation establish how you used them.

Sources checked 22 October 2026:

- Captured provider item: `fixtures/real_catalogue.json`; subset plans/checksums:
  `fixtures/aoi_manifest.json`.
- [Element 84 collection notes](https://github.com/Element84/earth-search/blob/main/docs/collections/sentinel-2-l2a.md).
- [Element 84 issue 66: inconsistent offset flags](https://github.com/Element84/earth-search/issues/66).
- [Element 84 issue 24: offset and collection transition](https://github.com/Element84/earth-search/issues/24).

The repair check deliberately also tests the general nonzero-offset formula using
the original metadata. A correct calculation function must apply the interpretation
passed to it; it must not hard-code offset 0 to make this particular image look right.
