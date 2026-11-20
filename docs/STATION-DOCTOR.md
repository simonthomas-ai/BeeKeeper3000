# BeeKeeper station preflight

The preflight is a read-only diagnostic for the two-repository station reference implementation. It checks repository files, Python/Node versions, bridge cursor safety, local service APIs, and an optional model manifest. It does not install software, create secrets, alter databases, send detections, download data, or change services.

Run from the BeeKeeper3000 repository root:

## Windows PowerShell

~~~powershell
python .\scripts\station_doctor.py --monitor-repo ..\Beekeeper-Monitor
~~~

## Linux

~~~sh
python3 scripts/station_doctor.py --monitor-repo ../Beekeeper-Monitor
~~~

The source API and Monitor checks use read-only GET requests to literal loopback IP addresses only (`127.0.0.0/8` or `::1`); DNS hostnames such as `localhost` are rejected to avoid DNS rebinding. HTTP redirects are not followed. To verify authenticated reads, run the doctor in a shell that has the correct secret environment variables loaded. The values are never printed:

- \`HORNET3000_API_KEY\`
- \`BEEKEEPER_MONITOR_INGEST_TOKEN\` or \`VESPAGUARD_INGEST_TOKEN\`

Set \`BRIDGE_REQUIRE_CURSOR=true\` and a persistent \`BRIDGE_STATE_FILE\` for the bridge configuration check. The doctor deliberately fails when the lossy latest-only compatibility mode is enabled.

## Optional checks

Model manifest and ONNX CPU runtime:

~~~powershell
python .\scripts\station_doctor.py --model-manifest "$env:LOCALAPPDATA\BeeKeeper3000\models\manifest.json"
~~~

One-frame camera check (explicit opt-in; set the source in the environment so RTSP credentials do not appear in shell history or process arguments):

~~~powershell
$env:BEEKEEPER_CAMERA_SOURCE = "0"
python .\scripts\station_doctor.py --test-camera
~~~

Connect-only MeshCore hardware check (explicit opt-in; no packet transmitted):

~~~powershell
python .\scripts\station_doctor.py --probe-radio --radio-port "COM5" --station-id "station-test" --signing-key "C:\Secure\meshcore-test-ed25519.pem"
~~~

The radio check uses a dedicated test identity. It only opens and closes the serial connection. It never sends the hardware-probe heartbeat. Use a private key created solely for testing and follow the radio manufacturer's and national frequency/power requirements.

## Result interpretation

- \`PASS\`: the check was verified in this execution.
- \`WARN\`: optional hardware/model configuration is absent or authentication could not be verified because the secret was not available to this shell.
- \`FAIL\`: a required file, version, local service contract, path or enabled safety setting is invalid.

Exit code 1 means at least one FAIL. WARN-only runs exit 0 but are not a field-acceptance certificate. A successful software preflight does not prove radio range, camera classification quality, triangulation accuracy, GDPR compliance, or successful field operation. Test the real station and documented acceptance plan before deployment.
