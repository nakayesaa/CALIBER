"""Initialize private demo data on a persistent volume, without replacing workflow state."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"IRIS1"
AAD = b"IRIS competition data v1"


def initialize_data(bundle: Path, key_file: Path, destination: Path) -> Path:
    payload = bundle.read_bytes()
    if payload[:5] != MAGIC:
        raise ValueError("Unrecognized data bundle")
    digest = hashlib.sha256(payload).hexdigest()
    marker = destination / ".iris-bundle-version"
    if (destination / "data").exists():
        if not marker.is_file() or marker.read_text().strip() != digest:
            raise RuntimeError(
                "Existing persistent data belongs to another bundle. Back up and migrate it explicitly."
            )
        return destination
    key = base64.b64decode(key_file.read_text().strip(), validate=True)
    if len(key) != 32:
        raise ValueError("Data bundle key must contain 32 bytes")
    archive = AESGCM(key).decrypt(payload[5:17], payload[17:], AAD)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination, prefix=".seed-") as temporary:
        stage = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as handle:
            for member in handle.getmembers():
                name = Path(member.name)
                if (
                    name.is_absolute()
                    or ".." in name.parts
                    or not name.parts
                    or name.parts[0] != "data"
                ):
                    raise ValueError("Unsafe data bundle entry")
                if not (member.isfile() or member.isdir()):
                    raise ValueError("Links and special files are forbidden in data bundles")
            handle.extractall(stage, filter="data")
        if not (stage / "data/catalog").is_dir():
            raise ValueError("Data bundle lacks required catalog")
        version_tmp = destination / ".iris-bundle-version.tmp"
        version_tmp.write_text(digest + "\n")
        # Marker precedes rename so an interrupted initialization can safely retry.
        version_tmp.replace(marker)
        (stage / "data").rename(destination / "data")
    return destination


def create_deployment_app():
    from fastapi.staticfiles import StaticFiles

    from services.api.app.demo_auth import install_demo_auth
    from services.api.app.main import create_app

    if os.environ.get("RENDER") and not (
        os.environ.get("IRIS_PUBLIC_ORIGIN") or os.environ.get("RENDER_EXTERNAL_URL")
    ):
        raise RuntimeError("A fixed public origin is required on Render")
    repository = Path(__file__).resolve().parents[1]
    root = initialize_data(
        repository / "deployment/private-data.enc",
        Path(os.environ.get("IRIS_BUNDLE_KEY_FILE", "/etc/secrets/iris-bundle-key")),
        Path(os.environ.get("IRIS_DATA_ROOT", "/var/data/iris")),
    )
    application = create_app(root=root)
    install_demo_auth(application)
    application.mount(
        "/", StaticFiles(directory=repository / "apps/web/dist", html=True), name="web"
    )
    return application
