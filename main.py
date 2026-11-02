"""Decky API v1 entry point. All hardware imports live in the bundled package."""

from pathlib import Path
import sys

_modules = str(Path(__file__).resolve().parent / "py_modules")
if _modules not in sys.path:
    sys.path.insert(0, _modules)

from ally_system_control.controller import SystemController


class Plugin:
    def __init__(self):
        self._controller = SystemController()

    async def _main(self):
        # Workers are lazy: loading a plugin never applies saved system values.
        pass

    async def _unload(self):
        result = await self._controller.close()
        if not all(result.values()):
            try:
                import decky
                decky.logger.warning("Ally System Control: native Windows call still pending during unload; worker retired.")
            except (ImportError, AttributeError):
                pass

    async def _migration(self):
        pass

    async def get_state(self):
        return await self._controller.get_state()

    async def get_capabilities(self):
        return await self._controller.get_capabilities()

    async def get_diagnostics(self):
        return self._controller.get_diagnostics()

    async def set_volume(self, percent=None, expected_device_id=None):
        return await self._controller.set_volume(percent, expected_device_id)

    async def set_mute(self, muted=None, expected_device_id=None):
        return await self._controller.set_mute(muted, expected_device_id)

    async def set_brightness(self, percent=None, expected_instance_name=None):
        return await self._controller.set_brightness(percent, expected_instance_name)
