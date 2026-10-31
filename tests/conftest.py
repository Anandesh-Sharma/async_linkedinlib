import pytest

from async_linkedinlib import Session


@pytest.fixture
def member_data():
    return {
        "memberID": 12345,
        "firstName": "Test",
        "lastName": "Member",
        "fullName": "Test Member",
        "shortFullName": "Test Member",
        "headline": "Fixture",
    }


@pytest.fixture
def session():
    return Session.from_cookies("test-session-secret", "ajax:1234567890123456789")
