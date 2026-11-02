"""One bounded, single-threaded owner per adapter and COM apartment.

A native COM call cannot safely be killed from another Python thread. A timeout
therefore retires this worker, cancels queued writes and never spawns replacements.
The daemon exits and releases COM when the native call returns. close() reports
whether that cleanup completed within its deadline instead of hanging Decky.
"""

import asyncio
from concurrent.futures import Future
from dataclasses import dataclass, field
import queue
import threading
import time

from .errors import ControlFailure, normalize_error


@dataclass
class _Operation:
    method: str
    args: tuple
    result: Future = field(default_factory=Future)
    cancelled: threading.Event = field(default_factory=threading.Event)


class ControlWorker:
    def __init__(self, name, adapter_factory, timeout=3.0):
        self.name = name
        self._factory = adapter_factory
        self._timeout = timeout
        self._queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._thread = None
        self._active = None
        self._closed = False
        self._timed_out = False
        self._last_error = None

    async def call(self, method, *args):
        operation = _Operation(method, args)
        with self._lock:
            if self._timed_out:
                raise ControlFailure("timeout", "El control no responde. Recarga el plugin para reintentarlo.")
            if self._closed:
                raise ControlFailure("operation_failed", "El plugin se está cerrando.")
            try:
                self._queue.put_nowait(operation)
            except queue.Full:
                raise ControlFailure("busy", "Hay otra operación pendiente; vuelve a intentarlo.")
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="Ally-" + self.name, daemon=True)
                self._thread.start()
        wrapped = asyncio.wrap_future(operation.result)
        try:
            # Keep the underlying future valid if the caller is cancelled.
            return await asyncio.wait_for(asyncio.shield(wrapped), self._timeout)
        except asyncio.TimeoutError:
            operation.cancelled.set()
            self._retire(timed_out=True)
            # Consume a later exception without leaving an unhandled asyncio future.
            wrapped.add_done_callback(_consume_future)
            raise ControlFailure("timeout", "Windows no ha respondido a tiempo; el control queda detenido.")
        except asyncio.CancelledError:
            operation.cancelled.set()
            wrapped.add_done_callback(_consume_future)
            raise

    def _run(self):
        adapter = None
        initialization_error = None
        try:
            try:
                adapter = self._factory()
                adapter.open()
            except Exception as exc:
                self._last_error = "{}: {}".format(type(exc).__name__, exc)[:500]
                failure = normalize_error(exc)
                # Retain primitive data only, never an open() traceback that may
                # own partially created COM objects. Each request gets a new error.
                initialization_error = (failure.code, failure.message)
                del failure
            while True:
                with self._lock:
                    if self._closed or self._timed_out:
                        break
                try:
                    operation = self._queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                with self._lock:
                    self._active = operation
                    stopping = self._closed or self._timed_out
                try:
                    if stopping or operation.cancelled.is_set():
                        raise ControlFailure("operation_failed", "La operación se ha cancelado.")
                    if initialization_error is not None:
                        raise ControlFailure(*initialization_error)
                    value = getattr(adapter, operation.method)(*operation.args, cancelled=operation.cancelled)
                    if not operation.result.done():
                        operation.result.set_result(value)
                except Exception as exc:
                    self._last_error = "{}: {}".format(type(exc).__name__, exc)[:500]
                    if not operation.result.done():
                        # Native tracebacks may retain COM pointers. Never let
                        # their finalizers run on Decky's asyncio thread.
                        failure = normalize_error(exc)
                        operation.result.set_exception(ControlFailure(failure.code, failure.message))
                        del failure
                finally:
                    with self._lock:
                        self._active = None
                    self._queue.task_done()
        finally:
            initialization_error = None
            if adapter is not None:
                try:
                    adapter.close()
                except Exception:
                    # Resource cleanup must not crash the host process.
                    pass

    def _retire(self, timed_out=False):
        with self._lock:
            self._closed = True
            self._timed_out = self._timed_out or timed_out
            if self._active is not None:
                self._active.cancelled.set()
            while True:
                try:
                    operation = self._queue.get_nowait()
                except queue.Empty:
                    break
                operation.cancelled.set()
                if not operation.result.done():
                    operation.result.set_exception(ControlFailure("operation_failed", "La operación se ha cancelado."))
                self._queue.task_done()

    async def close(self, timeout=1.0):
        self._retire()
        deadline = time.monotonic() + timeout
        while self._thread is not None and self._thread.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        return self._thread is None or not self._thread.is_alive()

    def status(self):
        with self._lock:
            return {"started": self._thread is not None,
                    "alive": self._thread is not None and self._thread.is_alive(),
                    "closed": self._closed, "timed_out": self._timed_out,
                    "queued": self._queue.qsize(), "last_error": self._last_error}


def _consume_future(future):
    if not future.cancelled():
        future.exception()
