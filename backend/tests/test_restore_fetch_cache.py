"""A restored evidence archive can actually be parsed without the network."""
import hashlib
import io
import zipfile
from pathlib import Path

from observatory.archive import Fetcher
from observatory.cli import backup, restore
from observatory.db import Database, Revision, Snapshot
from observatory.settings import PROJECT_ROOT, Settings


def test_restore_rebuilds_latest_original_url_cache_and_preserves_source_types(tmp_path, monkeypatch):
    settings = Settings(tmp_path/'original', project_root=PROJECT_ROOT)
    database = Database(settings)
    url = 'https://example.org/original-redirect-endpoint?state=NC&format=csv'
    pdf_url = 'https://example.org/official-report.pdf'
    zip_url = 'https://example.org/publisher-download/123'
    zip_stream = io.BytesIO()
    with zipfile.ZipFile(zip_stream, 'w') as archive:
        archive.writestr('precincts.csv', 'precinct,votes\nA,20\n')
    records = [
        (url, b'date,total\n2026-10-20,10\n', 'text/csv; charset=utf-8', '2026-10-20T23:00:00Z'),
        (url, b'date,total\n2026-10-21,20\n', 'text/csv; charset=utf-8', '2026-10-21T01:00:00Z'),
        # A later local revision can preserve an older retrieval. Retrieval
        # chronology wins; revision/record order only breaks an actual tie.
        (url, b'date,total\n2026-10-19,5\n', 'text/csv; charset=utf-8', '2026-10-19T20:00:00Z'),
        (pdf_url, b'%PDF-1.4\n% Explicit binary test fixture\n', 'application/pdf', '2026-10-21T01:00:00Z'),
        (zip_url, zip_stream.getvalue(), 'application/zip', '2026-10-21T01:00:00Z'),
    ]
    for original_url, content, content_type, retrieved_at in records:
        digest = hashlib.sha256(content).hexdigest()
        archived = settings.archive_dir/digest[:2]/digest
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes(content)
        with database.session() as session, session.begin():
            revision = Revision(reason='Explicit recovery test fixture', source_id='test')
            session.add(revision)
            session.flush()
            session.add(Snapshot(source_id='test', url=original_url, sha256=digest, path=str(archived),
                content_type=content_type, retrieved_at=retrieved_at, byte_count=len(content), revision=revision.id))
    assert not (settings.data_dir/'fetch-cache').exists()
    archive_path = backup(database, tmp_path/'backup.zip')
    restored_dir = tmp_path/'restored'
    recovered = restore(archive_path, restored_dir)
    assert recovered['fetch_cache_entries'] == 3
    assert recovered['archives_verified'] == 5
    fetcher = Fetcher(Settings(restored_dir, project_root=PROJECT_ROOT), offline=True)
    def unexpected_network(*args, **kwargs):
        raise AssertionError('Offline restoration must not request a redirect or source')
    monkeypatch.setattr(fetcher.client, 'stream', unexpected_network)
    try:
        csv_document = fetcher.fetch(url)
        assert csv_document.url == url
        assert Path(csv_document.path).read_bytes() == records[1][1]
        assert Path(csv_document.path).is_relative_to(restored_dir/'archive')
        assert csv_document.content_type == 'text/csv; charset=utf-8'
        assert csv_document.retrieved_at == '2026-10-21T01:00:00Z'
        assert csv_document.etag is None and csv_document.last_modified is None
        pdf_document = fetcher.fetch(pdf_url)
        assert pdf_document.content_type == 'application/pdf'
        assert Path(pdf_document.path).read_bytes().startswith(b'%PDF-')
        zip_document = fetcher.fetch(zip_url)
        assert zip_document.content_type == 'application/zip'
        with zipfile.ZipFile(zip_document.path) as source:
            assert source.read('precincts.csv') == b'precinct,votes\nA,20\n'
    finally:
        fetcher.close()
