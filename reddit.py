import praw
import prawcore

submissions = []

class RedditError(Exception):
    def __init__(self, message):
        self.message = message

class RedditAPIWrapper():
    def __init__(self, creds):
        self.upvoted = set()
        self.downvoted = set()
        self.saved = set()

        self.r = praw.Reddit(
            client_id = creds["client_id"],
            client_secret = creds["client_secret"],
            username = creds["username"],
            password = creds["password"],
            user_agent = creds["user_agent"]
        )

        print("Logged in as:", self.r.user.me())

        print("Getting extra user info...")
        self.reload()
        print("\tDone.")

    def get_submissions(self, subreddit=None, sort="hot", time_filter="all", limit=20):
        int(limit)

        if not sort:
            sort = "hot"
        if not time_filter:
            time_filter = "all"

        if subreddit == None:
            subreddit = self.r.front
        else:
            subreddit = self.r.subreddit(subreddit)

        if sort == "top":
            try:
                return subreddit.top(limit=limit, time_filter=time_filter)
            except ValueError:
                raise RedditError("invalid time filter (must be one of: all, day, week, year, hour, month)")
        elif sort == "controversial":
            try:
                return subreddit.controversial(limit=limit, time_filter=time_filter)
            except ValueError:
                raise RedditError("Invalid time filter (must be one of: all, day, week, year, hour, month)")
        elif sort == "hot":
            return subreddit.hot(limit=limit)
        elif sort == "new":
            return subreddit.new(limit=limit)
        else:
            raise RedditError("Invalid sort specifier (must be one of: top, hot, new, controversial)")

    def reload(self):
        self.upvoted = set(self.r.user.me().upvoted())
        self.downvoted = set(self.r.user.me().downvoted())
        self.saved = set(self.r.user.me().saved())

    def add_upvote(self, post):
        self.remove_downvote(post)
        self.upvoted.add(post)
    
    def remove_upvote(self, post):
        try:
            self.upvoted.remove(post)
        except KeyError:
            pass
    
    def add_downvote(self, post):
        self.remove_upvote(post)
        self.downvoted.add(post)

    def remove_downvote(self, post):
        try:
            self.downvoted.remove(post)
        except KeyError:
            pass
    
    def remove_votes(self, post):
        self.remove_upvote(post)
        self.remove_downvote(post)

    def add_saved(self, post):
        self.saved.add(post)

    def remove_saved(self, post):
        try:
            self.saved.remove(post)
        except KeyError:
            pass

    def get_submissions_and_info(self, submissions):
        submissions = list(submissions)
        try:
            return submissions, [self.get_submission_info(s) for s in submissions]
        except (prawcore.exceptions.NotFound, prawcore.exceptions.Redirect):
            raise RedditError("Could not find subreddit.")

    def get_submission_info(self, s):
        score = str(s.score)
        if s in self.upvoted:
            score += "+"
        elif s in self.downvoted:
            score += "-"
        if s in self.saved:
            score += "^"
        return [s.subreddit.display_name, s.title, s.author.name, score]