import pytest

from tasklog.store import MAX_TITLE_LEN, Store


def test_add_and_list(tmp_path):
    s = Store(tmp_path / "t.db")
    s.add("write report")
    assert [t.title for t in s.list()] == ["write report"]


def test_title_limit(tmp_path):
    s = Store(tmp_path / "t.db")
    with pytest.raises(ValueError):
        s.add("x" * (MAX_TITLE_LEN + 1))


def test_archive_hides_task(tmp_path):
    s = Store(tmp_path / "t.db")
    t = s.add("old")
    s.archive(t.id)
    assert s.list() == []
