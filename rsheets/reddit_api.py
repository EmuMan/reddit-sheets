from typing import Literal
import praw
import prawcore

from .errors import *

class PRAWWrapper():
    """A class that wraps around PRAW to provide extra utilities specific to Reddit Sheets."""

    upvoted_posts: set
    downvoted_posts: set
    saved_posts: set

    upvoted_comments: set
    downvoted_comments: set
    saved_comments: set

    r: praw.Reddit

    def __init__(self, creds: dict, load_user_info: bool = False):
        """Initializes a new PRAW wrapper.

        :param creds: A dictionary of credentials for the user, containing {client_id, client_secret, username, password, user_agent}
        :type creds: dict
        """
        self.upvoted_posts = set()
        self.downvoted_posts = set()
        self.saved_posts = set()

        self.upvoted_comments = set()
        self.downvoted_comments = set()
        self.saved_comments = set()

        self.r = praw.Reddit(
            client_id = creds["client_id"],
            client_secret = creds["client_secret"],
            username = creds["username"],
            password = creds["password"],
            user_agent = creds["user_agent"]
        )
        
        if load_user_info: self.reload_user_info()

    def get_submissions(self,
                        subreddit_name: str | None = None,
                        sort: Literal['top', 'hot', 'new', 'controversial'] = 'hot',
                        time_filter: Literal['hour', 'day', 'week', 'month', 'year', 'all'] = 'all',
                        limit: int = 20) -> praw.reddit.models.ListingGenerator:
        """Retrieve a `ListingGenerator` with the given criteria.

        :param subreddit_name: The name of the subreddit to access, or None for the front page, defaults to None
        :type subreddit_name: str | None, optional
        :param sort: The sort type for the post order, defaults to 'hot'
        :type sort: Literal[&#39;top&#39;, &#39;hot&#39;, &#39;new&#39;, &#39;controversial&#39;], optional
        :param time_filter: The time constraint for the posts, defaults to 'all'
        :type time_filter: Literal[&#39;hour&#39;, &#39;day&#39;, &#39;week&#39;, &#39;month&#39;, &#39;year&#39;, &#39;all&#39;], optional
        :param limit: The maximum number of pages to retrieve, defaults to 20
        :type limit: int, optional
        :raises RedditError: If `time_filter` is not one of [hour, day, week, month, year, all].
        :raises RedditError: If `sort` is not one of [top, hot, new, controversial].
        :return: A `ListingGenerator` containing the posts specified in the arguments.
        :rtype: praw.reddit.models.ListingGenerator
        """

        if subreddit_name is None:
            subreddit = self.r.front
        else:
            subreddit = self.r.subreddit(subreddit_name)

        if sort == "top":
            try:
                return subreddit.top(limit=limit, time_filter=time_filter)
            except ValueError:
                raise RedditError("invalid time filter (must be one of: hour, day, week, month, year, all)")
        elif sort == "controversial":
            try:
                return subreddit.controversial(limit=limit, time_filter=time_filter)
            except ValueError:
                raise RedditError("Invalid time filter (must be one of: hour, day, week, month, year, all)")
        elif sort == "hot":
            return subreddit.hot(limit=limit)
        elif sort == "new":
            return subreddit.new(limit=limit)
        else:
            raise RedditError("Invalid sort specifier (must be one of: top, hot, new, controversial)")

    def reload_user_info(self) -> None:
        """Retrieve the upvoted, downvoted, and saved posts from the user and store it locally.
        
        This should only be used infrequently to make sure the internal sets are still correct.
        """
        self.upvoted_posts = set(self.r.user.me().upvoted())
        self.downvoted_posts = set(self.r.user.me().downvoted())
        self.saved_posts = set(self.r.user.me().saved())

    def add_upvote(self, post: praw.reddit.models.Submission) -> None:
        """Add a post to the internal "upvoted" set if it is not already within the set.

        :param post: The post to add to the "upvoted" set.
        :type post: praw.reddit.models.Submission
        """
        self.remove_downvote(post)
        self.upvoted_posts.add(post)
    
    def remove_upvote(self, post: praw.reddit.models.Submission) -> None:
        """Remove a post from the internal "upvoted" set if it is already contained within the set.

        :param post: The post to remove from the "upvoted" set.
        :type post: praw.reddit.models.Submission
        """
        try:
            self.upvoted_posts.remove(post)
        except KeyError:
            pass
    
    def add_downvote(self, post: praw.reddit.models.Submission) -> None:
        """Add a post to the internal "downvoted" set if it is not already within the set.

        :param post: The post to add to the "downvoted" set.
        :type post: praw.reddit.models.Submission
        """
        self.remove_upvote(post)
        self.downvoted_posts.add(post)

    def remove_downvote(self, post: praw.reddit.models.Submission) -> None:
        """Remove a post from the internal "downvoted" set if it is already contained within the set.

        :param post: The post to remove from the "downvoted" set.
        :type post: praw.reddit.models.Submission
        """
        try:
            self.downvoted_posts.remove(post)
        except KeyError:
            pass
    
    def remove_votes(self, post: praw.reddit.models.Submission) -> None:
        """Remove a post from both the "upvote"/"downvote" internal sets if it is already contained within either.

        :param post: The post to remove from the "upvote"/"downvote" set.
        :type post: praw.reddit.models.Submission
        """
        self.remove_upvote(post)
        self.remove_downvote(post)

    def add_saved(self, post: praw.reddit.models.Submission) -> None:
        """Add a post to the internal "saved" set if it is not already within the set.

        :param post: The post to add to the "saved" set.
        :type post: praw.reddit.models.Submission
        """
        self.saved_posts.add(post)

    def remove_saved(self, post: praw.reddit.models.Submission) -> None:
        """Remove a post from the internal "saved" set if it is already contained within the set.

        :param post: The post to remove from the "saved" set.
        :type post: praw.reddit.models.Submission
        """
        try:
            self.saved_posts.remove(post)
        except KeyError:
            pass

    def get_submissions_and_info(self, submissions: praw.reddit.models.ListingGenerator) -> tuple[list[praw.reddit.models.Submission], list[list]]:
        """Return a tuple containing both a list of the submissions and their info.

        The first element of the tuple is a Python list conversion of the `submissions` parameter.
        The second element is a Python list containing the corresponding information from `get_submission_info`.

        :param submissions: The `ListingGenerator` to be converted
        :type submissions: praw.reddit.models.ListingGenerator
        :raises RedditError: If the `ListingGenerator` does not link to a valid subreddit-like source.
        :return: A tuple containing a list of the submissions and their information.
        :rtype: tuple[list[praw.reddit.models.Submission], list[tuple]]
        """
        try:
            submissions = list(submissions)
            return (submissions, [self.get_submission_info(s) for s in submissions])
        except (prawcore.exceptions.NotFound, prawcore.exceptions.Redirect):
            raise RedditError("Could not find subreddit.")

    def get_submission_info(self, s: praw.reddit.models.Submission, upvote_ratio: bool = False) -> list:
        """Return a tuple containing information on the given submission.

        :param s: The submission to retrieve info on.
        :type s: praw.reddit.models.Submission
        :param upvote_ratio: If `False`, the upvote ratio will be returned as `N/A`, defaults to False
        :type upvote_ratio: bool, optional
        :return: A tuple containing: (subreddit_name, post_title, author_name, post_score, upvote_ratio)
        :rtype: tuple
        """
        score = str(s.score)
        if s in self.upvoted_posts:
            score += "+"
        elif s in self.downvoted_posts:
            score += "-"
        if s in self.saved_posts:
            score += "^"
        author_name = s.author.name if s.author is not None else 'deleted-user'
        return [s.subreddit.display_name, s.title, author_name, score, (str(s.upvote_ratio * 100) + "%" if upvote_ratio else "N/A%")]

    def get_post(self, _id: int) -> praw.reddit.models.Submission | None:
        """Retrieves a Reddit submission by its ID.

        :param _id: The ID of the submission to retrieve
        :type _id: int
        :return: Returns the matching Reddit submission, or None if a matching submission was not found.
        :rtype: praw.reddit.models.Submission | None
        """
        try:
            return self.r.submission(_id)
        except Exception:
            return None
