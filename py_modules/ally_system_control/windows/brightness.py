"""Integrated-panel brightness through root\\wmi; never DDC/CI or gamma."""

from ..errors import ControlFailure, check_write_allowed
from .apartment import ComApartment

# D3DKMDT_VIDEO_OUTPUT_TECHNOLOGY embedded connection values, also used by WMI.
_INTEGRATED_CONNECTIONS = {6, 11, 13, 0x80000000}


def select_monitor(monitors, connections, pinned_instance=None):
    """Choose an integrated target, refusing ambiguous/replaced panels."""
    active = [row for row in monitors if row["active"]]
    internal = [row for row in active if connections.get(row["instance_name"]) in _INTEGRATED_CONNECTIONS]
    if len(internal) == 1:
        return internal[0]
    if len(internal) > 1:
        raise ControlFailure("unsupported", "Hay varias pantallas integradas; no se elegirá una automáticamente.")
    # Some OEM drivers do not expose connection metadata. A single WMI brightness
    # provider is the documented laptop-panel path; pin its identity thereafter.
    candidates = [row for row in active if row["instance_name"] == pinned_instance] if pinned_instance else active
    if len(candidates) == 1:
        candidate = candidates[0]
        technology = connections.get(candidate["instance_name"])
        if technology is None:
            return candidate
    if not active or (pinned_instance and not candidates):
        raise ControlFailure("device_unavailable", "La pantalla integrada no está disponible.")
    raise ControlFailure("unsupported", "No se puede identificar con seguridad la pantalla integrada.")


def nearest_level(percent, levels):
    if not levels:
        raise ControlFailure("unsupported", "La pantalla no comunica niveles de brillo válidos.")
    return min(levels, key=lambda level: (abs(level - percent), level))


def _property(obj, name):
    return obj.Properties_.Item(name).Value


class WindowsBrightnessAdapter:
    def __init__(self):
        self._apartment = ComApartment()
        self._locator = None
        self._services = None
        self._pinned_instance = None

    def open(self):
        self._apartment.open()
        from comtypes.client import CreateObject
        self._locator = CreateObject("WbemScripting.SWbemLocator", dynamic=True)
        self._services = self._locator.ConnectServer(".", r"root\wmi")

    def _query(self, class_name):
        # wbemFlagReturnImmediately | wbemFlagForwardOnly; no generated bindings.
        return self._services.ExecQuery("SELECT * FROM " + class_name, "WQL", 0x30)

    def _monitor(self):
        monitors = []
        for row in self._query("WmiMonitorBrightness"):
            raw_levels = _property(row, "Level") or ()
            levels = sorted({int(level) for level in raw_levels if 0 <= int(level) <= 100})
            monitors.append({"active": bool(_property(row, "Active")),
                             "instance_name": str(_property(row, "InstanceName")),
                             "percent": int(_property(row, "CurrentBrightness")), "levels": levels})
        connections = {}
        try:
            for row in self._query("WmiMonitorConnectionParams"):
                connections[str(_property(row, "InstanceName"))] = int(_property(row, "VideoOutputTechnology")) & 0xFFFFFFFF
        except Exception:
            # Older OEM providers can omit this optional class. Pin the first
            # unambiguous WMI panel rather than switching to a newly attached one.
            pass
        monitor = select_monitor(monitors, connections, self._pinned_instance)
        if not monitor["levels"]:
            raise ControlFailure("unsupported", "La pantalla no comunica niveles de brillo válidos.")
        if self._pinned_instance is None:
            self._pinned_instance = monitor["instance_name"]
        elif monitor["instance_name"] != self._pinned_instance:
            raise ControlFailure("device_changed", "La pantalla integrada ha cambiado. Recarga el plugin.")
        return monitor

    @staticmethod
    def _snapshot(monitor):
        return {"available": True, "percent": monitor["percent"], "levels": monitor["levels"],
                "instance_name": monitor["instance_name"], "error": None}

    def read(self, cancelled=None):
        return self._snapshot(self._monitor())

    def set_brightness(self, percent, expected_instance_name, cancelled=None):
        # Re-enumerate just before writing; a stale UI must never target a dock.
        monitor = self._monitor()
        if monitor["instance_name"] != expected_instance_name:
            raise ControlFailure("device_changed", "La pantalla ha cambiado. Actualiza el panel.")
        method_target = None
        for row in self._query("WmiMonitorBrightnessMethods"):
            if (bool(_property(row, "Active")) and
                    str(_property(row, "InstanceName")) == expected_instance_name):
                method_target = row
                break
        if method_target is None:
            raise ControlFailure("device_unavailable", "La pantalla ya no permite ajustar el brillo.")
        requested = nearest_level(percent, monitor["levels"])
        method = method_target.Methods_.Item("WmiSetBrightness")
        parameters = method.InParameters.SpawnInstance_()
        parameters.Properties_.Item("Timeout").Value = 0
        parameters.Properties_.Item("Brightness").Value = requested
        if self._monitor()["instance_name"] != expected_instance_name:
            raise ControlFailure("device_changed", "La pantalla ha cambiado. Actualiza el panel.")
        check_write_allowed(cancelled)
        result = method_target.ExecMethod_("WmiSetBrightness", parameters)
        return_value = int(_property(result, "ReturnValue"))
        if return_value:
            if return_value in (5, 0x80070005, 0x80041003):
                raise ControlFailure("access_denied", "Windows ha denegado el cambio de brillo.")
            raise ControlFailure("operation_failed", "El controlador no ha confirmado el cambio de brillo.")
        # Read back instead of claiming that the requested level was applied.
        return self.read(cancelled=cancelled)

    def close(self):
        self._services = None
        self._locator = None
        self._apartment.close()
