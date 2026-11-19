# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

TOKEN = "t0ken-" + "x" * 26


@pytest.fixture
def settings(tmp_path):
    from hornet.config import Settings
    return Settings(data_dir=tmp_path / "data", access_token=TOKEN, camera_name="Teststand 1")


@pytest.fixture
def store(settings):
    from hornet.config import ensure_private_dir
    from hornet.store import Store
    ensure_private_dir(settings.data_dir)
    st = Store(settings.db_path)
    yield st
    st.close()


@pytest.fixture
def make_app(settings, tmp_path):
    from fastapi.testclient import TestClient
    from hornet.server import create_app

    clients = []

    def _make(**over):
        for k, v in over.items():
            setattr(settings, k, v)
        app = create_app(settings, start_engine=False, load_model=False, env_path=tmp_path / ".env")
        c = TestClient(app, base_url="http://testserver")
        clients.append(c)
        return app, c

    yield _make
    for c in clients:
        c.close()


def login(client):
    r = client.post("/api/login", json={"token": TOKEN})
    assert r.status_code == 200, r.text
    return r
