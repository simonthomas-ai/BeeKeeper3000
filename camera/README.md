# Local camera and ONNX inference (experimental)

This optional module is the first local producer for the BeeKeeper3000 source API. It captures a USB camera, local video file or RTSP/HTTP stream using OpenCV, runs a documented ONNX object-detection graph on the CPU, and queues **metadata only** for the local source API. It does not upload, persist or log frames, thumbnails, audio, camera URLs, GPS coordinates or model tensors.

## Safety and readiness boundary

- Every observation is emitted as a candidate in the existing strict source API schema. The Monitor adapter continues to mark it unverified. No automatic species confirmation, nest localization or extermination decision is made.
- No model weights or datasets are included. The example manifest is deliberately invalid (placeholder hash and unreviewed license state) and cannot start inference.
- Before running a model, record the original artifact URL, immutable version/hash, actual SPDX license, redistribution/training rights and an explicit license review in a local manifest. Nonprofit intent does not override NC/ND terms or missing permissions.
- Only a model with license_review_status set to approved or public-domain passes the technical gate. This field records an operator review; it is not legal advice or automatic proof of rights.
- The graph must emit three named outputs: normalized xyxy boxes after model-side NMS, scores in 0..1 and integer class IDs. Preprocessing is fixed RGB, NCHW, float32 0..1, stretch resize. Models with other signatures need an adapter and tests; do not guess tensor order.
- Experimental model output remains unverified. Do not use this pipeline for nest destruction, trapping, pesticide use or other irreversible action.

## Install (Python 3.11+)

From BeeKeeper3000 repository root:

~~~powershell
python -m venv .venv-camera
.\.venv-camera\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r camera/requirements.txt
~~~

Linux:

~~~sh
python3 -m venv .venv-camera
. .venv-camera/bin/activate
python -m pip install --upgrade pip
python -m pip install -r camera/requirements.txt
~~~

The inference runtime is CPU-only. ONNX Runtime is MIT; opencv-python-headless is Apache-2.0. These are optional direct dependencies, not a complete transitive SBOM. Re-audit and pin transitive packages for each target platform before a release.

## Configure

Copy camera/model-manifest.example.json to a local, private file next to the ONNX model and replace every placeholder with verified source data. The model path must remain beneath the manifest directory. Generate its hash locally:

~~~powershell
Get-FileHash .\models\your-model.onnx -Algorithm SHA256
~~~

Set environment variables in the same terminal. Do not store real credentials in scripts, source control or command-line arguments:

~~~powershell
$env:BEEKEEPER_MODEL_MANIFEST = 'C:\secure\beekeeper\model-manifest.json'
$env:BEEKEEPER_CAMERA_SOURCE = '0' # USB camera index; or local file / rtsp(s):// URL
$env:HORNET3000_STATION_ID = 'station-01'
$env:HORNET3000_API_KEY = '<locally provisioned source API key>'
$env:HORNET3000_URL = 'http://127.0.0.1:8787'
$env:BEEKEEPER_CAMERA_OUTBOX = "$env:LOCALAPPDATA\BeeKeeper3000\data\camera-outbox.sqlite3"
$env:BEEKEEPER_CAMERA_MAX_FPS = '5'
$env:BEEKEEPER_CAMERA_COOLDOWN_SECONDS = '30'
python -m camera.runtime
~~~

The source URL is restricted to loopback (127.0.0.1, ::1 or localhost) in this first release. The camera source is local configuration; do not paste RTSP credentials into tickets or logs. Start the base station services separately with scripts/Start-BeeKeeperStation.ps1.

## Offline queue and failure behaviour

- Detections are stored in a private local SQLite outbox before network delivery.
- Events are removed only after the source API returns HTTP 200 or 201.
- Temporary connection failures leave queued events intact and capture continues.
- A full bounded outbox stops the runtime rather than silently dropping observations.
- A stable event ID cannot be reused with changed payload content.
- Camera reconnect uses capped exponential backoff. Processing is CPU-bounded by configurable FPS and ONNX worker threads.
- Raw images are held only in process memory for inference and are not retained by this module.

Windows NTFS ACLs must be restrictive; Linux/macOS directories are mode 0700 and database files mode 0600. SQLite is not application-encrypted: use BitLocker or an encrypted volume. The outbox is a separate database and must be included in a future full station backup/restore drill before deployment.

## Tests

~~~sh
python -m unittest discover -s camera -p 'test_*.py' -v
~~~

Tests use synthetic metadata and fake components. They do not establish camera compatibility, model quality, ONNX model signature compatibility, field performance or GDPR compliance. Verify on the exact camera, stream, PC and model before any pilot.
