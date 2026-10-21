"""Bound repeated cyclic-GC scans during a single-process publication build.

Reference counting continues normally. Cycles are collected at state boundaries,
and automatic cyclic collection is restored before the results/model phases.
Do not use this process-wide policy inside the interactive API server.
"""
from __future__ import annotations

import gc
from contextlib import AbstractContextManager
from time import monotonic
from typing import Callable


class PublicationRuntime(AbstractContextManager):
    def __init__(self, progress: Callable[[dict], None] | None = None):
        self._callback = progress or (lambda update: None)
        self._initial_enabled = None
        self._suspended = False
        self._entered = False
        self.collections: list[dict] = []

    def __enter__(self):
        if self._entered:
            raise RuntimeError("Publication runtime context cannot be entered twice")
        self._initial_enabled = gc.isenabled()
        self._entered = True
        return self

    def _collect(self, boundary: str):
        started = monotonic()
        collected = gc.collect()
        self.collections.append({"boundary": boundary, "objects_collected": collected,
                                 "seconds": round(monotonic() - started, 6)})

    def progress(self, update: dict):
        if not self._entered:
            raise RuntimeError("Publication runtime progress requires an active context")
        if self._initial_enabled:
            stage = update.get("stage")
            if stage == "state":
                # The callback occurs before the next state's work. The previous
                # state's temporary SQLAlchemy/object cycles can be released now.
                self._collect("state:" + str(update.get("state", "unknown")))
                gc.disable()
                self._suspended = True
            elif self._suspended:
                try:
                    self._collect("before:" + str(stage or "next-phase"))
                finally:
                    gc.enable()
                    self._suspended = False
        self._callback(update)

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._suspended:
                self._collect("context-exit")
        finally:
            # Existing callers that disabled cyclic collection keep their policy;
            # this helper never changes GC thresholds, debug flags or callbacks.
            if self._initial_enabled:
                gc.enable()
            else:
                gc.disable()
            self._suspended = False
            self._entered = False
        return False

    def summary(self) -> dict:
        return {"policy": "state-bounded-cyclic-gc", "initial_automatic_gc": self._initial_enabled,
                "manual_collections": len(self.collections),
                "manual_collection_seconds": round(sum(row["seconds"] for row in self.collections), 6),
                "mode_restored": gc.isenabled() == self._initial_enabled}
