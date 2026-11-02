"""Safe, JSON-compatible errors shared by the controller and Windows adapters."""

import math


class ControlFailure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self):
        return {"code": self.code, "message": self.message}


def validate_percent(value):
    # bool subclasses int, but is never a valid slider value.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ControlFailure("invalid_argument", "El porcentaje debe ser un número entre 0 y 100.")
    if value < 0 or value > 100 or not math.isfinite(value):
        raise ControlFailure("invalid_argument", "El porcentaje debe estar entre 0 y 100.")
    return float(value)


def validate_identity(value):
    if not isinstance(value, str) or not value.strip():
        raise ControlFailure("invalid_argument", "Actualiza el panel antes de cambiar este control.")
    return value


def check_write_allowed(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise ControlFailure("operation_failed", "La operación se ha cancelado.")


def normalize_error(exc):
    if isinstance(exc, ControlFailure):
        return exc
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return ControlFailure("unsupported", "Falta una dependencia de Windows en el paquete del plugin.")
    raw_code = getattr(exc, "hresult", getattr(exc, "winerror", None))
    if raw_code is None and getattr(exc, "args", ()) and isinstance(exc.args[0], int):
        raw_code = exc.args[0]
    code = (raw_code & 0xFFFFFFFF) if isinstance(raw_code, int) else None
    if isinstance(exc, PermissionError) or code in (5, 0x80070005, 0x80041003):
        return ControlFailure("access_denied", "Windows ha denegado el acceso a este control.")
    if code in (0x80070490, 0x88890004, 0x80041002):
        return ControlFailure("device_unavailable", "El dispositivo ya no está disponible.")
    if code in (0x80041010, 0x8004100E):
        return ControlFailure("unsupported", "El controlador de Windows no ofrece esta función.")
    if isinstance(exc, TimeoutError) or code in (0x80043001, 0x80041069):
        return ControlFailure("timeout", "Windows no ha respondido a tiempo.")
    return ControlFailure("operation_failed", "No se ha podido completar la operación en Windows.")
