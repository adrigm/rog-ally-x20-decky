"""COM must be initialized and released on the thread owning each adapter."""

import importlib
import sys
import threading

from ..errors import ControlFailure

_import_lock = threading.Lock()


class ComApartment:
    def __init__(self):
        self._comtypes = None
        self._owner = None

    def open(self):
        if sys.platform != "win32":
            raise ControlFailure("unsupported", "Este plugin necesita Windows.")
        # comtypes initializes the importing thread as STA on its first import.
        # Balance that call, or explicitly initialize every subsequent worker.
        with _import_lock:
            already_loaded = "comtypes" in sys.modules
            comtypes = importlib.import_module("comtypes")
            if already_loaded:
                comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
            self._comtypes = comtypes
            self._owner = threading.get_ident()
        return comtypes

    def close(self):
        if self._comtypes is not None:
            if self._owner != threading.get_ident():
                raise RuntimeError("COM apartment must close on its owning thread")
            self._comtypes.CoUninitialize()
            self._comtypes = None
