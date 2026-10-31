from async_linkedinlib.models.posts_results import ScheduledPost
from async_linkedinlib.models.posts_results import SharedPost


def test_shared_post_names_the_plain_share_from_the_entity_urn():
    reply = {"entity": {"entityUrn": "urn:li:fsd_share:urn:li:ugcPost:3000", "status": {}}}
    shared = SharedPost.from_reply(reply)
    assert shared is not None
    assert shared.share_urn == "urn:li:ugcPost:3000"
    assert (shared.activity_urn, shared.post, shared.social_detail_urn, shared.message) == (
        None,
        None,
        None,
        None,
    )
    assert shared.published is False


def test_shared_post_without_any_share_urn_is_none():
    assert SharedPost.from_reply({}) is None
    assert SharedPost.from_reply({"entity": {"entityUrn": "urn:li:fsd_share:"}}) is None


def test_scheduled_post_missing_fields_read_as_none():
    post = ScheduledPost.from_preview(
        {"miniUpdate": {"metadata": {"backendUrn": "urn:li:share:1"}}}
    )
    assert post is not None
    assert (post.share_urn, post.text, post.publish_at, post.description) == (
        "urn:li:share:1",
        None,
        None,
        None,
    )
    assert ScheduledPost.from_preview({"scheduledAt": 1}) is None
