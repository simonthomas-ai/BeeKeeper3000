# MeshCore hardware probe

The signed MeshCore protocol, receiver, serial transport and synthetic tests are
present. No real radio, antenna, repeater, companion firmware or RF environment
has been field-validated. This utility supports controlled initial checks.

## Safety modes

Default mode is a dry run: it reads an owner-only Ed25519 private key, builds
one synthetic five-minute station_heartbeat, signs it and reports payload size.
It does not open a serial port and does not transmit.

The --probe option opens and closes the companion radio serial connection but
does not transmit. Use this first to validate USB/serial connectivity and
compatible companion firmware.

The --transmit-test-packet option requires --probe and sends exactly one signed
synthetic heartbeat. It contains no GPS, photo, audio, free text or personal
data. It is unverified, uses taxon unknown and confidence zero. It is not a
hornet detection and must not be counted as a biological event.

## Examples

After installing the optional MeshCore requirements:

    # Dry run only — no serial port opened and no transmission
    python -m network.meshcore.hardware_probe --port COM5 --station-id station-west --signing-key C:\Secure\station-ed25519.pem

    # Serial connection only — no packet sent
    python -m network.meshcore.hardware_probe --port COM5 --station-id station-west --signing-key C:\Secure\station-ed25519.pem --probe

    # Send one signed heartbeat only after selecting an authorised test channel
    python -m network.meshcore.hardware_probe --port COM5 --station-id station-west --signing-key C:\Secure\station-ed25519.pem --channel 0 --probe --transmit-test-packet

On Linux a typical serial path is /dev/ttyUSB0 or /dev/ttyACM0. The service
account must own the key file and POSIX permissions must be 0600 or stricter.
Do not copy a production signing key to a test station; provision a separate
test identity and receiver allowlist.

A local send receipt confirms only that the local MeshCore API accepted the
send command. It does not prove remote reception. For a real field test, record
the matching event ID at a second station with the sender's public key and
station-key mapping provisioned. Record send/receive timestamps, channel,
firmware versions, antenna/site IDs, RSSI/SNR if exposed, retries/loss and
legal radio settings. Keep coordinates and logs private.

Before transmission, confirm selected device, frequency, channel width, EIRP,
antenna gain, duty cycle, firmware mode and regional rules. This tool does not
certify legal compliance. It sends only one packet, not a coverage benchmark.
