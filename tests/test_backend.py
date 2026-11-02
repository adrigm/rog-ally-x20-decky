"""Contract and lifecycle tests never write to real audio or display hardware."""

import asyncio
import copy
from pathlib import Path
import sys
import threading
import traceback
from types import SimpleNamespace
import unittest
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py_modules"))

from ally_system_control.controller import SystemController
from ally_system_control.errors import ControlFailure
from ally_system_control.windows.audio import WindowsAudioAdapter
from ally_system_control.windows.brightness import nearest_level, select_monitor, WindowsBrightnessAdapter
from ally_system_control.worker import ControlWorker


class FakeAdapter:
    def __init__(self, control, block=None):
        self.control = control
        self.block = block
        self.started = threading.Event()
        self.calls = []
        self.open_thread = None
        self.close_thread = None
        self.read_threads = []
        self.writes = []
        self.closed = False
        if control == "audio":
            self.state = {"available": True, "volume": 42.0, "muted": False,
                          "device_id": "speakers", "device_name": "Speakers", "error": None}
        else:
            self.state = {"available": True, "percent": 60, "levels": [0, 20, 40, 60, 80, 100],
                          "instance_name": "panel", "error": None}

    def open(self):
        self.open_thread = threading.get_ident()

    def read(self, cancelled=None):
        self.calls.append("read")
        self.read_threads.append(threading.get_ident())
        self.started.set()
        if self.block:
            self.block.wait(2)
        return copy.deepcopy(self.state)

    def set_volume(self, percent, expected_device_id, cancelled=None):
        if self.state["device_id"] != expected_device_id:
            raise ControlFailure("device_changed", "Changed")
        if cancelled is not None and cancelled.is_set():
            raise ControlFailure("operation_failed", "Cancelled")
        self.writes.append(("volume", percent))
        self.state["volume"] = percent
        return copy.deepcopy(self.state)

    def set_mute(self, muted, expected_device_id, cancelled=None):
        if self.state["device_id"] != expected_device_id:
            raise ControlFailure("device_changed", "Changed")
        self.writes.append(("muted", muted))
        self.state["muted"] = muted
        return copy.deepcopy(self.state)

    def set_brightness(self, percent, expected_instance_name, cancelled=None):
        if self.state["instance_name"] != expected_instance_name:
            raise ControlFailure("device_changed", "Changed")
        actual = nearest_level(percent, self.state["levels"])
        self.writes.append(("brightness", actual))
        self.state["percent"] = actual
        return copy.deepcopy(self.state)

    def close(self):
        self.closed = True
        self.close_thread = threading.get_ident()


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.audio = FakeAdapter("audio")
        self.brightness = FakeAdapter("brightness")
        self.controller = SystemController(lambda: self.audio, lambda: self.brightness, timeout=0.4)

    async def asyncTearDown(self):
        await self.controller.close()

    async def test_read_state_and_separate_thread_ownership(self):
        state = await self.controller.get_state()
        self.assertEqual(state["audio"]["volume"], 42)
        self.assertEqual(state["brightness"]["percent"], 60)
        self.assertTrue(state["updated_at"].endswith("Z"))
        self.assertEqual(self.audio.open_thread, self.audio.read_threads[0])
        self.assertNotEqual(self.audio.open_thread, self.brightness.open_thread)
        self.assertEqual(self.audio.writes + self.brightness.writes, [])
        result = await self.controller.close()
        self.assertTrue(all(result.values()))
        self.assertEqual(self.audio.open_thread, self.audio.close_thread)
        self.assertEqual(self.brightness.open_thread, self.brightness.close_thread)

    async def test_invalid_inputs_are_structured_and_never_write(self):
        await self.controller.get_state()
        for invalid in (True, False, None, "12", float("nan"), float("inf"), -1, 101, 10 ** 1000):
            with self.subTest(invalid=repr(invalid)[:40]):
                state = await self.controller.set_volume(invalid, "speakers")
                self.assertEqual(state["audio"]["error"]["code"], "invalid_argument")
                self.assertTrue(state["audio"]["available"])
        for invalid in (1, 0, "false", None):
            state = await self.controller.set_mute(invalid, "speakers")
            self.assertEqual(state["audio"]["error"]["code"], "invalid_argument")
        state = await self.controller.set_brightness(50, None)
        self.assertEqual(state["brightness"]["error"]["code"], "invalid_argument")
        self.assertEqual(self.audio.writes + self.brightness.writes, [])

    async def test_independent_setters_never_read_the_other_control(self):
        state = await self.controller.set_volume(22, "speakers")
        self.assertFalse(state["brightness"]["available"])
        self.assertIsNone(state["brightness"]["percent"])
        await asyncio.gather(self.controller.set_mute(True, "speakers"),
                             self.controller.set_brightness(20, "panel"))
        self.assertEqual(self.audio.calls, [])
        self.assertEqual(self.brightness.calls, [])
        self.assertEqual(self.audio.state["volume"], 22)
        self.assertTrue(self.audio.state["muted"])
        self.assertEqual(self.brightness.state["percent"], 20)

    async def test_invalid_setter_does_not_start_workers(self):
        state = await self.controller.set_volume(float("nan"), "speakers")
        self.assertEqual(state["audio"]["error"]["code"], "invalid_argument")
        self.assertIsNone(self.audio.open_thread)
        self.assertIsNone(self.brightness.open_thread)
        self.assertIsNone(state["audio"]["volume"])

    async def test_slow_wmi_does_not_delay_audio_setter(self):
        release = threading.Event()
        brightness = FakeAdapter("brightness", release)
        audio = FakeAdapter("audio")
        controller = SystemController(lambda: audio, lambda: brightness, timeout=1.0)
        reading = asyncio.create_task(controller.get_state())
        try:
            while not brightness.started.is_set():
                await asyncio.sleep(0.001)
            state = await asyncio.wait_for(controller.set_volume(23, "speakers"), timeout=0.15)
            self.assertEqual(state["audio"]["volume"], 23)
            self.assertFalse(reading.done())
            self.assertEqual(brightness.calls, ["read"])
        finally:
            release.set()
            await reading
            await controller.close()

    async def test_old_read_cannot_replace_newer_confirmed_setter(self):
        read_started = asyncio.Event()
        release_read = asyncio.Event()
        old_state = copy.deepcopy(self.audio.state)
        new_state = dict(old_state, volume=75)

        async def scripted_call(method, *args):
            if method == "read":
                read_started.set()
                await release_read.wait()
                return copy.deepcopy(old_state)
            return copy.deepcopy(new_state)

        self.controller._audio.call = scripted_call
        reading = asyncio.create_task(self.controller.get_state())
        await read_started.wait()
        state = await self.controller.set_volume(75, "speakers")
        self.assertEqual(state["audio"]["volume"], 75)
        release_read.set()
        state = await reading
        self.assertEqual(state["audio"]["volume"], 75)

    async def test_busy_poll_preserves_confirmed_device_availability(self):
        await self.controller.get_state()

        async def busy_call(method, *args):
            raise ControlFailure("busy", "Queue full")

        self.controller._audio.call = busy_call
        state = await self.controller.get_state()
        self.assertTrue(state["audio"]["available"])
        self.assertEqual(state["audio"]["volume"], 42)
        self.assertIsNone(state["audio"]["error"])

    async def test_setters_return_effective_state_and_mute_is_independent(self):
        await self.controller.set_mute(True, "speakers")
        state = await self.controller.set_volume(22, "speakers")
        self.assertTrue(state["audio"]["muted"])
        self.assertEqual(state["audio"]["volume"], 22)
        state = await self.controller.set_brightness(52, "panel")
        self.assertEqual(state["brightness"]["percent"], 60)
        self.assertIsNone(state["brightness"]["error"])

    async def test_stale_identity_rejected_after_device_swap(self):
        await self.controller.get_state()
        self.audio.state["device_id"] = "headphones"
        state = await self.controller.set_volume(12, "speakers")
        self.assertEqual(state["audio"]["error"]["code"], "device_changed")
        self.assertEqual(self.audio.writes, [])
        state = await self.controller.get_state()
        self.assertEqual(state["audio"]["device_id"], "headphones")

    async def test_close_never_reapplies_values(self):
        await self.controller.get_state()
        await self.controller.close()
        state = await self.controller.set_volume(20, "speakers")
        self.assertFalse(state["audio"]["available"])
        self.assertEqual(self.audio.writes + self.brightness.writes, [])

    async def test_unknown_values_remain_null_on_failure(self):
        class Denied(FakeAdapter):
            def read(self, cancelled=None):
                raise PermissionError("Access denied")
        denied = Denied("brightness")
        controller = SystemController(lambda: FakeAdapter("audio"), lambda: denied)
        try:
            state = await controller.get_state()
            self.assertTrue(state["audio"]["available"])
            self.assertIsNone(state["brightness"]["percent"])
            self.assertEqual(state["brightness"]["error"]["code"], "access_denied")
        finally:
            await controller.close()


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_init_failure_retains_no_native_traceback(self):
        references = []
        opens = []

        class NativeResource:
            pass

        class FailedInitialization(FakeAdapter):
            def open(self):
                super().open()
                opens.append(1)
                resource = NativeResource()
                references.append(weakref.ref(resource))
                raise RuntimeError("initialization failed with local resource")

        worker = ControlWorker("test", lambda: FailedInitialization("audio"))
        try:
            for _ in range(3):
                try:
                    await worker.call("read")
                    self.fail("Expected initialization failure")
                except ControlFailure as exc:
                    self.assertEqual(exc.code, "operation_failed")
                    self.assertNotIn("open", [frame.name for frame in traceback.extract_tb(exc.__traceback__)])
                self.assertIsNone(references[0]())
            self.assertEqual(len(opens), 1)
        finally:
            await worker.close()

    async def test_native_exception_traceback_never_crosses_thread_boundary(self):
        class FailingAdapter(FakeAdapter):
            def read(self, cancelled=None):
                raise RuntimeError("native diagnostic detail")

        worker = ControlWorker("test", lambda: FailingAdapter("audio"))
        try:
            try:
                await worker.call("read")
                self.fail("Expected a structured error")
            except ControlFailure as exc:
                self.assertEqual(exc.code, "operation_failed")
                self.assertNotIn("read", [frame.name for frame in traceback.extract_tb(exc.__traceback__)])
            self.assertIn("native diagnostic detail", worker.status()["last_error"])
        finally:
            await worker.close()

    async def test_timeout_retires_worker_without_replacement_or_audio_block(self):
        release = threading.Event()
        brightness = FakeAdapter("brightness", release)
        factories_called = []

        def factory():
            factories_called.append(1)
            return brightness

        controller = SystemController(lambda: FakeAdapter("audio"), factory, timeout=0.05)
        try:
            state = await controller.get_state()
            self.assertTrue(state["audio"]["available"])
            self.assertEqual(state["brightness"]["error"]["code"], "timeout")
            state = await controller.set_brightness(20, "panel")
            self.assertEqual(state["brightness"]["error"]["code"], "timeout")
            self.assertEqual(len(factories_called), 1)
            self.assertEqual(brightness.writes, [])
        finally:
            release.set()
            result = await controller.close()
        self.assertTrue(all(result.values()))
        self.assertTrue(brightness.closed)

    async def test_close_cancels_queued_write_and_reports_stuck_native_call(self):
        release = threading.Event()
        adapter = FakeAdapter("audio", release)
        worker = ControlWorker("test", lambda: adapter, timeout=1)
        reading = asyncio.create_task(worker.call("read"))
        try:
            while not adapter.started.is_set():
                await asyncio.sleep(0.001)
            writing = asyncio.create_task(worker.call("set_volume", 99, "speakers"))
            await asyncio.sleep(0.01)
            cleaned_up = await worker.close(timeout=0.01)
            self.assertFalse(cleaned_up)
            with self.assertRaises(ControlFailure):
                await writing
            self.assertEqual(adapter.writes, [])
        finally:
            release.set()
            await reading
            self.assertTrue(await worker.close())

    async def test_worker_queue_is_bounded(self):
        release = threading.Event()
        adapter = FakeAdapter("audio", release)
        worker = ControlWorker("test", lambda: adapter, timeout=1)
        first = asyncio.create_task(worker.call("read"))
        try:
            while not adapter.started.is_set():
                await asyncio.sleep(0.001)
            second = asyncio.create_task(worker.call("read"))
            await asyncio.sleep(0.01)
            with self.assertRaises(ControlFailure) as exc:
                await worker.call("set_volume", 50, "speakers")
            self.assertEqual(exc.exception.code, "busy")
            release.set()
            await asyncio.gather(first, second)
        finally:
            release.set()
            await worker.close()


class RealAdapterGuardsTests(unittest.TestCase):
    def test_audio_checks_fresh_endpoint_before_writing(self):
        class Volume:
            written = False

            def SetMasterVolumeLevelScalar(self, *args):
                self.written = True

        adapter = WindowsAudioAdapter()
        volume = Volume()
        adapter._endpoint = lambda: (object(), "new-endpoint", volume)
        with self.assertRaises(ControlFailure) as exc:
            adapter.set_volume(50, "old-endpoint")
        self.assertEqual(exc.exception.code, "device_changed")
        self.assertFalse(volume.written)

    def test_brightness_checks_fresh_instance_before_invoking_method(self):
        adapter = WindowsBrightnessAdapter()
        adapter._monitor = lambda: {"instance_name": "new-panel"}
        with self.assertRaises(ControlFailure) as exc:
            adapter.set_brightness(50, "old-panel")
        self.assertEqual(exc.exception.code, "device_changed")

    def test_audio_cancellation_is_checked_after_resolving_endpoint(self):
        class Volume:
            written = False

            def SetMasterVolumeLevelScalar(self, *args):
                self.written = True

        cancelled = threading.Event()
        volume = Volume()
        adapter = WindowsAudioAdapter()

        def endpoint():
            cancelled.set()  # Cancellation arrives while the native lookup runs.
            return object(), "speakers", volume

        adapter._endpoint = endpoint
        adapter._current_device_id = lambda: "speakers"
        with self.assertRaises(ControlFailure):
            adapter.set_volume(50, "speakers", cancelled=cancelled)
        self.assertFalse(volume.written)

    def test_audio_rechecks_default_after_interface_activation(self):
        class Volume:
            written = False

            def SetMasterVolumeLevelScalar(self, *args):
                self.written = True

        volume = Volume()
        adapter = WindowsAudioAdapter()
        adapter._endpoint = lambda: (object(), "speakers", volume)
        adapter._current_device_id = lambda: "headphones"
        with self.assertRaises(ControlFailure) as exc:
            adapter.set_volume(50, "speakers")
        self.assertEqual(exc.exception.code, "device_changed")
        self.assertFalse(volume.written)

    def test_choose_internal_panel_and_refuse_ambiguous_external_targets(self):
        internal = {"active": True, "instance_name": "internal"}
        external = {"active": True, "instance_name": "external"}
        self.assertEqual(select_monitor([external, internal], {"internal": 0x80000000, "external": 5}), internal)
        with self.assertRaises(ControlFailure):
            select_monitor([external, internal], {})
        with self.assertRaises(ControlFailure):
            select_monitor([external], {"external": 5}, "internal")
        with self.assertRaises(ControlFailure):
            select_monitor([external], {}, "internal")

    def test_discrete_levels_choose_nearest_with_stable_tie(self):
        self.assertEqual(nearest_level(38, [0, 20, 40, 100]), 40)
        self.assertEqual(nearest_level(30, [0, 20, 40, 100]), 20)
        with self.assertRaises(ControlFailure):
            nearest_level(50, [])


class BrightnessWriteConfirmationTests(unittest.TestCase):
    class MissingProperty(Exception):
        hresult = -2147217406  # WBEM_E_NOT_FOUND

    class Properties:
        def __init__(self, **values):
            self.values = {name: SimpleNamespace(Value=value) for name, value in values.items()}

        def Item(self, name):
            if name not in self.values:
                raise BrightnessWriteConfirmationTests.MissingProperty(name)
            return self.values[name]

    def make_adapter(self, readbacks, output=None, cancel_on_write=None):
        adapter = WindowsBrightnessAdapter()
        adapter._readback_interval = 0.001
        adapter._readback_timeout = 0.025
        record = {"called": False, "readbacks": 0}
        values = list(readbacks)
        parameters = SimpleNamespace(Properties_=self.Properties(Timeout=None, Brightness=None))
        method = SimpleNamespace(InParameters=SimpleNamespace(SpawnInstance_=lambda: parameters))

        def execute(name, supplied):
            self.assertEqual(name, "WmiSetBrightness")
            self.assertIs(supplied, parameters)
            self.assertEqual(parameters.Properties_.Item("Timeout").Value, 0)
            self.assertEqual(parameters.Properties_.Item("Brightness").Value, 50)
            record["called"] = True
            if cancel_on_write is not None:
                cancel_on_write.set()
            return output

        target = SimpleNamespace(Properties_=self.Properties(Active=True, InstanceName="panel"),
                                 Methods_=SimpleNamespace(Item=lambda name: method), ExecMethod_=execute)
        adapter._query = lambda class_name: [target]

        def monitor():
            value = 100
            if record["called"]:
                record["readbacks"] += 1
                value = values.pop(0) if len(values) > 1 else values[0]
            return {"active": True, "instance_name": "panel", "percent": value, "levels": [0, 50, 100]}

        adapter._monitor = monitor
        return adapter, record

    def test_none_or_missing_output_requires_eventual_readback_confirmation(self):
        outputs = (None, SimpleNamespace(Properties_=self.Properties()),
                   SimpleNamespace(Properties_=self.Properties(ReturnValue=0)))
        for output in outputs:
            with self.subTest(output=output):
                adapter, record = self.make_adapter([100, 100, 50], output)
                result = adapter.set_brightness(53, "panel")
                self.assertEqual(result["percent"], 50)
                self.assertIsNone(result["error"])
                self.assertEqual(record["readbacks"], 3)

    def test_provider_return_failure_is_not_hidden_by_readback(self):
        for code, error in ((1, "operation_failed"), (5, "access_denied")):
            with self.subTest(code=code):
                output = SimpleNamespace(Properties_=self.Properties(ReturnValue=code))
                adapter, record = self.make_adapter([50], output)
                with self.assertRaises(ControlFailure) as exc:
                    adapter.set_brightness(50, "panel")
                self.assertEqual(exc.exception.code, error)
                self.assertEqual(record["readbacks"], 0)

    def test_unconfirmed_applied_value_times_out_instead_of_claiming_success(self):
        adapter, record = self.make_adapter([100])
        with self.assertRaises(ControlFailure) as exc:
            adapter.set_brightness(50, "panel")
        self.assertEqual(exc.exception.code, "timeout")
        self.assertTrue(record["called"])
        self.assertGreater(record["readbacks"], 1)

    def test_readback_obeys_cancellation(self):
        cancelled = threading.Event()
        adapter, record = self.make_adapter([50], cancel_on_write=cancelled)
        with self.assertRaises(ControlFailure) as exc:
            adapter.set_brightness(50, "panel", cancelled=cancelled)
        self.assertEqual(exc.exception.code, "operation_failed")
        self.assertEqual(record["readbacks"], 0)


if __name__ == "__main__":
    unittest.main()
