# reddit-sheets

A Reddit client that uses Google Sheets as a user interface.

## Setup and Authentication

1. Install the required dependencies by navigating to the project directory and running `python -m pip install requirements.txt`.
2. Create a `creds` folder in the root directory of this project (you can also place it in a different location by modifying `reddit_sheets.py`).
3. Follow [these instructions](https://docs.gspread.org/en/latest/oauth2.html#for-bots-using-service-account) and move the resulting JSON file into the `creds` folder, renaming it to `google_creds.json`. This can also be adjusted in `reddit_sheets.py`.
4. Follow [all of these instructions](https://praw.readthedocs.io/en/stable/getting_started/authentication.html) to get the custom Reddit application set up. Create a file in the `creds` folder named `reddit_creds.json` and put the information specified in the `praw.Reddit` initialization from the provided link, using key names matching the variable names. The final result should look something like this:

    ```json
    {
        "client_id": "XXXXXXXXXXXXXX",
        "client_secret": "XXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "username": "XXXXXXXXXXXXXXXX",
        "password": "XXXXXXXXXXXXXXXX",
        "user_agent": "Reddit Sheets"
    }
    ```

5. Finally, create a Google Sheets project titled "Reddit Sheets", and share it with the email listed in your `google_creds.json` under `client_email`. You should now be able to run the application with `python reddit_sheets.py`.

## How To Use

There are currently two modes that Reddit Sheets can be in: subreddit mode for viewing subreddits or your own frontpage, and post mode, for viewing the content of a specific post.

Reddit Sheets also utilizes two different types of command spaces: the main command space, which is located in the upper left corner of the sheet, and the post command spaces, which can be found to the left of post listings while in subreddit mode. All command spaces are checked at 5 second intervals, and will not be registered until you press enter/return/move off the edited cell.

### Main Commands

- `frontpage` - Enters subreddit mode and lists posts from your front page feed.
- `r/<subreddit>` - Enters subreddit mode and lists posts from the specified subreddit.
- In post mode, any of the [Post Commands](#post-commands) can be used to perform that action on the currently opened post.

### Post Commands

- `upvote` - Upvotes the post on the command's row.
- `downvote` - Downvotes the post on the command's row.
- `clearvote` - Clears any votes on the post on the command's row.
- `save` - Saves the post on the command's row.
- `unsave` - Unsaves the post on the command's row.

One important row to note is the "Status" row that shows up on the right hand side of the post listing in subreddit mode. This is also present to the left of the score in post mode. In these cells, a series of emojis will be used to convey the status of the post:

- 🔞 - The post is marked as NSFW.
- 🔒 - The post has been archived or locked.
- 🖊 - The post has been edited.
- 🔺 - The authenticated user has upvoted the post.
- 🔽 - The authenticated user has downvoted the post.
- 💾 - The authenticated user has saved the post.

## Capabilities and Limitations

Currently, one of the biggest limitations of this "client" (aside from its lack of comprehensive features) is the display of media. By using the `=IMAGE` formula built into Google Sheets, it is possible to display still graphics, but anything moving (or albums of any sort) will only display a link. I have not found a way around this as of now.

Another limitation is cell resizing. It is on my to-do list to see if cells can be dynamically resized to fit large post content so they don't need to constantly be clicked on or edited to see chunks of text or images.
