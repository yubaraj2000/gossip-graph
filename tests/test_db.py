import pytest

from memory import db


@pytest.mark.parametrize("bad", ["", "has space", "x" * 65, "a/b", "w') DETACH DELETE n //"])
def test_graph_name_rejects_unsafe_world_ids(bad):
    with pytest.raises(ValueError):
        db.graph_name(bad)


def test_graph_name_accepts_convex_ids():
    assert db.graph_name("m177e3zakbq26txfhjmd8mtb0s8ga9ef") == "world_m177e3zakbq26txfhjmd8mtb0s8ga9ef"


def test_missing_world_has_no_indexes(world_id):
    assert db.existing_indexes(world_id) == set()


def test_ensure_schema_creates_all_indexes_once(world_id):
    created = db.ensure_schema(world_id)
    assert len(created) == len(db.RANGE_INDEXES) + len(db.VECTOR_INDEXES)
    assert db.ensure_schema(world_id) == []
    assert ("Claim", "embedding", "VECTOR") in db.existing_indexes(world_id)
    assert world_id in db.list_worlds()


def test_worlds_are_isolated(world_id):
    other = world_id + "_b"
    try:
        db.world_graph(world_id).query("CREATE (:Character {id:'p:1', name:'Bram'})")
        db.world_graph(other).query("CREATE (:Character {id:'p:1', name:'Somebody else'})")
        name = db.world_graph(world_id).ro_query("MATCH (c:Character {id:'p:1'}) RETURN c.name").result_set
        assert name == [["Bram"]]
    finally:
        db.world_graph(other).delete()
