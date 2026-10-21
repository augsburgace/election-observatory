"""Reviewed definition corrections retain originals and exact historical pins."""
from sqlalchemy import select

from .db import QualityValidation, Revision, record_dict


def apply_definition_validations(database):
    policies = [
        ("AZ", "ballots_requested", "Arizona request_* fields in the UF tracker are ballots issued on a permanent early-voting list, not applications."),
        ("DE", "ballots_requested", "Delaware request_* fields substitute returned ballots; actual requests are not published."),
        ("UT", "ballots_requested", "Utah request_* fields substitute active registration totals; actual request counts are not observed."),
        ("WA", "ballots_requested", "Washington's old tracker request field has no established application definition; a universal-mail registration/distribution placeholder cannot establish actual requests."),
    ]
    findings = []
    with database.lock, database.session() as session:
        for state, metric, reason in policies:
            key = f"uf-native-definition-{state}-{metric}-v1"
            old = session.scalar(select(QualityValidation).where(QualityValidation.key == key))
            if old:
                findings.append(record_dict(old))
                continue
            source_id = f"uf-fallback-{state.lower()}"
            revision = Revision(reason="Reviewed producer definition correction", source_id=source_id)
            session.add(revision)
            session.flush()
            decision = QualityValidation(key=key, revision=revision.id, state=state, metric=metric,
                time_basis="reported", source_id=source_id, reason=reason + " Originals remain archived; corrected data use their native measure.")
            session.add(decision)
            session.flush()
            findings.append(record_dict(decision))
        session.commit()
    return findings
