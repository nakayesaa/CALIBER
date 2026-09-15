"""Tests for shared pipeline file operations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from services.api.app.services.file_io import atomic_write_json, file_sha256


class ExamplePayload(BaseModel):
    value: int


def test_atomic_write_json_supports_models_and_replaces_existing_file(
    tmp_path: Path,
) -> None:
    output = tmp_path / "nested/artifact.json"
    atomic_write_json(output, {"value": 1})
    atomic_write_json(output, ExamplePayload(value=2))

    assert json.loads(output.read_text(encoding="utf-8")) == {"value": 2}
    assert not output.with_suffix(".json.tmp").exists()


def test_file_sha256_reads_complete_content(tmp_path: Path) -> None:
    content = b"caliber-artifact"
    source = tmp_path / "source.bin"
    source.write_bytes(content)
    assert file_sha256(source) == hashlib.sha256(content).hexdigest()
