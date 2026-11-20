# Camera and detector acceptance protocol

Status: **not yet accepted on physical hardware**. The local pipeline is an executable software adapter, not a claim that any particular camera, RTSP stream or detector model works.

## 1. Configuration and provenance gate

Before camera startup:

- Record camera make/model, firmware, connection type, resolution, frame rate and whether the stream is local-only.
- Record ONNX model source URL, immutable release/commit, file SHA-256, SPDX license, weight redistribution terms, training dataset provenance and every image/annotation license.
- Confirm that the local model manifest records a completed license review. A model repository's code license does not automatically license weights or images.
- Verify tensor names, input dimensions, color/layout/normalization and output semantics on the exact ONNX file. Output boxes must be normalized xyxy after NMS; scores must be in 0..1; class IDs must map to documented labels.
- Store model artifacts and manifests outside the public repository unless their redistribution licenses clearly allow that.

## 2. Camera acquisition test

Use a dedicated test station and a non-production camera account. Capture both representative day/night conditions and difficult cases (motion blur, rain, glare, background clutter, multiple insects, partial occlusion).

Record for at least a continuous 2-hour run:

- successful open and first-frame time;
- frame rate, frame age and dropped-frame rate;
- reconnect count and recovery time after camera/network interruption;
- CPU, memory and thermal behavior;
- whether camera authentication data appears in process logs, crash dumps or diagnostics;
- confirmation that no image/audio/GPS file is created by the pipeline and no media bytes leave the local host.

Repeat with a physically disconnected camera and with the local source API unavailable. The process must reconnect with bounded backoff; queued metadata must remain until acknowledged. A full outbox must stop the process visibly rather than discard a record.

## 3. Detection-quality evaluation

Do not use random frame-level splits. Group images by observation, photographer, hive/site, camera and capture period so near-duplicates do not leak across training and test sets. Maintain a separately held-out field test set.

Report separately for Vespa velutina, Vespa crabro, other Vespa, Vespula/Dolichovespula, Apis, Bombus, hoverflies and unknown/other:

- precision, recall, F1, per-class confusion matrix and 95% confidence intervals;
- false positive events per camera-day / hive-day;
- false negative cases under low light, occlusion and small-object conditions;
- unknown/open-set rejection behavior;
- confidence calibration and threshold selection on validation data only;
- end-to-end inference latency, CPU and memory at target resolution/FPS.

A generic accuracy percentage is not an acceptance metric. A model cannot be promoted because a training or validation score looks high. Independent reviewers must manually adjudicate the held-out images, especially velutina-vs-crabro confusions. No destructive control action may depend solely on an automated classification.

## 4. Software integration and recovery

On a dedicated test system:

1. Start the source API, monitor receiver and bridge.
2. Start the camera worker with a reviewed model manifest.
3. Verify candidate events in the local source journal and Monitor PWA.
4. Stop the source API during capture, allow the outbox to accumulate events, then restore the API and verify eventual delivery exactly once in the Monitor store.
5. Restart the camera worker and PC; confirm the outbox survives process restarts and no accepted event reappears as a duplicate.
6. Fill a disposable outbox to its configured limit and verify that the runtime stops without deleting pending events.
7. Create a complete backup, verify hashes, restore the source, Monitor and camera databases to new paths, and replay only in the isolated test environment.

## 5. Go/no-go

A camera/model combination is **pilot-ready only after** all sections above have evidence files, a reviewed model card, completed license register, successful recovery drill and independent field evaluation. Until then, keep inference status experimental, detections unverified and external outreach disabled.
