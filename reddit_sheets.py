import gspread
from reddit import RedditAPIWrapper, RedditError
from oauth2client.service_account import ServiceAccountCredentials
import time
import datetime
import json

alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

class CommandCell:
    def __init__(self, sheet, x, y, on_cmd, **kwargs):
        self.x, self.y = x, y
        self.sheet = sheet
        self.on_cmd = on_cmd
        self.kwargs = kwargs

        print("Now monitoring cell %d%s" % (self.y, alphabet[self.x-1]))
    
    def update(self):
        cell_value = self.sheet.cell(self.x, self.y).value
        if cell_value != "":
            self.on_cmd(cell_value, **self.kwargs, caller=self)

    def show_response(self, message):
        self.sheet.update_cell(self.y, self.x + 1, message)

    def clear(self):
        self.sheet.update_cell(self.y, self.x, "")

class RedditSheetsClient:
    def __init__(self, sheet):
        with open("reddit_creds.json") as f:
            reddit_creds = json.load(f)

        self.reddit = RedditAPIWrapper(reddit_creds)

        self.sheet = sheet
        self.command_monitor = CommandCell(self.sheet, 1, 1, self.process_root_cmd)
        self.post_monitors = []

        self.current_subreddit = None
        self.current_sort = None
        self.current_time_filter = None

        self.iteration = 0

        self.posts = []
    
    def show_error(self, error, clear=False):
        if clear:
            self.sheet.clear()
        print("Error:", error)
        self.command_monitor.show_response("Error: " + error)
    
    def show_posts(self, subreddit=None, sort=None, time_filter=None, extend=False):
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
            self.sheet.insert_row(["Subreddit", "Title", "Author", "Score"], 2)
        for info in post_info[-20:]:
            self.sheet.append_row(info)

    def get_post_on_row(self, args, args_index):
        try:
            post_index = int(args[args_index]) - 3
        except IndexError:
            self.show_error("Not enough arguments for link request.")
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
        self.sheet.delete_row(index + 3)
        self.sheet.insert_row(updated_info, index + 3)

    def image(self, link):
        return f"=IMAGE(\"{link}\")"

    def process_root_cmd(self, cmd, **kwargs):
        args = cmd.split(" ")

        # Goto subreddit
        if args[0] == "frontpage" or args[0].startswith("r/"):
            self.sheet.clear()
            sort = None
            time_filter = None
            self.current_subreddit = None if args[0] == "frontpage" else args[0][2:]
            if len(args) >= 2:
                sort = args[1]
                self.current_sort = sort
                if len(args) == 3:
                    time_filter = args[2]
                    self.current_time_filter = args[2]
                elif len(args) > 3:
                    self.show_error("Too many arguments for subreddit request.")
                    return
            self.show_posts(self.current_subreddit, sort, time_filter)

        # Switch sort
        elif args[0] in ["top", "hot", "new", "controversial"]:
            self.sheet.clear()
            self.current_sort = args[0]
            time_filter = None
            if len(args) == 2:
                time_filter = args[1]
                self.current_time_filter = args[1]
            elif len(args) > 2:
                self.show_error("Too many arguments for sort request.")
                return
            self.show_posts(self.current_subreddit, self.current_sort, time_filter)

        # Switch time filter
        elif args[0] in ["all", "day", "week", "hour", "month", "year"]:
            self.sheet.clear()
            self.current_time_filter = args[0]
            self.show_posts(self.current_subreddit, self.current_sort, self.current_time_filter)

        # Get more posts
        elif args[0] == "more":
            self.command_monitor.clear()
            self.show_posts(self.current_subreddit, self.current_sort, self.current_time_filter, extend=True)

        # Refresh current subreddit and configuration
        elif args[0] == "refresh":
            self.sheet.clear()
            self.show_posts(self.current_subreddit, self.current_sort, self.current_time_filter)
        
        # Clear the page
        elif args[0] == "clear":
            self.sheet.clear()

        # Give link for a post
        elif args[0] == "link":
            self.command_monitor.clear()
            post_index = self.get_post_on_row(args, 1)
            if post_index != None:
                self.command_monitor.show_response(self.posts[post_index].shortlink)

        # Upvote a post
        elif args[0] == "upvote":
            self.command_monitor.clear()
            post_index = self.get_post_on_row(args, 1)
            if post_index != None:
                self.posts[post_index].upvote()
                self.reddit.add_upvote(self.posts[post_index])
                self.command_monitor.show_response("Upvoted post on row %d" % (post_index + 3))
                self.update_post(post_index)

        # Downvote a post
        elif args[0] == "downvote":
            self.command_monitor.clear()
            post_index = self.get_post_on_row(args, 1)
            if post_index != None:
                self.posts[post_index].downvote()
                self.reddit.add_downvote(self.posts[post_index])
                self.command_monitor.show_response("Downvoted post on row %d" % (post_index + 3))
                self.update_post(post_index)

        # Clear the vote on a post
        elif args[0] == "clear_vote":
            self.command_monitor.clear()
            post_index = self.get_post_on_row(args, 1)
            if post_index != None:
                self.posts[post_index].clear_vote()
                self.reddit.remove_votes(self.posts[post_index])
                self.command_monitor.show_response("Cleared vote on post on row %d" % (post_index + 3))
                self.update_post(post_index)

        # Save a post
        elif args[0] == "save":
            self.command_monitor.clear()
            post_index = self.get_post_on_row(args, 1)
            if post_index != None:
                self.posts[post_index].save()
                self.reddit.add_saved(self.posts[post_index])
                self.command_monitor.show_response("Saved post on row %d" % (post_index + 3))
                self.update_post(post_index)

        # Unsave a post
        elif args[0] == "unsave":
            self.command_monitor.clear()
            post_index = self.get_post_on_row(args, 1)
            if post_index != None:
                self.posts[post_index].unsave()
                self.reddit.remove_saved(self.posts[post_index])
                self.command_monitor.show_response("Unsaved post on row %d" % (post_index + 3))
                self.update_post(post_index)

        # Reload user info
        elif args[0] == "reload":
            self.command_monitor.show_response("Getting user info...")
            self.reddit.reload()
            self.command_monitor.show_response("User info successfully reloaded!")

        # Testing
        elif args[0] == "test_image":
            self.command_monitor.show_response(self.image("https://i.redd.it/k1nil2bq3dd41.jpg"))

        # Command not found
        else:
            self.show_error("Command \"%s\" not recognized" % cmd)

    def command_monitor_loop(self, delay):
        while(1):
            self.command_monitor.update()
            time.sleep(delay)

def main():
    scope = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open("Reddit Sheets").sheet1

    sheets_client = RedditSheetsClient(sheet)

    print("Sheets API successfully connected!")

    sheets_client.command_monitor_loop(5)

if __name__ == "__main__":
    main()