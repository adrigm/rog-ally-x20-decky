"""The public wire format deliberately contains only plain JSON values."""


def unavailable_audio(error=None):
    return {"available": False, "volume": None, "muted": None,
            "device_id": None, "device_name": None, "error": error}


def unavailable_brightness(error=None):
    return {"available": False, "percent": None, "levels": [],
            "instance_name": None, "error": error}
