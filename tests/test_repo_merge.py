"""The three-way merge of a profile fragment into one repo JSON file (spec Part 2)."""
from loadout import repo_merge as rm

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def test_pointer_round_trips_slashes_and_tildes():
    assert rm.pointer(("mcpServers", "a/b~c")) == "mcpServers/a~1b~0c"
    assert rm.unpointer("mcpServers/a~1b~0c") == ("mcpServers", "a/b~c")


def test_an_mcp_server_is_one_entry():
    got = dict(rm.leaves({"mcpServers": {"x": {"command": "npx", "args": ["-y", "a@1"]}}, "env": {"A": "1"}}))
    assert got == {("mcpServers", "x"): {"command": "npx", "args": ["-y", "a@1"]}, ("env", "A"): "1"}


def test_a_missing_entry_without_a_record_is_added_and_recorded():
    m = rm.merge({}, {"a": {"b": 1}}, {})
    assert m.after == {"a": {"b": 1}} and m.added == ["a/b"] and m.record == {"a/b": 1}


def test_the_input_is_not_changed():
    current = {"a": {"b": 1}}
    rm.merge(current, {"a": {"c": 2}}, {})
    assert current == {"a": {"b": 1}}


def test_a_profile_update_applies_when_the_file_has_the_recorded_value():
    m = rm.merge({"a": 1}, {"a": 2}, {"a": 1})
    assert m.after == {"a": 2} and m.updated == ["a"] and m.record == {"a": 2}


def test_a_teammate_change_is_kept_and_offered_once():
    m = rm.merge({"a": 5}, {"a": 2}, {"a": 1})
    assert m.after == {"a": 5} and [d.pointer for d in m.differs] == ["a"]
    assert m.record == {"a": 2}
    again = rm.merge({"a": 5}, {"a": 2}, m.record)
    assert again.after == {"a": 5} and again.differs == [] and again.kept


def test_take_uses_the_profile_value():
    m = rm.merge({"a": 5}, {"a": 2}, {"a": 1}, take=True)
    assert m.after == {"a": 2} and m.record == {"a": 2} and m.updated == ["a"]


def test_a_value_a_person_removed_is_offered_not_added_back():
    m = rm.merge({}, {"a": 2}, {"a": 1})
    assert m.after == {} and m.differs[0].theirs is rm.MISSING


def test_an_unchanged_profile_keeps_a_changed_file_silently():
    m = rm.merge({"a": 5}, {"a": 1}, {"a": 1})
    assert m.after == {"a": 5} and m.differs == [] and m.kept and m.record == {"a": 1}


def test_without_a_record_another_value_stays_and_is_not_recorded():
    m = rm.merge({"a": 5}, {"a": 2}, {})
    assert m.after == {"a": 5} and m.left and m.record == {} and m.differs == []


def test_a_value_the_repo_already_had_is_not_recorded():
    m = rm.merge({"a": 2}, {"a": 2}, {})
    assert m.record == {} and m.after == {"a": 2}


def test_list_entries_are_added_and_only_those_are_recorded():
    m = rm.merge({"l": ["mine"]}, {"l": ["mine", "x"]}, {})
    assert m.after == {"l": ["mine", "x"]} and m.record == {"l": ["x"]}


def test_a_list_entry_a_person_removed_stays_removed_even_with_take():
    m = rm.merge({"l": []}, {"l": ["x"]}, {"l": ["x"]}, take=True)
    assert m.after == {"l": []} and m.kept_removed and m.record == {"l": ["x"]}


def test_an_entry_the_profile_dropped_is_removed_when_unchanged():
    m = rm.merge({"a": 1, "b": 2, "l": ["x", "mine"]}, {"b": 2}, {"a": 1, "l": ["x"]})
    assert m.after == {"b": 2, "l": ["mine"]} and sorted(m.removed) == ["a", 'l: "x"']


def test_a_dropped_entry_a_person_changed_stays():
    m = rm.merge({"a": 9}, {}, {"a": 1})
    assert m.after == {"a": 9} and m.removed == [] and m.record == {}


def test_a_dropped_entry_another_profile_recorded_stays():
    m = rm.merge({"a": 1, "l": ["x"]}, {}, {"a": 1, "l": ["x"]}, others=({"a": 1, "l": ["x"]},))
    assert m.after == {"a": 1, "l": ["x"]} and m.removed == []


def test_an_entry_another_profile_recorded_is_recorded_too():
    m = rm.merge({"l": ["x"]}, {"l": ["x"]}, {}, others=({"l": ["x"]},))
    assert m.record == {"l": ["x"]}


def test_a_parent_of_the_wrong_shape_blocks_the_entry():
    m = rm.merge({"a": [1]}, {"a": {"b": 1}}, {})
    assert m.after == {"a": [1]} and m.blocked and m.blocked[0].startswith("a/b: not written")


def test_a_list_where_the_file_has_a_scalar_is_blocked():
    m = rm.merge({"l": "x"}, {"l": ["y"]}, {})
    assert m.after == {"l": "x"} and m.blocked


def test_true_and_one_are_different_values():
    m = rm.merge({"a": 1}, {"a": True}, {"a": 1})
    assert m.after == {"a": True}


def test_a_secret_looking_value_is_recorded_as_a_hash():
    m = rm.merge({}, {"mcpServers": {"gh": {"env": {"GITHUB_TOKEN": TOKEN}}}}, {})
    s = m.record["mcpServers/gh"]
    assert isinstance(s, str) and s.startswith(rm.HASH) and TOKEN not in s
    assert rm.matches(s, {"env": {"GITHUB_TOKEN": TOKEN}})
    assert TOKEN not in rm.show({"env": {"GITHUB_TOKEN": TOKEN}})
