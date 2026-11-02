"""Decky-independent async contract; each control owns a separate COM worker."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os
import platform
import sys

from . import __version__
from .errors import ControlFailure, normalize_error, validate_identity, validate_percent
from .models import unavailable_audio, unavailable_brightness
from .worker import ControlWorker


def _audio_factory():
    from .windows.audio import WindowsAudioAdapter
    return WindowsAudioAdapter()


def _brightness_factory():
    from .windows.brightness import WindowsBrightnessAdapter
    return WindowsBrightnessAdapter()


class SystemController:
    def __init__(self, audio_factory=None, brightness_factory=None, timeout=3.0):
        self._audio = ControlWorker("audio", audio_factory or _audio_factory, timeout)
        self._brightness = ControlWorker("brightness", brightness_factory or _brightness_factory, timeout)
        self._closed = False
        self._cache = {"audio": unavailable_audio(), "brightness": unavailable_brightness()}
        self._issued = {"audio": 0, "brightness": 0}
        self._completed = {"audio": 0, "brightness": 0}

    async def _invoke(self, control, method="read", *args):
        worker = self._audio if control == "audio" else self._brightness
        empty = unavailable_audio if control == "audio" else unavailable_brightness
        self._issued[control] += 1
        revision = self._issued[control]
        try:
            result = await worker.call(method, *args)
        except Exception as exc:
            error = normalize_error(exc).as_dict()
            if error["code"] == "busy":
                # A full queue is not evidence that a previously working device
                # disappeared. Polls can use the last confirmed snapshot while a
                # setter is running; a rejected setter still reports its error.
                result = deepcopy(self._cache[control])
                if method != "read":
                    result["error"] = error
                return result
            result = empty(error)
        if revision >= self._completed[control]:
            self._cache[control] = deepcopy(result)
            self._completed[control] = revision
        # An older read completing after a newer setter cannot replace its value.
        return deepcopy(self._cache[control])

    def _state(self, **overrides):
        values = deepcopy(self._cache)
        values.update(deepcopy(overrides))
        return {"audio": values["audio"], "brightness": values["brightness"],
                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}

    async def get_state(self):
        await asyncio.gather(self._invoke("audio"), self._invoke("brightness"))
        return self._state()

    async def get_capabilities(self):
        state = await self.get_state()
        return {"contract_version": 1, "poll_interval_ms": 1000,
                "audio": {"available": state["audio"]["available"], "supports_mute": True,
                          "error": state["audio"]["error"]},
                "brightness": {"available": state["brightness"]["available"],
                               "levels": state["brightness"]["levels"],
                               "error": state["brightness"]["error"]}}

    async def _validation_error(self, control, error):
        # Validation is local and must never start or wait for either COM worker.
        state = self._state()
        state[control]["error"] = error.as_dict()
        return state

    async def set_volume(self, percent, expected_device_id):
        try:
            percent = validate_percent(percent)
            expected_device_id = validate_identity(expected_device_id)
        except ControlFailure as exc:
            return await self._validation_error("audio", exc)
        audio = await self._invoke("audio", "set_volume", percent, expected_device_id)
        return self._state(audio=audio)

    async def set_mute(self, muted, expected_device_id):
        try:
            if not isinstance(muted, bool):
                raise ControlFailure("invalid_argument", "El estado de silencio debe ser verdadero o falso.")
            expected_device_id = validate_identity(expected_device_id)
        except ControlFailure as exc:
            return await self._validation_error("audio", exc)
        audio = await self._invoke("audio", "set_mute", muted, expected_device_id)
        return self._state(audio=audio)

    async def set_brightness(self, percent, expected_instance_name):
        try:
            percent = validate_percent(percent)
            expected_instance_name = validate_identity(expected_instance_name)
        except ControlFailure as exc:
            return await self._validation_error("brightness", exc)
        brightness = await self._invoke("brightness", "set_brightness", percent, expected_instance_name)
        return self._state(brightness=brightness)

    def get_diagnostics(self):
        loader_version = os.environ.get("DECKY_LOADER_VERSION") or os.environ.get("DECKY_VERSION")
        # Avoid importing internals of the loader, which can have startup effects.
        for module_name in ("decky_loader", "decky"):
            module = sys.modules.get(module_name)
            if module is not None:
                candidate = getattr(module, "DECKY_LOADER_VERSION", None)
                if isinstance(candidate, str):
                    loader_version = candidate
        return {"python_version": platform.python_version(), "architecture": platform.machine(),
                "platform": platform.platform(), "plugin_version": __version__,
                "loader_version": loader_version,
                "comtypes_version": getattr(sys.modules.get("comtypes"), "__version__", None),
                "workers": {"audio": self._audio.status(), "brightness": self._brightness.status()}}

    async def close(self):
        self._closed = True
        audio, brightness = await asyncio.gather(self._audio.close(), self._brightness.close())
        return {"audio_cleaned_up": audio, "brightness_cleaned_up": brightness}
