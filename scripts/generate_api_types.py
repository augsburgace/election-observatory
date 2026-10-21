"""Generate TypeScript request/schema types from the actual FastAPI OpenAPI schema."""
from __future__ import annotations

import json

from observatory.api import app
from observatory.settings import PROJECT_ROOT


def typescript(schema: dict) -> str:
    if '$ref' in schema:
        return schema['$ref'].rsplit('/', 1)[-1]
    if 'enum' in schema:
        return ' | '.join(json.dumps(value) for value in schema['enum']) or 'never'
    if 'const' in schema:
        return json.dumps(schema['const'])
    if 'anyOf' in schema or 'oneOf' in schema:
        return ' | '.join(typescript(item) for item in schema.get('anyOf', schema.get('oneOf', [])))
    if 'allOf' in schema:
        return ' & '.join(typescript(item) for item in schema['allOf'])
    kind = schema.get('type')
    if kind == 'array':
        return f'Array<{typescript(schema.get("items", {}))}>'
    if kind == 'object' or 'properties' in schema:
        required = schema.get('required', [])
        properties = '; '.join(f'{json.dumps(name)}{"" if name in required else "?"}: {typescript(value)}' for name, value in schema.get('properties', {}).items())
        additional = schema.get('additionalProperties')
        if additional:
            properties += ('; ' if properties else '') + '[key: string]: ' + (typescript(additional) if isinstance(additional, dict) else 'unknown')
        return '{ ' + properties + ' }' if properties else 'Record<string, unknown>'
    return {'string': 'string', 'integer': 'number', 'number': 'number', 'boolean': 'boolean', 'null': 'null'}.get(kind, 'unknown')


def main():
    schema = app.openapi()
    output = PROJECT_ROOT / 'frontend' / 'src' / 'generated' / 'api.ts'
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ['// Generated from FastAPI OpenAPI by scripts/generate_api_types.py. Do not edit.\n']
    for name, definition in schema['components']['schemas'].items():
        lines.append(f'export type {name} = {typescript(definition)};\n')
    output.write_text('\n'.join(lines))
    print(output)


if __name__ == '__main__':
    main()
