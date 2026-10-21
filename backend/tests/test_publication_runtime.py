"""The batch runtime policy never leaks into later commands or API workers."""
from __future__ import annotations

import gc
import weakref

import pytest

from scripts.publication_runtime import PublicationRuntime


@pytest.fixture(autouse=True)
def restore_gc_mode():
    enabled = gc.isenabled()
    yield
    gc.enable() if enabled else gc.disable()


def test_state_boundaries_collect_cycles_and_restore_automatic_mode():
    gc.enable()
    thresholds = gc.get_threshold()
    seen = []

    class Cycle:
        pass

    with PublicationRuntime(lambda update: seen.append((update, gc.isenabled()))) as runtime:
        runtime.progress({"stage": "catalogs"})
        runtime.progress({"stage": "state", "state": "OH"})
        item = Cycle()
        item.self = item
        reference = weakref.ref(item)
        del item
        assert reference() is not None and not gc.isenabled()
        runtime.progress({"stage": "state", "state": "PA"})
        assert reference() is None and not gc.isenabled()
        runtime.progress({"stage": "results"})
        assert gc.isenabled()
        runtime.progress({"stage": "forecasts"})
    assert [enabled for _, enabled in seen] == [True, False, False, True, True]
    assert gc.isenabled() and gc.get_threshold() == thresholds
    assert runtime.summary()["mode_restored"]
    assert runtime.summary()["manual_collections"] == 3


def test_originally_disabled_mode_is_respected_without_manual_collection(monkeypatch):
    gc.disable()
    monkeypatch.setattr(gc, "collect", lambda: pytest.fail("A pre-existing disabled policy must remain untouched"))
    with PublicationRuntime() as runtime:
        runtime.progress({"stage": "state", "state": "OH"})
        runtime.progress({"stage": "results"})
    assert not gc.isenabled() and runtime.summary()["manual_collections"] == 0


def test_exceptions_restore_mode_and_do_not_swallow_the_build_failure():
    gc.enable()
    with pytest.raises(ValueError, match="synthetic build failure"):
        with PublicationRuntime() as runtime:
            runtime.progress({"stage": "state", "state": "OH"})
            raise ValueError("synthetic build failure")
    assert gc.isenabled()
    assert runtime.collections[-1]["boundary"] == "context-exit"


def test_failed_collection_still_restores_initial_mode(monkeypatch):
    gc.enable()
    with pytest.raises(RuntimeError, match="synthetic collection failure"):
        with PublicationRuntime() as runtime:
            runtime.progress({"stage": "state", "state": "OH"})
            monkeypatch.setattr(gc, "collect", lambda: (_ for _ in ()).throw(RuntimeError("synthetic collection failure")))
    assert gc.isenabled()


def test_progress_cannot_change_process_mode_outside_context():
    runtime = PublicationRuntime()
    with pytest.raises(RuntimeError, match="active context"):
        runtime.progress({"stage": "state", "state": "OH"})
