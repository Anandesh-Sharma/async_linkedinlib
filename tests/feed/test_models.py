from async_linkedinlib.models.content import Post
from async_linkedinlib.models.feed import Reactor
from async_linkedinlib.models.feed import SavedPost


def test_update_reads_post_fields_and_viewer_reaction(fx):
    post = Post.from_update(fx.make_update("1000", header="Someone likes this", reacted="PRAISE"))
    assert post is not None
    assert post.urn == post.activity_urn == "urn:li:activity:1000"
    assert (
        post.update_urn == "urn:li:fsd_update:(urn:li:activity:1000,MAIN_FEED,EMPTY,DEFAULT,false)"
    )
    assert post.text == "Synthetic post"
    assert post.age == "2h"
    assert post.context == "Someone likes this"
    assert post.content_type == "image"
    assert post.counts.viewer_reacted is True
    assert post.counts.viewer_reaction == "PRAISE"
    assert post.author is not None and post.author.profile_urn == fx.PROFILE
    assert post.author.public_id == "test-member"
    assert post.can_share is False
    assert post.poll is None


def test_share_url_drops_the_query_that_names_the_viewer(fx):
    post = Post.from_update(fx.make_update("1000"))
    assert post is not None
    assert post.share_url == "https://www.linkedin.com/posts/test_activity-1000-x"


def test_context_update_keeps_the_thread_and_the_feed_activity(fx):
    post = Post.from_update(fx.make_update("1000", thread="urn:li:ugcPost:3000"))
    assert post is not None
    assert post.urn == "urn:li:ugcPost:3000"
    assert post.activity_urn == "urn:li:activity:1000"


def test_modules_without_an_actor_are_not_posts(fx):
    assert Post.from_update(fx.module()) is None
    assert Post.from_update(fx.make_update(actor=False)) is None


def test_full_screen_video_layout_carries_actor_and_commentary(fx):
    video = {
        "actor": fx.actor_block("Video Page"),
        "commentary": {"text": "Video caption"},
        "saveState": {"saved": False},
    }
    update = fx.make_update(text=None, actor=False, content={"largeSingleVideoComponent": video})
    post = Post.from_update(update)
    assert post is not None
    assert post.author is not None and post.author.name == "Video Page"
    assert post.text == "Video caption"
    assert post.content_type == "largeSingleVideo"


def test_poll_options_line_up_with_summaries_and_votes(fx):
    poll = {
        "question": {"text": "Which one?"},
        "multiSelect": False,
        "pollOptions": [
            {
                "pollOptionUrn": "urn:li:fsu_pollOption:urn:li:pollOption:(urn:li:poll:1,11)",
                "option": {"text": "First"},
            },
            {
                "pollOptionUrn": "urn:li:fsu_pollOption:urn:li:pollOption:(urn:li:poll:1,12)",
                "option": {"text": "Second"},
            },
        ],
        "pollSummary": {
            "uniqueVotersCount": 7,
            "closed": False,
            "pollOptionSummaries": [{"voteCount": 5}],
            "votedPollOptionUrns": ["urn:li:fsu_pollOption:urn:li:pollOption:(urn:li:poll:1,12)"],
        },
    }
    post = Post.from_update(fx.make_update(content={"pollComponent": poll}))
    assert post is not None and post.poll is not None
    assert post.content_type == "poll"
    assert post.poll.question == "Which one?"
    assert post.poll.voters == 7 and post.poll.closed is False
    first, second = post.poll.options
    assert (first.text, first.votes, first.voted) == ("First", 5, False)
    assert (second.text, second.votes, second.voted) == ("Second", None, True)


def test_reactor_reads_the_lockup_card():
    reactor = Reactor.from_reaction(
        {
            "actorUrn": "urn:li:fsd_profile:ACoReactor",
            "reactionType": "EMPATHY",
            "reactorLockup": {
                "title": {"text": "Reacting Member"},
                "subtitle": {"text": "Fixture role"},
                "label": {"text": "2nd"},
                "navigationUrl": "https://www.linkedin.com/in/ACoReactor?x=1",
            },
        }
    )
    assert reactor is not None
    assert reactor.urn == "urn:li:fsd_profile:ACoReactor"
    assert reactor.reaction == "EMPATHY"
    assert (reactor.name, reactor.headline, reactor.degree) == (
        "Reacting Member",
        "Fixture role",
        "2nd",
    )
    assert reactor.url == "https://www.linkedin.com/in/ACoReactor"
    assert Reactor.from_reaction({}) is None


def test_saved_post_reads_the_result_card():
    saved = SavedPost.from_result(
        {
            "trackingUrn": "urn:li:activity:1000",
            "actorTrackingUrn": "urn:li:member:42",
            "title": {"text": "Test Member"},
            "primarySubtitle": {"text": "Fixture headline"},
            "secondarySubtitle": {"text": "3d •  "},
            "summary": {"text": "Saved text"},
            "navigationUrl": "https://www.linkedin.com/feed/update/urn:li:activity:1000?x=1",
            "actorNavigationUrl": "https://www.linkedin.com/in/ACoTest?miniProfileUrn=x",
            "image": {
                "attributes": [
                    {
                        "detailData": {
                            "nonEntityProfilePicture": {"profile": {"entityUrn": "urn:li:p:1"}}
                        }
                    }
                ]
            },
        }
    )
    assert saved is not None
    assert saved.urn == "urn:li:activity:1000"
    assert (saved.text, saved.age) == ("Saved text", "3d")
    assert saved.url == "https://www.linkedin.com/feed/update/urn:li:activity:1000"
    assert saved.author is not None
    assert saved.author.urn == "urn:li:member:42"
    assert saved.author.profile_urn == "urn:li:p:1"
    assert saved.author.url == "https://www.linkedin.com/in/ACoTest"
    assert SavedPost.from_result({"title": {"text": "No URN"}}) is None
