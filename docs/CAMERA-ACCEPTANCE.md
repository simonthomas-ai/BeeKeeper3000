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

The network/file capture adapter requests 5-second open and read timeouts through OpenCV's FFmpeg backend. Record the actual OpenCV version/backend and confirm observed timeout behaviour with the target camera firmware; library timeout settings are not a substitute for a physical disconnect/reconnect test.

Use a dedicated test station and a non-production camera account. Capture both representative day/night conditions and difficult cases (motion blur, rain, glare, background clutter, multiple insects, partial occlusion).

Record for at least a continuous 2-hour run:

- successful open and first-frame time;
- frame rate, frame age and dropped-frame rate;
- reconnect count and recovery time after camera/network interruption;
- CPU, memory and thermal behavior;
- whether camera authentication data appears in process logs, crash dumps or diagnostics;
- confirmation that no image/audio/GPS file is created by the pipeline and no media bytes leave the local host.

Repeat with a physically disconnected camera and with the local source API unavailable. The process must reconnect with bounded backoff; queued metadata must remain until acknowledged. A full outbox must stop the process visibly rather than discard a record.

## Windows one-frame hardware check

Run from the repository checkout with the camera dependencies installed in a dedicated environment:

```powershell
.\scripts\Test-BeeKeeperCamera.ps1 -PythonExe ".\.venv-camera\Scripts\python.exe"
```

The script prompts for the camera index (for example `0`) or the complete local RTSP(S)/HTTP(S) URL using hidden input. It passes the source only through a temporary process environment variable, never as a command-line argument, clears it afterwards, reads one frame, releases the camera and saves no image. The diagnostic does not need a model to prove that the capture backend returns a frame.

The station doctor also checks the base station, bridge and optional model configuration. Its overall exit code can therefore be non-zero even if the separate `Live camera test` row passes. Review that row and all other failures independently.

For Reolink or another network camera, enable its RTSP service in the camera's own settings, use a dedicated least-privilege camera account, and enter the correct stream path for the exact model/firmware. Do not paste a credential-bearing RTSP URL into issues, chat, screenshots or logs. A successful one-frame read is only a connection smoke test; complete the two-hour acquisition, disconnect/reconnect, privacy and field-quality checks above before any pilot.

### Reolink RLC-510WA RTSP/ONVIF check

Reolink currently lists the RLC-510WA among its plug-in Wi-Fi/RLC cameras with standalone RTSP and ONVIF support. In Reolink Client, check **Device Settings → Network → Advanced → Server Settings**; enable RTSP and save. The default RTSP port is 554. Reolink's documented stream path format for a standalone camera is `/Preview_01_main` (main stream) or `/Preview_01_sub` (sub stream).

On Windows, first check local TCP reachability without entering credentials:

```powershell
Test-NetConnection -ComputerName CAMERA_IP -Port 554
```

Then run the hidden-input one-frame test:

```powershell
.\scripts\Test-BeeKeeperCamera.ps1 -PythonExe ".\.venv-camera\Scripts\python.exe"
```

Enter the full RTSP URL only at the hidden prompt, using the actual camera username/password and IP, for example the documented structure `rtsp://USER:PASSWORD@CAMERA_IP:554/Preview_01_main`. Do not put the credential-bearing URL into PowerShell commands, shell history, issues or logs. Do not port-forward RTSP to the Internet. If the TCP test fails, resolve the camera's port setting, local network path or firewall before debugging ONNX inference.

Official references:
- [Reolink: supported RTSP/ONVIF products](https://support.reolink.com/articles/900000617826-Which-Reolink-Products-Support-CGI-RTSP-ONVIF/)
- [Reolink: RTSP URL format](https://support.reolink.com/articles/900000630706-Introduction-to-RTSP/)
- [Reolink: port settings](https://support.reolink.com/articles/900000621783-How-to-Configure-Reolink-Ports-Settings/)

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
