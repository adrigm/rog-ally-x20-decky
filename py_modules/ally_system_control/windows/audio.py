"""Master playback volume through the documented Windows Core Audio interfaces.

Only the vtable prefix actually used by the adapter is declared. No pycaw,
generated typelib cache, per-application mixer or microphone control is required.
"""

import ctypes
from ctypes import POINTER, Structure, Union, c_float, c_int, c_uint, c_ushort, c_void_p, c_wchar_p
from ctypes.wintypes import BOOL, DWORD, ULONG

from ..errors import ControlFailure, check_write_allowed
from .apartment import ComApartment

_interfaces = None


def _bindings(comtypes):
    global _interfaces
    if _interfaces is not None:
        return _interfaces
    GUID, COMMETHOD, HRESULT, IUnknown = comtypes.GUID, comtypes.COMMETHOD, comtypes.HRESULT, comtypes.IUnknown

    class PROPERTYKEY(Structure):
        _fields_ = [("fmtid", GUID), ("pid", DWORD)]

    class BLOB(Structure):
        _fields_ = [("cbSize", ULONG), ("pBlobData", c_void_p)]

    class VariantValue(Union):
        # BLOB ensures correct PROPVARIANT size/alignment on x64 and x86.
        _fields_ = [("pointer", c_void_p), ("integer", ctypes.c_longlong), ("blob", BLOB)]

    class PROPVARIANT(Structure):
        _anonymous_ = ("value",)
        _fields_ = [("vt", c_ushort), ("reserved1", c_ushort),
                    ("reserved2", c_ushort), ("reserved3", c_ushort), ("value", VariantValue)]

    class IPropertyStore(IUnknown):
        _iid_ = GUID("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(DWORD), "count")),
            COMMETHOD([], HRESULT, "GetAt", (["in"], DWORD, "index"), (["out"], POINTER(PROPERTYKEY), "key")),
            COMMETHOD([], HRESULT, "GetValue", (["in"], POINTER(PROPERTYKEY), "key"),
                      (["out"], POINTER(PROPVARIANT), "value")),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Activate", (["in"], POINTER(GUID), "iid"),
                      (["in"], DWORD, "clsctx"), (["in"], c_void_p, "params"),
                      (["out"], POINTER(c_void_p), "interface")),
            COMMETHOD([], HRESULT, "OpenPropertyStore", (["in"], DWORD, "access"),
                      (["out"], POINTER(POINTER(IPropertyStore)), "store")),
            # LPWSTR is caller-owned CoTaskMem memory; keep the pointer to free it.
            COMMETHOD([], HRESULT, "GetId", (["out"], POINTER(c_void_p), "identifier")),
            COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(DWORD), "state")),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = [
            COMMETHOD([], HRESULT, "EnumAudioEndpoints", (["in"], c_int, "flow"),
                      (["in"], DWORD, "mask"), (["out"], POINTER(c_void_p), "devices")),
            COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint", (["in"], c_int, "flow"),
                      (["in"], c_int, "role"), (["out"], POINTER(POINTER(IMMDevice)), "device")),
        ]

    class IAudioEndpointVolume(IUnknown):
        _iid_ = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")
        _methods_ = [
            COMMETHOD([], HRESULT, "RegisterControlChangeNotify", (["in"], c_void_p, "notify")),
            COMMETHOD([], HRESULT, "UnregisterControlChangeNotify", (["in"], c_void_p, "notify")),
            COMMETHOD([], HRESULT, "GetChannelCount", (["out"], POINTER(c_uint), "count")),
            COMMETHOD([], HRESULT, "SetMasterVolumeLevel", (["in"], c_float, "level"),
                      (["in"], POINTER(GUID), "context")),
            COMMETHOD([], HRESULT, "SetMasterVolumeLevelScalar", (["in"], c_float, "level"),
                      (["in"], POINTER(GUID), "context")),
            COMMETHOD([], HRESULT, "GetMasterVolumeLevel", (["out"], POINTER(c_float), "level")),
            COMMETHOD([], HRESULT, "GetMasterVolumeLevelScalar", (["out"], POINTER(c_float), "level")),
            COMMETHOD([], HRESULT, "SetChannelVolumeLevel", (["in"], c_uint, "channel"),
                      (["in"], c_float, "level"), (["in"], POINTER(GUID), "context")),
            COMMETHOD([], HRESULT, "SetChannelVolumeLevelScalar", (["in"], c_uint, "channel"),
                      (["in"], c_float, "level"), (["in"], POINTER(GUID), "context")),
            COMMETHOD([], HRESULT, "GetChannelVolumeLevel", (["in"], c_uint, "channel"),
                      (["out"], POINTER(c_float), "level")),
            COMMETHOD([], HRESULT, "GetChannelVolumeLevelScalar", (["in"], c_uint, "channel"),
                      (["out"], POINTER(c_float), "level")),
            COMMETHOD([], HRESULT, "SetMute", (["in"], BOOL, "muted"),
                      (["in"], POINTER(GUID), "context")),
            COMMETHOD([], HRESULT, "GetMute", (["out"], POINTER(BOOL), "muted")),
        ]

    _interfaces = {"IMMDeviceEnumerator": IMMDeviceEnumerator,
                   "IAudioEndpointVolume": IAudioEndpointVolume,
                   "PROPERTYKEY": PROPERTYKEY, "PROPVARIANT": PROPVARIANT}
    return _interfaces


class WindowsAudioAdapter:
    def __init__(self):
        self._apartment = ComApartment()
        self._enumerator = None
        self._types = None
        self._ole32 = None

    def open(self):
        comtypes = self._apartment.open()
        self._types = _bindings(comtypes)
        self._ole32 = ctypes.OleDLL("ole32")
        self._ole32.CoTaskMemFree.argtypes = [c_void_p]
        self._ole32.CoTaskMemFree.restype = None
        self._ole32.PropVariantClear.argtypes = [POINTER(self._types["PROPVARIANT"])]
        self._ole32.PropVariantClear.restype = ctypes.c_long
        self._enumerator = comtypes.CoCreateInstance(
            comtypes.GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"),
            interface=self._types["IMMDeviceEnumerator"], clsctx=comtypes.CLSCTX_INPROC_SERVER)

    def _device_id(self, device):
        pointer = device.GetId()
        try:
            return ctypes.wstring_at(pointer)
        finally:
            self._ole32.CoTaskMemFree(pointer)

    def _current_device_id(self):
        return self._device_id(self._enumerator.GetDefaultAudioEndpoint(0, 0))

    def _endpoint(self):
        # eRender=0, eConsole=0. Resolve on every operation, including setters.
        device = self._enumerator.GetDefaultAudioEndpoint(0, 0)
        identifier = self._device_id(device)
        endpoint_type = self._types["IAudioEndpointVolume"]
        raw = device.Activate(ctypes.byref(endpoint_type._iid_), 23, None)
        volume = ctypes.cast(raw, POINTER(endpoint_type))
        # Activate returns one owned interface reference. comtypes' pointer owns it.
        return device, identifier, volume

    def _device_name(self, device):
        try:
            comtypes = self._apartment._comtypes
            key = self._types["PROPERTYKEY"](
                comtypes.GUID("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14)
            store = device.OpenPropertyStore(0)  # STGM_READ
            value = store.GetValue(ctypes.byref(key))
            try:
                return ctypes.wstring_at(value.pointer) if value.vt == 31 and value.pointer else None
            finally:
                self._ole32.PropVariantClear(ctypes.byref(value))
        except Exception:
            # A missing label must not disable working volume controls.
            return None

    def _snapshot(self, device, identifier, volume):
        return {"available": True,
                "volume": round(float(volume.GetMasterVolumeLevelScalar()) * 100.0, 2),
                "muted": bool(volume.GetMute()), "device_id": identifier,
                "device_name": self._device_name(device), "error": None}

    def read(self, cancelled=None):
        return self._snapshot(*self._endpoint())

    def _checked_endpoint(self, expected_device_id, cancelled):
        device, identifier, volume = self._endpoint()
        if identifier != expected_device_id or self._current_device_id() != expected_device_id:
            raise ControlFailure("device_changed", "La salida de audio ha cambiado. Actualiza el panel.")
        check_write_allowed(cancelled)
        return device, identifier, volume

    def set_volume(self, percent, expected_device_id, cancelled=None):
        device, identifier, volume = self._checked_endpoint(expected_device_id, cancelled)
        # Do not implicitly unmute: the independent mute button preserves intent.
        volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
        return self._snapshot(device, identifier, volume)

    def set_mute(self, muted, expected_device_id, cancelled=None):
        device, identifier, volume = self._checked_endpoint(expected_device_id, cancelled)
        volume.SetMute(muted, None)
        return self._snapshot(device, identifier, volume)

    def close(self):
        # Drop every owned interface on its apartment before uninitializing COM.
        self._enumerator = None
        self._apartment.close()
