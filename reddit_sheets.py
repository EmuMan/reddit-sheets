import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
from datetime import datetime
import json
import praw
import prawcore

alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
scope = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]
    
def safe_request(func, *args):
    # make sure program doesn't crash when requests exceed 100/100s
    # return func(*args)
    try:
        return func(*args)
    except gspread.exceptions.APIError:
        print("Limit of 100 requests per 100 seconds exceeded. Activating cooldown...")
        time.sleep(100) # wait until sure that request limit is reset
        try:
            return func(*args) # try again
        except gspread.exceptions.APIError:
            print("Still recieving error, may not be request limit related. Giving up...")

class RedditError(Exception):
    def __init__(self, message):
        self.message = message

class RedditAPIWrapper():
    def __init__(self, creds):
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
        self.upvoted_posts = set(self.r.user.me().upvoted())
        self.downvoted_posts = set(self.r.user.me().downvoted())
        self.saved_posts = set(self.r.user.me().saved())

    def add_upvote(self, post):
        self.remove_downvote(post)
        self.upvoted_posts.add(post)
    
    def remove_upvote(self, post):
        try:
            self.upvoted_posts.remove(post)
        except KeyError:
            pass
    
    def add_downvote(self, post):
        self.remove_upvote(post)
        self.downvoted_posts.add(post)

    def remove_downvote(self, post):
        try:
            self.downvoted_posts.remove(post)
        except KeyError:
            pass
    
    def remove_votes(self, post):
        self.remove_upvote(post)
        self.remove_downvote(post)

    def add_saved(self, post):
        self.saved_posts.add(post)

    def remove_saved(self, post):
        try:
            self.saved_posts.remove(post)
        except KeyError:
            pass

    def get_submissions_and_info(self, submissions):
        submissions = list(submissions)
        try:
            to_return = (submissions, [self.get_submission_info(s) for s in submissions])
            return to_return
        except (prawcore.exceptions.NotFound, prawcore.exceptions.Redirect):
            raise RedditError("Could not find subreddit.")

    def get_submission_info(self, s, upvote_ratio=False):
        score = str(s.score)
        if s in self.upvoted_posts:
            score += "+"
        elif s in self.downvoted_posts:
            score += "-"
        if s in self.saved_posts:
            score += "^"
        return [s.subreddit.display_name, s.title, s.author.name, score, (str(s.upvote_ratio * 100) + "%" if upvote_ratio else "N/A%")]

    def get_post(self, id):
        try:
            return self.r.submission(id)
        except Exception:
            return None

class CommandCell:
    def __init__(self, sheet, x, y, on_cmd, **kwargs):
        self.x, self.y = x, y
        self.sheet = sheet
        self.on_cmd = on_cmd
        self.kwargs = kwargs

        print("Now monitoring cell %d%s" % (self.y, alphabet[self.x-1]))
    
    def update(self):
        cell_value = safe_request(self.sheet.cell, self.x, self.y).value
        if cell_value != "":
            self.on_cmd(cell_value, **self.kwargs, caller=self)

    def show_response(self, message):
        safe_request(self.sheet.update_cell, self.y, self.x + 1, message)

    def clear(self):
        safe_request(self.sheet.update_cell, self.y, self.x, "")

class RedditSheetsClient:
    def __init__(self):
        with open("reddit_creds.json") as f:
            reddit_creds = json.load(f)

        self.reddit = RedditAPIWrapper(reddit_creds)

        self.authorize()

        self.command_monitor = CommandCell(self.sheet, 1, 1, self.process_root_cmd)
        self.post_monitors = []

        self.current_subreddit = None
        self.current_post_sort = None
        self.current_post_time_filter = None

        self.current_post = None
        self.current_comment_sort = None
        self.current_comment_time_filter = None

        self.iteration = 0

        self.mode = "subreddit"

        self.posts = []

    def authorize(self):
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open("Reddit Sheets").sheet1
        self.auth_time = time.time()
        print("Sheets API successfully authorized,", datetime.now())
    
    def show_error(self, error, clear=False):
        if clear:
            self.sheet.clear()
        print("Error:", error)
        self.command_monitor.show_response("Error: " + error)

    def set_cell(self, row, col, value):
        # safe wrapper for setting a cell
        safe_request(self.sheet.update_cell, row, col, value)

    def insert_row(self, values, index):
        # safe wrapper for setting a row
        safe_request(self.sheet.insert_row, values, index)

    def delete_row(self, index):
        # safe wrapper for deleting a row
        safe_request(self.sheet.delete_row, index)

    def clear_sheet(self):
        # safe wrapper for clearing the spreadsheet
        safe_request(self.sheet.clear)

    def insert_rows(self, rows, index, extra=None):
        print("Inserting %d rows into the document..." % len(rows))
        added = []
        for i, row in enumerate(rows):
            info = (i + index, row)
            if extra:
                info += (extra[i],)
            added.append(info)
            self.insert_row(row, index=i + index)
        print("Done.")
        return added
    
    def show_posts(self, subreddit=None, sort=None, time_filter=None, extend=False):
        self.mode = "subreddit"
        subreddit_str = "r/" + subreddit if subreddit else "frontpage"
        subreddit_str += ", " + ((sort if sort != "controversial" else "most controversial") if sort else "hot")
        if sort in ["top", "controversial"]:
            if time_filter == "all":
                subreddit_str += " of all time"
            elif time_filter in ["year", "month", "week"]:
                subreddit_str += " of this " + time_filter
            else:
                subreddit_str += " of the past " + time_filter
        
        self.command_monitor.show_response(subreddit_str)
        print("Gathering posts for %s..." % subreddit_str)

        if extend:
            self.iteration += 1
        else:
            self.iteration = 0
            self.posts = []

        try:
            posts = self.reddit.get_submissions(subreddit, sort, time_filter, limit=20*(self.iteration+1))
            posts, post_info = self.reddit.get_submissions_and_info(posts)
            self.posts.extend(posts[-20:])
        except RedditError as e:
            self.show_error(e.message)
            return

        if not extend:
            self.insert_row(["Subreddit", "Title", "Author", "Score"], 2)
        self.insert_rows(post_info[-20:], 3 + self.iteration * 20)

    def display_post(self, post):
        self.current_post = post
        self.mode = "post"
        info = self.reddit.get_submission_info(post, upvote_ratio=True)
        info_dict = dict(zip(["subreddit", "title", "author", "score", "ratio"], info)) # god this is bad
        post_content = post.selftext
        image = False
        if post_content == "":
            post_content = post.url
            image = post_content.endswith((".jpg", ".png", ".gif"))
        rows = []
        rows.append([info_dict["title"]])
        rows.append(["From r/" + info_dict["subreddit"] + " by " + info_dict["author"]])
        rows.append([])
        rows.append(["", post_content])
        rows.append([])
        rows.append([info_dict["score"], info_dict["ratio"]])
        self.insert_rows(rows, 2)
        if image:
            self.set_cell(5, 2, self.image(post_content))
    
    def refresh_post_score(self):
        score, ratio = self.reddit.get_submission_info(self.current_post, upvote_ratio=True)[3:5]
        self.set_cell(7, 1, score)
        self.set_cell(7, 2, ratio)        

    def get_post_on_row(self, args, args_index):
        try:
            post_index = int(args[args_index]) - 3
        except IndexError:
            self.show_error("Not enough arguments for request.")
            return None
        except ValueError:
            self.show_error("Non-integer post index.")
            return None
        
        if post_index < 0 or post_index >= len(self.posts):
            self.show_error("No post on that row.")
            return None
        else:
            return post_index

    def update_post(self, index):
        updated_info = self.reddit.get_submission_info(self.posts[index])
        self.delete_row(index + 3)
        self.insert_row(updated_info, index + 3)

    def image(self, link):
        return f"=IMAGE(\"{link}\")"

    def process_root_cmd(self, cmd, **kwargs):
        args = cmd.split(" ")

        # Goto subreddit
        if args[0] == "frontpage" or args[0].startswith("r/"):
            self.clear_sheet()
            sort = None
            time_filter = None
            self.current_subreddit = None if args[0] == "frontpage" else args[0][2:]
            if len(args) >= 2:
                sort = args[1]
                self.current_post_sort = sort
                if len(args) == 3:
                    time_filter = args[2]
                    self.current_post_time_filter = args[2]
                elif len(args) > 3:
                    self.show_error("Too many arguments for subreddit request.")
                    return
            self.show_posts(self.current_subreddit, sort, time_filter)

        # Switch sort
        elif args[0] in ["top", "hot", "new", "controversial"]:
            self.clear_sheet()
            if self.mode == "subreddit":
                self.current_post_sort = args[0]
                time_filter = None
                if len(args) == 2:
                    time_filter = args[1]
                    self.current_post_time_filter = args[1]
                elif len(args) > 2:
                    self.show_error("Too many arguments for sort request.")
                    return
                self.show_posts(self.current_subreddit, self.current_post_sort, time_filter)
            elif self.mode == "post":
                pass

        # Switch time filter
        elif args[0] in ["all", "day", "week", "hour", "month", "year"]:
            self.clear_sheet()
            if self.mode == "subreddit":
                self.current_post_time_filter = args[0]
                self.show_posts(self.current_subreddit, self.current_post_sort, self.current_post_time_filter)
            elif self.mode == "post":
                pass

        # Get more posts or comments
        elif args[0] == "more":
            self.command_monitor.clear()
            if self.mode == "subreddit":
                self.show_posts(self.current_subreddit, self.current_post_sort, self.current_post_time_filter, extend=True)
            elif self.mode == "post":
                pass

        # Refresh current subreddit/post and configuration
        elif args[0] == "refresh":
            self.clear_sheet()
            if self.mode == "subreddit":
                self.show_posts(self.current_subreddit, self.current_post_sort, self.current_post_time_filter)
            elif self.mode == "post":
                self.display_post(self.current_post)
        
        # Clear the page
        elif args[0] == "clear":
            self.clear_sheet()

        # Give link for a post or comment
        elif args[0] == "link":
            self.command_monitor.clear()
            if self.mode == "subreddit":
                post_index = self.get_post_on_row(args, 1)
                if post_index != None:
                    self.command_monitor.show_response(self.posts[post_index].shortlink)
            elif self.mode == "post":
                pass

        # Upvote a post or comment
        elif args[0] == "upvote":
            self.command_monitor.clear()
            if self.mode == "subreddit":
                post_index = self.get_post_on_row(args, 1)
                if post_index != None:
                    self.posts[post_index].upvote()
                    self.reddit.add_upvote(self.posts[post_index])
                    self.command_monitor.show_response("Upvoted post on row %d" % (post_index + 3))
                    self.update_post(post_index)
            elif self.mode == "post":
                self.reddit.add_upvote(self.current_post)
                self.refresh_post_score()

        # Downvote a post or comment
        elif args[0] == "downvote":
            self.command_monitor.clear()
            if self.mode == "subreddit":
                post_index = self.get_post_on_row(args, 1)
                if post_index != None:
                    self.posts[post_index].downvote()
                    self.reddit.add_downvote(self.posts[post_index])
                    self.command_monitor.show_response("Downvoted post on row %d" % (post_index + 3))
                    self.update_post(post_index)
            elif self.mode == "post":
                self.reddit.add_downvote(self.current_post)
                self.refresh_post_score()

        # Clear the vote on a post or comment
        elif args[0] == "clear_vote":
            self.command_monitor.clear()
            if self.mode == "subreddit":
                post_index = self.get_post_on_row(args, 1)
                if post_index != None:
                    self.posts[post_index].clear_vote()
                    self.reddit.remove_votes(self.posts[post_index])
                    self.command_monitor.show_response("Cleared vote on post on row %d" % (post_index + 3))
                    self.update_post(post_index)
            elif self.mode == "post":
                self.reddit.remove_votes(self.current_post)
                self.refresh_post_score()

        # Save a post or comment
        elif args[0] == "save":
            self.command_monitor.clear()
            if self.mode == "subreddit":
                post_index = self.get_post_on_row(args, 1)
                if post_index != None:
                    self.posts[post_index].save()
                    self.reddit.add_saved(self.posts[post_index])
                    self.command_monitor.show_response("Saved post on row %d" % (post_index + 3))
                    self.update_post(post_index)
            elif self.mode == "post":
                self.reddit.add_saved(self.current_post)
                self.refresh_post_score()

        # Unsave a post or comment
        elif args[0] == "unsave":
            self.command_monitor.clear()
            if self.mode == "subreddit":
                post_index = self.get_post_on_row(args, 1)
                if post_index != None:
                    self.posts[post_index].unsave()
                    self.reddit.remove_saved(self.posts[post_index])
                    self.command_monitor.show_response("Unsaved post on row %d" % (post_index + 3))
                    self.update_post(post_index)
            elif self.mode == "post":
                self.reddit.remove_saved(self.current_post)
                self.refresh_post_score()

        # Open a post
        elif args[0] == "open":
            self.clear_sheet()
            if len(args) == 2:
                post = self.reddit.get_post(args[1])
                if post == None:
                    self.show_error("Could not find post with ID " + args[1])
                else:
                    self.command_monitor.show_response("Post at URL: " + post.shortlink)
                    self.display_post(post)
            else:
                self.show_error("Must specify a single post ID")

        # Reload user info
        elif args[0] == "reload":
            self.command_monitor.clear()
            self.command_monitor.show_response("Getting user info...")
            self.reddit.reload()
            self.command_monitor.show_response("User info successfully reloaded!")

        # Command not found
        else:
            self.show_error("Command \"%s\" not recognized" % cmd)

    def command_monitor_loop(self, delay):
        while(1):
            self.command_monitor.update()
            if time.time() - self.auth_time > 3600 - delay * 2 - 5:
                print("Reauthorizing client...")
                self.client.login()
                print("Client successfully reauthorized.")
            time.sleep(delay)

def main():
    sheets_client = RedditSheetsClient()
    sheets_client.command_monitor_loop(10)

if __name__ == "__main__":
    main()