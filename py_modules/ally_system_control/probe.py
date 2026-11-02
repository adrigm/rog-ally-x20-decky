"""Run `python -m ally_system_control.probe --read-only` with py_modules on sys.path.

This command has no setters, never changes audio/brightness, and needs no Steam UI.
It is also suitable for the extracted package with an isolated Python interpreter.
"""

import argparse
import asyncio
import json

from .controller import SystemController


async def run():
    controller = SystemController()
    try:
        state = await controller.get_state()
        result = {"diagnostics": controller.get_diagnostics(), "state": state}
    finally:
        cleanup = await controller.close()
    result["cleanup"] = cleanup
    return result


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico de Ally System Control, únicamente lectura.")
    parser.add_argument("--read-only", action="store_true", help="Confirma que solo se consultan valores (también es el comportamiento por defecto).")
    parser.parse_args()
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
