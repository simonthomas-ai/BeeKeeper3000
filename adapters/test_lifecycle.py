import asyncio
import unittest

from adapters.lifecycle import (
    AdapterConfigurationError,
    AdapterPermissionDenied,
    AdapterSpec,
    AdapterState,
    AdapterSupervisor,
    AdapterTransientError,
    retry_delay_seconds,
    safe_diagnostic,
    validate_metadata_event,
)


class FakeAdapter:
    def __init__(self, *, stop_event=None):
        self.stop_event = stop_event
        self.discover_calls = 0
        self.start_calls = 0
        self.stop_calls = 0
        self.read_calls = 0
        self.fail_first_discovery = False
        self.granted = True
        self.available = True
        self.event = {"event_id": "evt-000000000001", "candidate_taxon": "unknown"}

    async def discover(self):
        self.discover_calls += 1
        if self.fail_first_discovery and self.discover_calls == 1:
            return False
        return True

    async def capabilities(self):
        return {"camera": self.available, "manual_report": True}

    async def permissions(self):
        return {"camera": self.granted, "location": True}

    async def start(self):
        self.start_calls += 1

    async def read_event(self, timeout_seconds):
        self.read_calls += 1
        if self.stop_event is not None:
            self.stop_event.set()
        return self.event

    async def health(self):
        return {"healthy": True, "detail": "private source details are never logged"}

    async def stop(self):
        self.stop_calls += 1


class AdapterLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def spec(self, **kwargs):
        return AdapterSpec(
            adapter_id="camera.uvc",
            version="1.0.0",
            source_type="camera",
            required_capabilities=("camera",),
            required_permissions=("camera",),
            **kwargs,
        )

    async def test_happy_path_discovers_checks_permissions_and_stops(self):
        stop = asyncio.Event()
        adapter = FakeAdapter(stop_event=stop)
        supervisor = AdapterSupervisor(self.spec(), adapter, jitter_fraction=0)
        seen = []
        await supervisor.run_once(lambda event: seen.append(event), stop)
        self.assertEqual(supervisor.state, AdapterState.STOPPED)
        self.assertEqual(adapter.discover_calls, 1)
        self.assertEqual(adapter.start_calls, 1)
        self.assertEqual(adapter.stop_calls, 1)
        self.assertEqual(seen, [adapter.event])

    async def test_permission_denial_fails_before_start(self):
        stop = asyncio.Event()
        adapter = FakeAdapter(stop_event=stop)
        adapter.granted = False
        supervisor = AdapterSupervisor(self.spec(), adapter)
        with self.assertRaises(AdapterPermissionDenied):
            await supervisor.run_once(lambda event: None, stop)
        self.assertEqual(adapter.start_calls, 0)
        self.assertEqual(adapter.stop_calls, 0)
        self.assertEqual(supervisor.state, AdapterState.FAILED)

    async def test_missing_capability_fails_before_start(self):
        stop = asyncio.Event()
        adapter = FakeAdapter(stop_event=stop)
        adapter.available = False
        supervisor = AdapterSupervisor(self.spec(), adapter)
        with self.assertRaises(AdapterConfigurationError):
            await supervisor.run_once(lambda event: None, stop)
        self.assertEqual(adapter.start_calls, 0)

    async def test_sensitive_nested_event_is_rejected_and_adapter_is_stopped(self):
        stop = asyncio.Event()
        adapter = FakeAdapter(stop_event=stop)
        adapter.event = {"event_id": "evt-000000000001", "metadata": {"latitude": 51.0}}
        supervisor = AdapterSupervisor(self.spec(), adapter)
        with self.assertRaises(AdapterConfigurationError):
            await supervisor.run_once(lambda event: None, stop)
        self.assertEqual(adapter.stop_calls, 1)
        self.assertEqual(supervisor.state, AdapterState.FAILED)

    async def test_sensitive_camel_case_and_separator_variants_are_rejected(self):
        variants = (
            {"apiKey": "secret"},
            {"privateKey": "secret"},
            {"imageUrl": "https://example.invalid/image.jpg"},
            {"gpsCoordinates": [51.0, 7.0]},
            {"metadata": {"authorizationToken": "secret"}},
        )
        for event in variants:
            with self.subTest(event=event):
                with self.assertRaises(AdapterConfigurationError):
                    validate_metadata_event(event)

    async def test_stop_is_called_when_event_sink_fails(self):
        stop = asyncio.Event()
        adapter = FakeAdapter(stop_event=stop)
        supervisor = AdapterSupervisor(self.spec(), adapter)

        def broken_sink(event):
            raise RuntimeError("rtsp://user:password@example.invalid/private")

        with self.assertRaises(AdapterTransientError):
            await supervisor.run_once(broken_sink, stop)
        self.assertEqual(adapter.stop_calls, 1)

    async def test_lifecycle_timeout_is_bounded(self):
        class SlowAdapter(FakeAdapter):
            async def discover(self):
                await asyncio.sleep(1)
                return True

        stop = asyncio.Event()
        adapter = SlowAdapter(stop_event=stop)
        supervisor = AdapterSupervisor(
            self.spec(), adapter, operation_timeout_seconds=0.1
        )
        with self.assertRaises(AdapterTransientError) as raised:
            await supervisor.run_once(lambda event: None, stop)
        self.assertEqual(raised.exception.code, "adapter_operation_timeout")
        self.assertEqual(adapter.start_calls, 0)

    async def test_run_forever_reconnects_after_transient_discovery_failure(self):
        stop = asyncio.Event()
        adapter = FakeAdapter(stop_event=stop)
        adapter.fail_first_discovery = True
        supervisor = AdapterSupervisor(self.spec(), adapter, jitter_fraction=0)
        seen = []
        await supervisor.run_forever(
            lambda event: seen.append(event),
            stop,
            base_backoff_seconds=0.1,
            max_backoff_seconds=0.1,
            max_attempts=2,
        )
        self.assertEqual(adapter.discover_calls, 2)
        self.assertEqual(adapter.start_calls, 1)
        self.assertEqual(adapter.stop_calls, 1)
        self.assertEqual(len(seen), 1)

    async def test_diagnostics_do_not_include_exception_text_or_event_data(self):
        stop = asyncio.Event()
        adapter = FakeAdapter(stop_event=stop)
        adapter.event = {"event_id": "evt-000000000001", "latitude": 51.0}
        diagnostics = []
        supervisor = AdapterSupervisor(
            self.spec(), adapter, diagnostic_sink=lambda item: diagnostics.append(item)
        )
        try:
            await supervisor.run_forever(
                lambda event: None, stop, base_backoff_seconds=0.1,
                max_backoff_seconds=0.1, max_attempts=1
            )
        except AdapterConfigurationError:
            pass
        self.assertEqual(len(diagnostics), 1)
        self.assertNotIn("latitude", str(diagnostics))
        self.assertNotIn("private", str(diagnostics))
        self.assertEqual(diagnostics[0]["code"], "configuration_error")

    def test_event_contract_rejects_raw_media_secrets_and_exact_location(self):
        bad_events = [
            {"image_bytes": 123},
            {"image_url": "https://images.example.invalid/photo.jpg"},
            {"audio": "raw"},
            {"video_bytes": 123},
            {"media_url": "https://images.example.invalid/source"},
            {"gps": {"latitude": 51.0}},
            {"authorization": "Bearer secret"},
            {"payload": {"longitude": 7.0}},
        ]
        for event in bad_events:
            with self.subTest(event=event):
                with self.assertRaises(AdapterConfigurationError):
                    validate_metadata_event(event)

    def test_event_contract_enforces_json_and_size_limits(self):
        with self.assertRaises(AdapterConfigurationError):
            validate_metadata_event({"value": float("nan")})
        with self.assertRaises(AdapterConfigurationError):
            validate_metadata_event({"value": "x" * (65 * 1024)})

    def test_retry_backoff_is_capped_and_jitter_is_bounded(self):
        self.assertAlmostEqual(
            retry_delay_seconds(1, base_seconds=1, max_seconds=8,
                                jitter_fraction=0.2, random_value=-1),
            0.8,
        )
        self.assertAlmostEqual(
            retry_delay_seconds(2, base_seconds=1, max_seconds=8,
                                jitter_fraction=0.2, random_value=1),
            2.4,
        )
        self.assertLessEqual(
            retry_delay_seconds(100, base_seconds=1, max_seconds=8,
                                jitter_fraction=0.2, random_value=1),
            8,
        )
        with self.assertRaises(ValueError):
            retry_delay_seconds(0)

    def test_safe_diagnostic_is_allowlisted(self):
        spec = self.spec()
        record = safe_diagnostic(
            spec, AdapterState.FAILED, "device_disconnected",
            attempt=3, elapsed_ms=245
        )
        self.assertEqual(
            set(record),
            {"adapter_id", "state", "code", "attempt", "elapsed_ms"},
        )
        self.assertNotIn("message", record)
        self.assertNotIn("source", record)


if __name__ == "__main__":
    unittest.main()
