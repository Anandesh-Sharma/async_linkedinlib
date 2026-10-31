"""The app's persisted feed operations, with where each is built in LinkedIn Android 4.1.1267."""

from ...transport.voyager import GraphQLQuery

# feed/pages/main/MainFeedUpdatesConfigFactory.createGraphQLRequest
MAIN_FEED = GraphQLQuery("voyagerFeedDashMainFeed.8a3a2fc70646e2b7462e79e23cee3935", "MainFeed")

# feed/framework/graphql/FeedFrameworkGraphQLClient.feedSingleUpdateByBackendUrnOrNss
UPDATE = GraphQLQuery(
    "voyagerFeedDashUpdates.5f0daf4e88c68281f1fac9d328bc386e", "FeedSingleUpdateByBackendUrnOrNss"
)

# learning/LearningRepository$$ExternalSyntheticLambda0 (CreatorProfileFeedUpdateRepository)
PROFILE_POSTS = GraphQLQuery(
    "voyagerFeedDashProfileUpdates.8f803ebb60ca03b522e43c9a46dd539b",
    "CreatorFeedDashProfileUpdatesByMemberShareFeed",
)
PROFILE_COMMENTS = GraphQLQuery(
    "voyagerFeedDashProfileUpdates.6d854fab352bd47d28325b6abb93c6e8",
    "FeedDashProfileUpdatesByMemberComments",
)
PROFILE_REACTIONS = GraphQLQuery(
    "voyagerFeedDashProfileUpdates.1d5b78d08a87d2367604ab284efe1f1a",
    "FeedDashProfileUpdatesByMemberReactions",
)
# pages/graphql/PagesGraphQLClient.organizationalPageMemberPosts (PagesMemberPostsFeature)
COMPANY_POSTS = GraphQLQuery(
    "voyagerFeedDashOrganizationalPageUpdates.def294ef4d8d43b7b53324bf739d00d3",
    "OrganizationalPageMemberPosts",
)

# feed/framework/action/savestate/SaveStateManager.getSaveStateRequester
SAVE_STATE = GraphQLQuery(
    "voyagerFeedDashSaveStates.26886775a6d430481be84c4ca2eb1a5f", "UpdateSaveStateBySaveStateUrn"
)


# feed/framework/action/updateaction/UpdateActionPublisher.publish(Undo)FeedbackAction
HIDE = GraphQLQuery(
    "voyagerFeedDashUpdateFeedback.46392e3c45b16ecca40508fabcb2b9ab", "FeedbackAction"
)
UNDO_HIDE = GraphQLQuery(
    "voyagerFeedDashUpdateFeedback.27ec6f4a27da65e6f4a9338f8195f37d", "UndoFeedbackAction"
)

# feed/framework/plugin/poll/PollManager.performVote
VOTE = GraphQLQuery(
    "voyagerSocialDashPollVotes.3f3a224fe4f900d90add90c8095a4eb7", "VoteByPollOptionUrn"
)
UNVOTE = GraphQLQuery(
    "voyagerSocialDashPollVotes.686cdba82be7dc6f851fea7ab0a963d8", "UnVoteByPollOptionUrn"
)

# Module keys: FeedModuleKeyUtils.getModuleKey for the post detail page, and the constant
# PagesGraphQLClient.organizationalPageMemberPosts always sends.
DETAIL_MODULE = "feed-item:phone"
COMPANY_MODULE = "ORGANIZATION_MEMBER_FEED_PHONE"
