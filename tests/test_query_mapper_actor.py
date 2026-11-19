from core.query_mapper import QueryMapper


def test_current_actor_placeholder_is_resolved():
    mapper = QueryMapper({
        "table": "items", "pk": "id", "fixed_where": "owner='{{current_user_id}}'", "param_map": {},
    })
    where = mapper.build_where({"__current_user_id": "alice"})
    assert "owner='alice'" in where.sql
