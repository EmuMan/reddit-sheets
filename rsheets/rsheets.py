from typing import Any, Callable
import json
import time
from datetime import datetime
import enum
from enum import Enum
import os

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import praw

from .utils import ExpandingTable, safe_request, prepad_columns
from .errors import RedditError
from .reddit_api import PRAWWrapper, SubmissionInfo


SCOPE = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]


class RedditSheets:
    
    class DisplayMode(Enum):
        SUBREDDIT = enum.auto()
        POST = enum.auto()
    
    local_sheet: ExpandingTable
    changed: list[tuple[int, int]] # TODO: Optimize API calls by limiting to only changed cells.
    
    current_submissions: list[praw.reddit.models.Submission]
    current_post: praw.reddit.models.Submission

    def __init__(self, reddit_creds_file: str, google_creds_file: str):
        self.local_sheet = ExpandingTable()
        
        self.current_submissions = []
        
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

        self.mode = RedditSheets.DisplayMode.SUBREDDIT
        
    def commit(self) -> None:
        """Commits the local table to Google Sheets"""
        self.worksheet.clear()
        if self.local_sheet.num_rows > 0:
            self.worksheet.insert_rows(self.local_sheet.export(), value_input_option='USER_ENTERED')
            
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
        self.mode = RedditSheets.DisplayMode.SUBREDDIT
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
        
        self.commit()
        
    def show_post(self, post: praw.reddit.models.Submission):
        self.mode = RedditSheets.DisplayMode.POST
        self.current_post = post

        info = SubmissionInfo(post)
        post_content = post.selftext
        if post_content == '':
            post_content = self.imageify(post.url) if post.url.endswith(('.jpg', '.png', '.gif')) else post.url
        
        self.local_sheet.clear()
        self.local_sheet.add_row(['', f'From r/{info.subreddit} by {info.author}'])
        self.local_sheet.add_row(['', info.title])
        self.local_sheet.add_row([])
        for line in post_content.split('\n'):
            self.local_sheet.add_row(['', line])
        self.local_sheet.add_row([])
        self.local_sheet.add_row(['', info.score, info.status])
        
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
                
        elif self.mode == RedditSheets.DisplayMode.POST:
            if root_cmd[0] == 'link':
                self.local_sheet.set_cell(0, 0, self.current_post.shortlink)
                self.commit()
            elif root_cmd[0] == 'upvote':
                self.current_post.upvote()
                self.show_post(self.reddit.r.submission(self.current_post.id))
            elif root_cmd[0] == 'downvote':
                self.current_post.downvote()
                self.show_post(self.reddit.r.submission(self.current_post.id))
            elif root_cmd[0] == 'clearvote':
                self.current_post.clear_vote()
                self.show_post(self.reddit.r.submission(self.current_post.id))
            elif root_cmd[0] == 'save':
                self.current_post.save()
                self.show_post(self.reddit.r.submission(self.current_post.id))
            elif root_cmd[0] == 'unsave':
                self.current_post.unsave()
                self.show_post(self.reddit.r.submission(self.current_post.id))
                
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
