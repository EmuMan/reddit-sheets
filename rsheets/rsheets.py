import json
import time
from datetime import datetime
import enum
from enum import Enum
import os

import gspread
import gspread_formatting
from oauth2client.service_account import ServiceAccountCredentials
import praw
import prawcore

from .utils import ExpandingTable, prepad_columns
from .errors import RedditError
from .reddit_api import PRAWWrapper, SubmissionInfo


SCOPE = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]


class RedditSheets:
    
    class DisplayMode(Enum):
        SUBREDDIT = enum.auto()
        POST = enum.auto()
    
    local_sheet: ExpandingTable
    
    current_submissions: list[praw.reddit.models.Submission]
    current_post_info: SubmissionInfo | None

    def __init__(self, reddit_creds_file: str, google_creds_file: str):
        self.local_sheet = ExpandingTable()
        
        self.current_submissions = []
        self.current_post_info = None
        
        with open(os.path.join(os.getcwd(), reddit_creds_file)) as f:
            reddit_creds = json.load(f)
        self.reddit = PRAWWrapper(reddit_creds)
        self.log('Logged in as: ' + str(self.reddit.r.user.me()))
        
        google_creds = ServiceAccountCredentials.from_json_keyfile_name(
            os.path.join(os.getcwd(), google_creds_file), SCOPE)
        self._gclient = gspread.authorize(google_creds)
        self.worksheet = self._gclient.open('Reddit Sheets').sheet1
        self.auth_time = time.time()
        self.log('Google Sheets API successfully authorized.')

        self._mode = RedditSheets.DisplayMode.SUBREDDIT
        
    @property
    def mode(self):
        return self._mode
        
    @mode.setter
    def mode(self, value: DisplayMode) -> None:
        self._mode = value
        with gspread_formatting.batch_updater(self.worksheet.spreadsheet) as batch:
            bold = self._mode == RedditSheets.DisplayMode.SUBREDDIT
            batch.format_cell_range(self.worksheet, 'B3:F3', gspread_formatting.models.CellFormat(textFormat=gspread_formatting.models.TextFormat(bold=bold)))
            # batch.format_cell_range(self.worksheet, '8', gspread_formatting.models.CellFormat(wrapStrategy='WRAP')) # don't think this works
            if self.mode == RedditSheets.DisplayMode.POST and self.current_post_info.is_image:
                batch.set_row_height(self.worksheet, '4', 342)
            else:
                batch.set_row_height(self.worksheet, '4', 21)
        
    def commit(self) -> None:
        """Commits the local table to Google Sheets"""
        changed = self.local_sheet.get_changed_rect()
        if changed is None: return
        cell_range = self.worksheet.range(changed[0][0] + 1, changed[1][0] + 1,
                                            changed[0][1] + 1, changed[1][1] + 1)
        for cell in cell_range:
            cell.value = self.local_sheet.get_cell(cell.row - 1, cell.col - 1, sheet_format=True)
        self.worksheet.update_cells(cell_range, value_input_option='USER_ENTERED')
        self.local_sheet.reset_changed()
            
    def update(self) -> None:
        """Updates the local table, pulling from Google Sheets"""
        new_values = self.worksheet.get_values()
        self.local_sheet.rebuild(new_values)
        
    def update_submission_row(self, submission: praw.reddit.models.Submission, row: int) -> None:
        submission = self.reddit.r.submission(id=submission.id) # refresh the submission information
        self.local_sheet.set_row(row, [''] + SubmissionInfo(submission).to_row())
        self.commit()
        
    def show_error(self, row: int, col: int, error: str, clear_sheet: bool = False) -> None:
        if clear_sheet:
            self.local_sheet.initialize(row + 1, col + 1)
        self.local_sheet.set_cell(row, col, error)
        
        self.commit()
        
    def show_submissions(self, submissions: praw.reddit.models.ListingGenerator) -> None:
        self.local_sheet.clear()
        subreddit_str: str
        url_split = submissions.url.split('/')
        if submissions.url == '/hot':
            subreddit_str = 'frontpage'
        else:
            subreddit_str = f'r/{url_split[1]}, {url_split[2]}'
            if 't' in submissions.params:
                # there was a time setting (top or controversial)
                if submissions.params['t'] == 'all':
                    subreddit_str += ' (of all time)'
                else:
                    subreddit_str += f' (of this {submissions.params["t"]})'
        self.local_sheet.add_row(['', subreddit_str])
        self.local_sheet.add_row([])
        self.local_sheet.add_row(['', 'Subreddit', 'Title', 'Author', 'Score', 'Status'])
        self.current_submissions, post_info = self.reddit.get_submissions_and_info(submissions)
        self.local_sheet.add_rows(prepad_columns([info.to_row() for info in post_info], 1))
        
        self.mode = RedditSheets.DisplayMode.SUBREDDIT
        
        self.commit()
        
    def show_post(self, post: praw.reddit.models.Submission):
        try:
            info = self.current_post_info = SubmissionInfo(post)
        except (prawcore.exceptions.NotFound, prawcore.exceptions.Redirect) as e:
            raise RedditError('Post not found')
        post_content = self.imageify(post.url) if info.is_image else (post.url if info.is_link else post.selftext)
        
        self.local_sheet.clear()
        self.local_sheet.add_row(['', f'From r/{info.subreddit} by {info.author}'])
        self.local_sheet.add_row(['', info.title])
        if not info.is_image:
            self.local_sheet.add_row([]) # add an extra row if the text is not an image,
                                         # which allows for safe resizing without affecting autoscaling
        self.local_sheet.add_row([])
        for line in post_content.split('\n'):
            self.local_sheet.add_row(['', line])
        self.local_sheet.add_row([])
        self.local_sheet.add_row(['', info.score, info.status])
        
        self.mode = RedditSheets.DisplayMode.POST
        
        self.commit()
        
    def process_commands(self):
        self.update()
        root_cmd = self.local_sheet.get_cell(0, 0).split(' ')
        if len(root_cmd) == 0:
            return
        
        if root_cmd[0] == 'frontpage' or root_cmd[0].startswith('r/'):
            try:
                self.show_submissions(self.reddit.get_submissions(
                    subreddit_name = None if root_cmd[0] == 'frontpage' else root_cmd[0][2:],
                    sort = root_cmd[1] if len(root_cmd) > 1 else 'hot',
                    time_filter = root_cmd[2] if len(root_cmd) > 2 else 'all'
                ))
            except RedditError as e:
                self.show_error(0, 1, e.message)
                
        match root_cmd[0].split('/'):
            case ['frontpage']:
                self.show_submissions(self.reddit.get_submissions(
                    subreddit_name = None,
                    sort = root_cmd[1] if len(root_cmd) > 1 else 'hot',
                    time_filter = root_cmd[2] if len(root_cmd) > 2 else 'all'
                ))
                return
            case ['r', subreddit]:
                try:
                    self.show_submissions(self.reddit.get_submissions(
                        subreddit_name = subreddit,
                        sort = root_cmd[1] if len(root_cmd) > 1 else 'hot',
                        time_filter = root_cmd[2] if len(root_cmd) > 2 else 'all'
                    ))
                except RedditError as e:
                    self.show_error(0, 1, e.message)
                finally:
                    return
            case ([('http:' | 'https:'), '', ('www.reddit.com' | 'old.reddit.com'), 'r', _, 'comments', id, *_] | 
                  ['post', id]):
                try:
                    self.show_post(self.reddit.r.submission(id))
                except RedditError as e:
                    self.show_error(0, 1, e.message)
                finally:
                    return
            case ['']:
                pass
            case _:
                self.show_error(0, 1, 'Unknown command')
                return
                
        if self.mode == RedditSheets.DisplayMode.POST:
            submission = self.current_post_info.submission
            if root_cmd[0] == 'link':
                self.local_sheet.set_cell(0, 0, submission.shortlink)
                self.commit()
            elif root_cmd[0] == 'upvote':
                submission.upvote()
                self.show_post(self.reddit.r.submission(submission.id))
            elif root_cmd[0] == 'downvote':
                submission.downvote()
                self.show_post(self.reddit.r.submission(submission.id))
            elif root_cmd[0] == 'clearvote':
                submission.clear_vote()
                self.show_post(self.reddit.r.submission(submission.id))
            elif root_cmd[0] == 'save':
                submission.save()
                self.show_post(self.reddit.r.submission(submission.id))
            elif root_cmd[0] == 'unsave':
                submission.unsave()
                self.show_post(self.reddit.r.submission(submission.id))
                
        if self.mode == RedditSheets.DisplayMode.SUBREDDIT:
            for i, submission in enumerate(self.current_submissions, start=3):
                cmd_cell = self.local_sheet.get_cell(i, 0)
                if cmd_cell == 'open':
                    self.show_post(submission)
                elif cmd_cell == 'link':
                    self.local_sheet.set_cell(i, 0, submission.shortlink)
                    self.commit()
                elif cmd_cell == 'upvote':
                    submission.upvote()
                    self.update_submission_row(submission, i)
                elif cmd_cell == 'downvote':
                    submission.downvote()
                    self.update_submission_row(submission, i)
                elif cmd_cell == 'clearvote':
                    submission.clear_vote()
                    self.update_submission_row(submission, i)
                elif cmd_cell == 'save':
                    submission.save()
                    self.update_submission_row(submission, i)
                elif cmd_cell == 'unsave':
                    submission.unsave()
                    self.update_submission_row(submission, i)                    
                    
    def reauthorize(self):
        self.log('Reauthorizing client...')
        self._gclient.login()
        self.auth_time = time.time()
        self.log('\tDone.')
        
    def imageify(self, link: str):
        return f'=IMAGE("{link}")'
    
    def log(self, string: str) -> None:
        timestamp = datetime.now()
        print(f'[{timestamp}]: {string}')
