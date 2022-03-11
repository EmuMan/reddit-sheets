import time

import rsheets

def main():
    rs = rsheets.RedditSheets('creds/reddit_creds.json',
                              'creds/google_creds.json')
    
    while True:
        rs.process_commands()
        if time.time() - rs.auth_time > 3600 - 15:
            rs.reauthorize()
        time.sleep(5)

if __name__ == '__main__':
    main()
