"""Tests run against the local FalkorDB (docker compose up -d) using throwaway world graphs."""
import uuid

import pytest

from memory import db


@pytest.fixture
def world_id():
    wid = "test_" + uuid.uuid4().hex[:8]
    yield wid
    if db.graph_name(wid) in db.client().list_graphs():
        db.world_graph(wid).delete()
