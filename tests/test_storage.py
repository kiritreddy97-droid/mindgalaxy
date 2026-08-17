import datetime as dt

import pytest

from mindgalaxy.storage import Storage


@pytest.fixture
def store(tmp_path):
    s = Storage(tmp_path / "test.db")
    yield s
    s.close()


def test_add_and_count(store):
    assert store.count() == 0
    store.add("First thought")
    store.add("Second thought")
    assert store.count() == 2


def test_add_strips_and_rejects_empty(store):
    store.add("  padded text  ")
    entries = store.all_entries()
    assert entries[0].text == "padded text"
    with pytest.raises(ValueError):
        store.add("   ")


def test_add_many_skips_blanks(store):
    ids = store.add_many(["one", "", "  ", "two"])
    assert len(ids) == 2
    assert store.count() == 2


def test_all_entries_sorted_by_date(store):
    now = dt.datetime(2026, 1, 1)
    store.add("later", created_at=now + dt.timedelta(days=5))
    store.add("earlier", created_at=now)
    entries = store.all_entries()
    assert [e.text for e in entries] == ["earlier", "later"]


def test_clear(store):
    store.add("something")
    assert store.count() == 1
    store.clear()
    assert store.count() == 0


def test_persists_across_connections(tmp_path):
    db_path = tmp_path / "persist.db"
    s1 = Storage(db_path)
    s1.add("persisted thought")
    s1.close()

    s2 = Storage(db_path)
    assert s2.count() == 1
    s2.close()
