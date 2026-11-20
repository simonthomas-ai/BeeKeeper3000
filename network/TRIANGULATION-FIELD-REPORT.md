# Known-target triangulation field evidence

This report tool compares each measured station bearing with a surveyed, known target and evaluates the solver's estimated position and reported 95% uncertainty ellipse.

It is a **measurement-analysis tool**, not a radio test and not an approval process. It never changes station calibration values or automatically marks the solver safe for operational use.

## Safety and privacy before recording

- Use targets whose coordinates were surveyed independently and whose position is safe to use for controlled tests.
- Keep the input CSV on an encrypted local disk with access limited to the test team. It contains precise coordinates of stations and test targets.
- Do not commit the completed CSV, station locations, target coordinates, private camera URLs, radio keys or exact apiary locations to GitHub.
- Use pseudonymous `trial_id` and `station_id` values. Do not use names, addresses or phone numbers.
- The JSON output deliberately excludes coordinates. Treat it as operationally sensitive anyway: station identifiers and measured error distributions may reveal deployment characteristics.
- A station ID represents one fixed sensor, mount, alignment and calibration state. If a compass, camera, mount, antenna support or physical orientation changes, use a new station ID or calibration epoch.

## CSV format

Start with `network/field-test-template.csv`. Each row is one station bearing to the same surveyed target for one trial. A trial must contain at least three independent station IDs.

Required columns, in exact order:

```csv
trial_id,station_id,station_latitude,station_longitude,azimuth_deg,sigma_deg,observed_at,target_latitude,target_longitude
```

- `trial_id`: pseudonymous ID for one known-target trial.
- `station_id`: pseudonymous sensor/mount/calibration identity; unique within a trial.
- `station_latitude`, `station_longitude`: surveyed station location.
- `azimuth_deg`: measured bearing, clockwise from **true north**, in degrees [0, 360).
- `sigma_deg`: independently calibrated one-standard-deviation uncertainty for the complete sensor/mount/operator chain, from 0.5 to 45 degrees.
- `observed_at`: ISO-8601 timestamp with timezone, preferably UTC.
- `target_latitude`, `target_longitude`: surveyed reference-target coordinates. All rows within a trial must have the same target.

Use at least 30 known-target trials across the intended operational range. Include different azimuths and distances, good and adverse intersection geometry, relevant weather/lighting, and controlled bearing perturbations. Do not enter fabricated or inferred values as field measurements.

## Run locally

From the BeeKeeper3000 repository root:

```sh
python -m network.triangulation_field_report /secure/local/known-targets.csv \
  --minimum-trials 30 \
  --max-time-delta-sec 1800 \
  --output /secure/local/field-report.json
```

To print the report to the terminal instead, omit `--output` or set it to `-`. The tool refuses to overwrite an existing report file. It does not upload the CSV or report.

Exit codes:
- `0`: at least the minimum number of trials and enough evidence to request expert review only.
- `2`: the number of known-target trials is below the configured minimum, or calibration review is required.
- `1`: invalid input or a file/report error.

## Report contents

- Successful estimates and solver failures by pseudonymous trial ID.
- Horizontal ground-truth error median, p95 and maximum.
- Whether the surveyed target falls inside each estimated 95% ellipse.
- Observed ellipse hit-rate and Wilson 95% confidence interval.
- Per-station circular azimuth bias, circular standard deviation, p95 absolute angular error, declared sigma and normalized RMS sigma.

The solver-failure count is reported separately. Failed trials do not enter the ellipse-coverage denominator; always assess solver failure rate together with coverage and position error. A result of `enough_samples_for_expert_review_only` is not a pass: the JSON decision remains `not_approved_for_operational_use`.

The current ellipse is a local linearized approximation. Thirty or more trials are a minimum evidence sample, not proof that all 95% coverage assumptions hold. An independent expert must review measurement methodology, station independence, coordinate survey quality, error distribution, geometry and confidence intervals.

## What this does not test

The tool evaluates bearings supplied in CSV. It does not validate MeshCore packet delivery, antenna direction-finding hardware, RF range, interference, clock synchronization beyond timestamp-window checks, legal radio parameters, or the detector's biological classification quality. Those require separate hardware and field acceptance.
