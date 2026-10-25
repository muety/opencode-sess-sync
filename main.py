import argparse
import logging
import sys
import time

import httpx2

from client import OpenCodeClient, SyncError
from config import DEFAULT_CONFIG_PATH, load_config
from sync import run_once


def main() -> None:
    parser = argparse.ArgumentParser(prog='opencode-sess-sync', description='Sync OpenCode sessions between a local instance and a remote hub.')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument('--dry-run', action='store_true', help='print the plan without applying it')
    parser.add_argument('--daemon', action='store_true', help='keep running and reconcile every --interval seconds')
    parser.add_argument('--interval', type=float, default=300)
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)
    logging.getLogger('httpx2').setLevel(logging.WARNING)  # drop per-request 'HTTP Request: ...' lines
    log = logging.getLogger('opencode-sess-sync')

    config = load_config(args.config)

    local = OpenCodeClient(config.local_url, config.local_token)
    hub = OpenCodeClient(config.hub_url, config.hub_token)

    try:
        while True:
            try:
                run_once(local, hub, config, dry_run=args.dry_run)
            except (SyncError, httpx2.RequestError) as exc:
                log.error('sync failed: %s', exc)
                if not args.daemon:
                    sys.exit(1)
            if not args.daemon:
                return
            time.sleep(args.interval)
    finally:
        local.close()
        hub.close()


if __name__ == '__main__':
    main()
