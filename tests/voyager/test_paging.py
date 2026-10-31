import pytest

from async_linkedinlib import Cursor
from async_linkedinlib import ProtocolError
from async_linkedinlib.resources import paging


def collection(elements, paging_=None, token=None):
    found = {"elements": elements, "metadata": {"paginationToken": token}}
    if paging_ is not None:
        found["paging"] = paging_
    return found


def read(element):
    return element.get("id")


def test_capped_page_advances_by_what_the_server_served():
    found = collection([{"id": str(n)} for n in range(10)], {"start": 0, "count": 10, "total": 100})
    page = paging.page(found, read, "op", "q", 0, 50)
    assert page.next == Cursor("op", "q", 10, None)
    assert page.total == 100


def test_missing_total_continues_while_pages_are_non_empty():
    found = collection([{"id": "a"}], {"start": 0, "count": 1}, token="t2")
    page = paging.page(found, read, "op", "q", 0, 1)
    assert page.next == Cursor("op", "q", 1, "t2")
    assert page.total is None


def test_missing_paging_count_falls_back_to_the_requested_count():
    page = paging.page(collection([{"id": "a"}]), read, "op", "q", 20, 10)
    assert page.next is not None and page.next.start == 30


def test_last_page_and_empty_page_end_paging():
    last = collection([{"id": "a"}], {"start": 90, "count": 10, "total": 100})
    assert paging.page(last, read, "op", "q", 90, 10).next is None
    empty = collection([], {"start": 0, "count": 10}, token="t")
    assert paging.page(empty, read, "op", "q", 0, 10).next is None


def test_token_comes_only_from_the_new_page():
    found = collection([{"id": "a"}], {"start": 10, "count": 10, "total": 50})
    page = paging.page(found, read, "op", "q", 10, 10)
    assert page.next is not None and page.next.token is None


def test_skipped_entries_still_continue_and_a_separate_estimate_is_shown():
    found = collection([{"other": 1}], {"start": 0, "count": 10, "total": 1000})
    page = paging.page(found, read, "op", "q", 0, 10, total=123456)
    assert page.items == ()
    assert page.next is not None
    assert page.total == 123456


def test_nested_elements_are_read_while_paging_follows_the_collection():
    found = collection([{"cluster": 1}], {"start": 0, "count": 10, "total": 30})
    page = paging.page(found, read, "op", "q", 0, 10, elements=[{"id": "x"}, {"id": "y"}])
    assert page.items == ("x", "y")
    assert page.next is not None and page.next.start == 10


def test_resume_checks_the_cursor():
    assert paging.resume(None, "op", "q") == (0, None)
    assert paging.resume(Cursor("op", "q", 20, "t"), "op", "q") == (20, "t")
    with pytest.raises(ValueError):
        paging.resume(Cursor("op", "other", 20), "op", "q")
    with pytest.raises(ValueError):
        paging.resume("20", "op", "q")  # type: ignore[arg-type]


@pytest.mark.parametrize("data", [{}, {"x": []}, {"x": {"paging": {"total": 1}}}])
def test_collections_without_an_elements_list_are_malformed(data):
    with pytest.raises(ProtocolError):
        paging.collection(data, "x")


def test_page_cursors_only_continue_on_the_session_that_read_them():
    found = collection([{"id": "a"}], {"start": 0, "count": 1, "total": 5})
    cursor = paging.page(found, read, "op", "q", 0, 1, "device-a").next
    assert cursor is not None and cursor.owner == "device-a" and "device-a" not in repr(cursor)
    assert paging.resume(cursor, "op", "q", "device-a") == (1, None)
    with pytest.raises(ValueError, match="different session"):
        paging.resume(cursor, "op", "q", "device-b")
    assert paging.resume(Cursor("op", "q", 3), "op", "q", "device-b") == (3, None)
