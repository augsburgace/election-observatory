from collections import OrderedDict
from types import SimpleNamespace

from observatory import service
from observatory.domain import ResearchQuery


def test_national_publication_reuses_exact_scope_across_states_without_mutation(monkeypatch):
    calls = []
    def build(*args):
        calls.append(args)
        return [{"value": 12}]
    monkeypatch.setattr(service, "_national_uncached", build)
    database = SimpleNamespace(_publication_national_cache=OrderedDict())
    oh = ResearchQuery(state="OH")
    first = service._national(database, oh, 1, "2026-10-21", [], {})
    first[0]["value"] = 999
    second = service._national(database, oh.model_copy(update={"state": "NC"}), 1, "2026-10-21", [], {})
    assert len(calls) == 1 and second[0]["value"] == 12
    service._national(database, oh, 2, "2026-10-21", [], {})
    service._national(database, oh, 1, "2026-10-20", [], {})
    service._national(database, oh.model_copy(update={"mode": "mail"}), 1, "2026-10-21", [], {})
    service._national(database, oh, 1, "2026-10-21", [{"id": "new-source"}], {})
    assert len(calls) == 5
