from dataclasses import dataclass
from typing import Literal
import praw
import prawcore

from .errors import *

@dataclass(init=False, repr=True, eq=True)
class SubmissionInfo:
    subreddit: str
    title: str
    author: str
    score: int
    ratio: int
    
    def __init__(self, submission: praw.reddit.models.Submission):
        self.score = str(submission.score)
        if submission.likes == True:
            self.score += chr(0x1f53a) # red up arrow
        elif submission.likes == False:
            self.score += chr(0x1f53d) # blue down button
        if submission.saved:
            self.score += chr(0x1f4be) # floppy disk icon
        self.author = submission.author.name if submission.author is not None else 'deleted-user'
        self.subreddit = submission.subreddit.display_name
        self.title = submission.title
        self.ratio = int(submission.upvote_ratio * 100)
    
    def to_row(self):
        return [self.subreddit, self.title, self.author, f'\'{self.score}', f'\'{self.ratio}%']
        

class PRAWWrapper:
    """A class that wraps around PRAW to provide extra utilities specific to Reddit Sheets."""

    r: praw.Reddit

    def __init__(self, creds: dict, load_user_info: bool = False):
        """Initializes a new PRAW wrapper.

        :param creds: A dictionary of credentials for the user, containing {client_id, client_secret, username, password, user_agent}
        :type creds: dict
        """

        self.r = praw.Reddit(
            client_id = creds["client_id"],
            client_secret = creds["client_secret"],
            username = creds["username"],
            password = creds["password"],
            user_agent = creds["user_agent"]
        )

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

    def get_submissions_and_info(self, submissions: praw.reddit.models.ListingGenerator) -> tuple[list[praw.reddit.models.Submission], list[SubmissionInfo]]:
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
            return (submissions, [SubmissionInfo(s) for s in submissions])
        except (prawcore.exceptions.NotFound, prawcore.exceptions.Redirect):
            raise RedditError("Could not find subreddit.")

    def get_post(self, _id: str) -> praw.reddit.models.Submission | None:
        """Retrieves a Reddit submission by its ID.

        :param _id: The ID of the submission to retrieve
        :type _id: str
        :return: Returns the matching Reddit submission, or None if a matching submission was not found.
        :rtype: praw.reddit.models.Submission | None
        """
        try:
            return self.r.submission(_id)
        except Exception:
            return None
