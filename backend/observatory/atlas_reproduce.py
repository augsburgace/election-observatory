"""Verify an atlas export against its exact evidence revision before regeneration."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from .atlas import context_query, result_query
from .db import Snapshot
from .domain import utc_now


def reproduce_atlas(database, package_path: Path, format: str = 'html', output: Path | None = None):
    with zipfile.ZipFile(package_path) as package:
        manifest = json.loads(package.read('manifest.json'))
        if manifest.get('schema') == 'observatory-composed-report-v1':
            from .report_composer import reproduce_report
            return reproduce_report(database, package_path, format, output)
        is_context = manifest.get('schema') == 'observatory-context-research-v1'
        original = json.loads(package.read('context.json' if is_context else 'results.json'))
    digest = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
    if digest != manifest.get('result_sha256'):
        raise ValueError('Research package result checksum failed')
    query = {**manifest['query'], 'revision': manifest['dataset_revision']}
    view = context_query(database, **query) if is_context else result_query(database, **query)
    with database.session() as session:
        for expected in manifest.get('source_snapshots', []):
            snapshot = session.get(Snapshot, expected['id'])
            if not snapshot or snapshot.sha256 != expected['sha256']:
                raise ValueError('This package requires its matching evidence database and source archives')
            if hashlib.sha256(Path(snapshot.path).read_bytes()).hexdigest() != snapshot.sha256:
                raise ValueError('Archived source checksum failed')
    # Ordering and provenance belong to the research output as well as the totals.
    keys = ('query', 'revision', 'estimates') if is_context else ('query', 'revision', 'summary', 'geographies', 'coverage', 'margin_definition')
    for key in keys:
        if view[key] != original[key]:
            raise ValueError('Analytical output differs; retain the original application version for exact reproduction')
    if is_context:
        from .atlas_reporting import context_export
        content, _ = context_export(view, format, manifest.get('presentation'))
    else:
        from .atlas_api import _result_export
        content, _ = _result_export(view, format, manifest.get('presentation'))
    output = output or database.settings.data_dir / 'exports' / f"reproduced-atlas-{query['state'] or 'US'}-r{view['revision']}-{utc_now().replace(':', '-')}.{format}"
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Output already exists; choose a new filename')
    output.write_bytes(content)
    return {'output': str(output), 'revision': view['revision'], 'results_agree': True, 'source_hashes_verified': True}
