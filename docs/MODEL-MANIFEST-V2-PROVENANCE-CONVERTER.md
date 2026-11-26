# Model-manifest v2 provenance converter

**Status: implemented as a local, fail-closed conversion tool; not a model or training approval.**

The converter consumes a local ZIP that already satisfies the BeeKeeper3000 multi-label dataset validator and a separate source-rights review JSON file. It emits:

- provenance.jsonl: one model-manifest v2 provenance row per image.
- training_data_sources.json: the matching training_data_sources array for a future manifest.

It does not download sources, read consent documents, upload images, train, run inference, create model weights, or activate a camera model. The CLI summary explicitly keeps the AI status BLOCKED.

## Why a second review file is mandatory

The field ZIP contains a user attestation (rights.status=training_approved) and a manual image/label review (reviewed_by, reviewed_at). Neither proves source-level legal rights. The converter never copies that attestation into license_review_status.

The separate source-rights review file must be prepared through the project's independent rights-review process. It records only an opaque reviewer ID, a timezone-aware review timestamp, the source/license/revision tuple, and explicit permissions. This is still an operator-supplied review record, not cryptographic proof, legal advice, or an independent external verification by the converter.

The source-rights reviewer ID must differ from the per-image label reviewer ID for every image. The converter rejects missing, unknown, duplicate, ambiguous, unreferenced, unsupported, or incomplete review records.

## Source-review file format

Use a UTF-8 JSON file with unique keys and this top-level shape:

~~~json
{
  "format_version": 1,
  "sources": [
    {
      "source_url": "https://example.org/dataset/photo-001",
      "revision": "0123456789abcdef0123456789abcdef01234567",
      "license": "CC-BY-4.0",
      "license_review_status": "approved",
      "license_evidence_url": "https://creativecommons.org/licenses/by/4.0/",
      "training_use_allowed": true,
      "redistribution_allowed": false,
      "reviewed_by": "reviewer:source-reviewer-01",
      "reviewed_at": "2026-11-21T09:00:00Z",
      "review_kind": "source_rights"
    },
    {
      "source_url": "local-capture://session-0001",
      "license": "LicenseRef-ExplicitPermission",
      "license_review_status": "approved",
      "license_evidence_url": null,
      "training_use_allowed": true,
      "redistribution_allowed": false,
      "reviewed_by": "reviewer:source-reviewer-02",
      "reviewed_at": "2026-11-21T09:30:00Z",
      "review_kind": "source_rights"
    }
  ]
}
~~~

Rules:

- Public sources require credential-free HTTPS without query strings or fragments, an immutable full Git commit SHA or SHA-256 archive digest, and the canonical CC0/CC-BY evidence URL.
- CC-BY requires per-image attribution in the original field annotation.
- public-domain review status is accepted only for CC0-1.0; otherwise use approved.
- Local field captures require local-capture://<opaque-session-id>, LicenseRef-ExplicitPermission, approved, a null evidence URL, and an opaque per-image permission_ref.
- For local captures the converter derives revision as sha256:<digest-of-the-exact-validated-ZIP-snapshot>. Do not supply a revision in the local source-review entry.
- Local session IDs must be opaque, 8–80 character identifiers using only letters, digits, dot, underscore, or hyphen.
- training_use_allowed must be the literal boolean true; redistribution must be an explicit boolean.
- Names, email addresses, URLs, private consent documents, GPS coordinates, device paths, and arbitrary extra fields are not accepted as reviewer metadata.

## Local command

Run from the BeeKeeper3000 repository root with already approved local files:

~~~powershell
python -m training.build_provenance --archive "D:\field-data\reviewed-export.zip" --source-review "D:\field-data\source-rights-review.json" --output-dir "D:\field-data\manifest-provenance"
~~~

The archive is copied to a bounded private temporary snapshot, hashed, and that exact snapshot is passed to the existing ZIP validator. The converter then uses the validator's hashes, which are calculated from the extracted image bytes. A changed or replaced source archive is rejected. The output directory must not already exist; existing files are never overwritten.

The converter enforces the model-manifest provenance row, line, source-count, and byte limits. It emits only the minimum provenance fields and the separate source list. It does not copy captured_at, capture_session_id, labeler_id, arbitrary rights fields, raw consent material, or GPS/device metadata into per-image provenance.

## CI and acceptance

training.test_build_provenance uses synthetic byte fixtures only. It tests:

- local explicit permission with archive-bound SHA-256 revision;
- public CC0 and CC-BY source review and immutable revisions;
- distinct image-review and source-rights reviewer IDs;
- deterministic output;
- missing or incomplete source review, unknown fields, duplicate JSON keys, invalid revision, mismatched local/public license use, unreferenced source rows, unsafe archive paths, and output overwrite prevention;
- round-trip acceptance by camera.model_manifest.load_manifest.

A successful converter run proves only that the submitted metadata satisfies the technical contract. It does not verify the truth of a source-rights review, species identification, image quality, consent, or legal ownership. Real data remain blocked until the separate rights review, expert annotations, full dataset approval, and independent model evaluation are complete.
