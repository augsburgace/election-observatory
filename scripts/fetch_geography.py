"""Download official Census 2024 boundaries and produce local-only GeoJSON assets."""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import httpx
import shapefile
from observatory.registry import all_states

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "frontend" / "public" / "geography"


def normalized_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().replace(" COUNTY", ""))


def load_archive(url: str):
    response = httpx.get(url, follow_redirects=True, timeout=90)
    response.raise_for_status()
    content = response.content
    archive = zipfile.ZipFile(io.BytesIO(content))
    def part(suffix):
        name = next(n for n in archive.namelist() if n.endswith(suffix))
        return io.BytesIO(archive.read(name))
    return shapefile.Reader(shp=part(".shp"), shx=part(".shx"), dbf=part(".dbf"), encoding="utf-8"), hashlib.sha256(content).hexdigest()


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    by_fips = {row["fips"]: row for row in all_states()}
    manifest = {"source": "U.S. Census Bureau", "vintage": "2024", "files": []}
    for kind, url in (
        ("states", "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip"),
        ("counties", "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_5m.zip"),
    ):
        reader, digest = load_archive(url)
        features = []
        for record in reader.iterShapeRecords():
            props = record.record.as_dict()
            info = by_fips.get(props.get("STATEFP"))
            if not info:
                continue
            name = props["NAME"]
            feature_id = f"state:{info['code']}" if kind == "states" else f"{info['code']}:{normalized_name(name)}"
            features.append({"type": "Feature", "id": feature_id,
                "properties": {**props, "id": feature_id, "name": name, "postal": info["code"],
                               "STUSPS": info["code"], "vintage": "2024"},
                "geometry": record.shape.__geo_interface__})
        metadata = {"source": "U.S. Census Bureau", "source_url": url, "archive_sha256": digest,
                    "vintage": "2024", "geography_type": "state" if kind == "states" else "county"}
        if kind == "states":
            (DESTINATION / "states.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features, "metadata": metadata}))
        else:
            for state in all_states():
                selected = [f for f in features if f["properties"]["postal"] == state["code"]]
                (DESTINATION / f"{state['code']}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": selected, "metadata": metadata}))
        manifest["files"].append({"kind": kind, "source_url": url, "sha256": digest, "features": len(features)})
        print(f"{kind}: {len(features)} official boundary features")
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
