"""Pack immutable public JSON fragments without changing any analytical bytes.

Run only against a disposable website build. Logical URLs and their SHA-256
values stay intact; the browser retrieves their exact UTF-8 text from a small,
hash-verified container instead of downloading thousands of tiny files.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path, PurePosixPath

PACK_SCHEMA = "observatory-object-packs-v1"
MAX_PACK_OBJECTS = 128
MAX_PACK_BYTES = 256 * 1024
MAX_MEMBER_BYTES = 64 * 1024
MAX_DECODED_BYTES = 100_000_000
OBJECT_HASH = re.compile(r"(?:^|/)([0-9a-f]{64})\.json(?:\.gz)?$")


def safe_public_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("Unsafe public-data path")
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or not name.parts:
        raise ValueError("Unsafe public-data path")
    target = root.joinpath(*name.parts).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Unsafe public-data path")
    return target


def decoded_bytes(path: Path, limit: int = MAX_DECODED_BYTES) -> bytes:
    with path.open("rb") as stream:
        magic = stream.read(2)
        stream.seek(0)
        if magic == b"\x1f\x8b":
            with gzip.GzipFile(fileobj=stream) as packed:
                value = packed.read(limit + 1)
        else:
            value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError("Public JSON exceeds its decoded size limit")
    return value


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _object_hash(name: str) -> str:
    found = OBJECT_HASH.search(name)
    if not name.startswith("objects/") or not found:
        raise ValueError("Packed logical object must retain its content-addressed filename")
    return found[1]


def pack_public_objects(root: Path, manifest: dict, *, max_objects: int = MAX_PACK_OBJECTS,
                        max_pack_bytes: int = MAX_PACK_BYTES,
                        max_member_bytes: int = MAX_MEMBER_BYTES) -> dict:
    """Pack in publication insertion order, then remove only copied member files."""
    if manifest.get("object_packs") or manifest.get("packs"):
        raise ValueError("This public artifact has already been packed")
    if min(max_objects, max_pack_bytes, max_member_bytes) <= 0:
        raise ValueError("Object pack limits must be positive")
    objects = manifest.get("objects", [])
    if not isinstance(objects, list):
        raise ValueError("Invalid public object inventory")
    descriptors = {item["path"]: item for item in objects}
    if len(descriptors) != len(objects):
        raise ValueError("Duplicate public object inventory")
    packs, standalone, mappings, packed_members = [], [], {}, []
    pending = {}
    pending_size = len(b'{"objects":{}}')
    original_bytes = 0

    def flush():
        nonlocal pending, pending_size
        if not pending:
            return
        raw = json.dumps({"objects": pending}, separators=(",", ":"), ensure_ascii=False).encode()
        if len(raw) > max_pack_bytes:
            raise ValueError("Object pack exceeded its declared decoded budget")
        digest = _digest(raw)
        name = f"packs/{digest[:2]}/{digest}.json.gz"
        path = safe_public_path(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = gzip.compress(raw, compresslevel=7, mtime=0)
        path.write_bytes(encoded)
        index = len(packs)
        packs.append({"path": name, "sha256": digest, "bytes": len(encoded),
            "uncompressed_bytes": len(raw), "compression": "gzip"})
        for logical in pending:
            mappings[logical] = index
            packed_members.append(logical)
        pending, pending_size = {}, len(b'{"objects":{}}')

    for name, descriptor in descriptors.items():
        path = safe_public_path(root, name)
        raw = decoded_bytes(path)
        if _digest(raw) != descriptor.get("sha256"):
            raise ValueError("Public aggregate integrity mismatch before packing")
        json.loads(raw)
        original_bytes += len(raw)
        # Larger map/chunk payloads remain independently addressable, so opening
        # one page cannot accidentally download a huge container of unrelated data.
        if len(raw) > max_member_bytes:
            standalone.append(descriptor)
            continue
        if _object_hash(name) != descriptor["sha256"]:
            raise ValueError("Packed aggregate filename does not match its declared hash")
        text = raw.decode("utf-8")
        entry_size = len(json.dumps({name: text}, separators=(",", ":"), ensure_ascii=False).encode()) - 2
        added_size = entry_size + bool(pending)
        if pending and (len(pending) >= max_objects or pending_size + added_size > max_pack_bytes):
            flush()
            added_size = entry_size
        if pending_size + added_size > max_pack_bytes:
            standalone.append(descriptor)
            continue
        pending[name] = text
        pending_size += added_size
    flush()
    # No partial conversion of the source publication is allowed. The caller
    # gives us a disposable copy; all hashes were checked before member removal.
    manifest["object_packs"] = mappings
    manifest["packs"] = packs
    manifest["objects"] = standalone + packs
    manifest["logical_object_count"] = len(objects)
    manifest["transport"] = {"schema": PACK_SCHEMA, "logical_objects": len(objects),
        "packed_objects": len(mappings), "standalone_objects": len(standalone), "pack_files": len(packs),
        "maximum_decoded_pack_bytes": max_pack_bytes, "maximum_pack_objects": max_objects,
        "maximum_member_bytes": max_member_bytes, "original_bytes": original_bytes,
        "integrity": "Container and original object hashes cover their exact decompressed UTF-8 JSON bytes. Original logical URLs, queries and values are unchanged."}
    for name in packed_members:
        safe_public_path(root, name).unlink()
    return manifest["transport"]


class PublicObjectReader:
    """Strict verification reader for both unpacked and packed public editions."""

    def __init__(self, root: Path, manifest: dict):
        self.root = root
        self.physical = {row["path"]: row for row in manifest.get("objects", [])}
        self.mapping = manifest.get("object_packs", {})
        self.packs = manifest.get("packs", [])
        if not isinstance(self.mapping, dict) or not isinstance(self.packs, list):
            raise ValueError("Invalid public object pack index")
        self.members = defaultdict(set)
        for name, index in self.mapping.items():
            _object_hash(name)
            safe_public_path(root, name)
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self.packs):
                raise ValueError("Invalid public object pack index")
            self.members[index].add(name)
        for index, descriptor in enumerate(self.packs):
            if not descriptor.get("path", "").startswith("packs/") or not self.members[index]:
                raise ValueError("Invalid or unused public object pack")
            if self.physical.get(descriptor["path"]) != descriptor:
                raise ValueError("Object pack is absent from the physical inventory")
        self.cache: OrderedDict[int, dict] = OrderedDict()

    def names(self):
        return [name for name in self.physical if name.startswith("objects/")] + list(self.mapping)

    def expected_hash(self, name: str) -> str:
        if name in self.mapping:
            return _object_hash(name)
        if name not in self.physical or not name.startswith("objects/"):
            raise ValueError("Reference names an unpublished logical aggregate")
        return self.physical[name]["sha256"]

    def _container(self, index: int):
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index]
        descriptor = self.packs[index]
        raw = decoded_bytes(safe_public_path(self.root, descriptor["path"]), limit=8 * 1024**2)
        if _digest(raw) != descriptor["sha256"]:
            raise ValueError("Public object pack integrity mismatch")
        payload = json.loads(raw)
        if (not isinstance(payload, dict) or set(payload) != {"objects"}
                or not isinstance(payload["objects"], dict)
                or set(payload["objects"]) != self.members[index]
                or not all(isinstance(item, str) for item in payload["objects"].values())):
            raise ValueError("Public object pack contains missing or undeclared members")
        self.cache[index] = payload["objects"]
        while len(self.cache) > 4:
            self.cache.popitem(last=False)
        return payload["objects"]

    def read(self, name: str) -> bytes:
        expected = self.expected_hash(name)
        if name in self.mapping:
            raw = self._container(self.mapping[name])[name].encode("utf-8")
        else:
            raw = decoded_bytes(safe_public_path(self.root, name))
        if _digest(raw) != expected:
            raise ValueError("Public aggregate integrity mismatch")
        return raw

    def verify_references(self, value):
        if isinstance(value, dict):
            if set(value) == {"$public_ref", "sha256", "bytes"}:
                if self.expected_hash(value["$public_ref"]) != value["sha256"]:
                    raise ValueError("Public aggregate reference hash mismatch")
            elif set(value) == {"$public_chunks"}:
                if not isinstance(value["$public_chunks"], list):
                    raise ValueError("Invalid public array chunks")
                for chunk in value["$public_chunks"]:
                    self.verify_references(chunk)
            else:
                for item in value.values():
                    self.verify_references(item)
        elif isinstance(value, list):
            for item in value:
                self.verify_references(item)
