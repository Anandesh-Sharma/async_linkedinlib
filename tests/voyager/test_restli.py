import pytest

from async_linkedinlib.transport.restli import encode


def test_records_lists_and_scalars_follow_the_app_encoder():
    value = {"start": 0, "count": 10, "sortOrder": "REV_CHRON", "flag": True, "ids": [1, 2]}
    assert encode(value) == "(start:0,count:10,sortOrder:REV_CHRON,flag:true,ids:List(1,2))"


def test_reserved_characters_are_escaped_before_uri_encoding():
    assert encode("urn:li:activity:1") == "urn%3Ali%3Aactivity%3A1"
    assert encode("a,b(c)'d%") == "a%2Cb%28c%29%27d%25"
    assert encode("software engineer") == "software%20engineer"
    assert encode("café & co") == "caf%C3%A9%20%26%20co"


def test_empty_strings_and_nested_records():
    assert encode("") == "''"
    assert encode({"query": {"keywords": "x y", "filters": []}}) == (
        "(query:(keywords:x%20y,filters:List()))"
    )


def test_none_fields_are_left_out():
    assert encode({"a": 1, "b": None}) == "(a:1)"


@pytest.mark.parametrize("value", [float("nan"), object(), {"bad key": 1}, {"": 1}])
def test_unencodable_values_are_rejected(value):
    with pytest.raises(ValueError):
        encode(value)


def test_floats_use_plain_decimal_notation_and_bytes_are_refused():
    assert encode(1e20) == "100000000000000000000"
    assert encode(0.25) == "0.25"
    with pytest.raises(ValueError):
        encode(b"ab")
