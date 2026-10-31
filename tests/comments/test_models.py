import pytest

from async_linkedinlib.models.comments import Comment
from async_linkedinlib.models.feed import Reactor
from async_linkedinlib.resources.comments.urns import CommentUrn


def test_comment_urn_reads_both_spellings_of_one_comment():
    thread = CommentUrn.parse("urn:li:comment:(ugcPost:1000,2001)")
    entity = CommentUrn.parse("urn:li:fsd_comment:(2001,urn:li:ugcPost:1000)")
    assert thread == entity
    assert entity.urn == "urn:li:comment:(ugcPost:1000,2001)"
    assert thread.entity_urn == "urn:li:fsd_comment:(2001,urn:li:ugcPost:1000)"
    assert thread.post_urn == "urn:li:ugcPost:1000"


@pytest.mark.parametrize(
    "value",
    ["urn:li:activity:1000", "urn:li:comment:(activity:1000,x)", "comment:(activity:1,2)", None],
)
def test_comment_urn_rejects_other_values(value):
    with pytest.raises(ValueError):
        CommentUrn.parse(value)


def test_rest_comment_shape_and_missing_fields_read_as_none():
    comment = Comment.from_json(
        {
            "urn": "urn:li:comment:(ugcPost:1000,2001)",
            "commentary": {"text": "Synthetic"},
            "commenter": {
                "urn": "urn:li:member:42",
                "title": {"text": "Test Member"},
                "subtitle": {"text": "Fixture headline"},
                "actorUnion": {"profileUrn": "urn:li:fsd_profile:ACoTestProfile"},
            },
        }
    )
    assert comment is not None
    assert comment.post_urn == "urn:li:ugcPost:1000"
    assert comment.author is not None
    assert comment.author.headline == "Fixture headline"
    assert comment.author.profile_urn == "urn:li:fsd_profile:ACoTestProfile"
    assert comment.author.public_id is None
    assert comment.entity_urn is None
    assert comment.edited is None
    assert comment.counts.viewer_reaction is None
    assert comment.counts.reactions == 0
    assert comment.mentions == ()
    assert comment.replies == ()


def test_records_without_identity_are_not_comments_or_reactions():
    assert Comment.from_json({"entityUrn": "urn:li:fsd_comment:(1,urn:li:activity:2)"}) is None
    assert Reactor.from_reaction({"reactionType": "LIKE"}) is None
