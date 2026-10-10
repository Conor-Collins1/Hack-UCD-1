"""Database maintenance. Reset is intentionally explicit."""
import argparse
from dotenv import load_dotenv
load_dotenv()
from library import db, trust

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init-db','reset-db','reward-top'])
    parser.add_argument('--confirm-reset', action='store_true')
    args = parser.parse_args()
    if args.command == 'init-db':
        db.init_db()
        print('Database initialised.')
    elif args.command == 'reset-db':
        if not args.confirm_reset:
            parser.error('Reset deletes all data. Add --confirm-reset only for a disposable demo database.')
        db.reset_db()
        print('Database reset.')
    else:
        with db.engine.begin() as conn:
            print('Rewarded:', trust.reward_top_users(conn))

if __name__ == '__main__':
    main()
