"""Materialize Railway secret variables as private files for the demo runtime."""
import os
from pathlib import Path

from deployment.runtime import create_deployment_app


def create_app():
    secret_dir = Path('/tmp/iris-railway-secrets')
    secret_dir.mkdir(mode=0o700, exist_ok=True)
    for variable, filename, setting in (
        ('IRIS_BUNDLE_KEY', 'bundle-key', 'IRIS_BUNDLE_KEY_FILE'),
        ('IRIS_DEMO_ACCOUNTS_JSON', 'accounts.json', 'IRIS_DEMO_ACCOUNTS_FILE'),
    ):
        path = secret_dir / filename
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(os.environ[variable])
        os.environ[setting] = str(path)
    return create_deployment_app()
