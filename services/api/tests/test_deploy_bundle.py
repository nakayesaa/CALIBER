import base64
import io
import tarfile

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from deployment.runtime import AAD, MAGIC, initialize_data


def bundle(tmp_path, names=None):
    key = AESGCM.generate_key(bit_length=256)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as output:
        directory = tarfile.TarInfo("data/catalog")
        directory.type = tarfile.DIRTYPE
        output.addfile(directory)
        for name in names or ["data/catalog/example.txt"]:
            item = tarfile.TarInfo(name)
            content = b"source evidence"
            item.size = len(content)
            output.addfile(item, io.BytesIO(content))
    nonce = b"123456789012"
    encrypted = tmp_path / "bundle.enc"
    encrypted.write_bytes(MAGIC + nonce + AESGCM(key).encrypt(nonce, archive.getvalue(), AAD))
    secret = tmp_path / "key"
    secret.write_text(base64.b64encode(key).decode())
    return encrypted, secret


def test_initialization_retains_workflow_after_restart(tmp_path):
    encrypted, secret = bundle(tmp_path)
    root = tmp_path / "persistent"
    initialize_data(encrypted, secret, root)
    workflow = root / "data/workflow.json"
    workflow.write_text("verified")
    initialize_data(encrypted, secret, root)
    assert workflow.read_text() == "verified"


def test_tampered_bundle_rejected_before_seed(tmp_path):
    encrypted, secret = bundle(tmp_path)
    payload = bytearray(encrypted.read_bytes())
    payload[-1] ^= 1
    encrypted.write_bytes(payload)
    with pytest.raises(InvalidTag):
        initialize_data(encrypted, secret, tmp_path / "persistent")
    assert not (tmp_path / "persistent/data").exists()


def test_path_traversal_rejected(tmp_path):
    encrypted, secret = bundle(tmp_path, ["data/../../escaped"])
    with pytest.raises(ValueError, match="Unsafe"):
        initialize_data(encrypted, secret, tmp_path / "persistent")
    assert not (tmp_path / "escaped").exists()


def test_changed_bundle_does_not_overwrite_persistent_data(tmp_path):
    encrypted, secret = bundle(tmp_path)
    root = tmp_path / "persistent"
    initialize_data(encrypted, secret, root)
    encrypted.write_bytes(encrypted.read_bytes() + b"changed")
    with pytest.raises(RuntimeError, match="Back up"):
        initialize_data(encrypted, secret, root)
    assert (root / "data/catalog/example.txt").read_text() == "source evidence"
