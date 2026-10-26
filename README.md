# opencode-sess-sync

Replicate [OpenCode](https://opencode.ai) sessions between a local instance and a remote "hub" instance (-> "star" topology of potentially multiple "clients" and a central instance they all sync against) over the [v2 HTTP API](https://opencode.ai/v2/docs/api). Whole sessions are synced via export / import. Latest session (by `time.updated`) wins and deletions propagate as well.

**Assumption:** a session is only ever edited on one machine at a time (i.e. we don't _merge_ individual sessions).

Written with AI assistance 🤖.

## Requirements

- OpenCode 2.x, incl. REST API
    - Listening on `http://127.0.0.1:49374` by default, check `opencode service status`
    - Remote hub will be accessible publicly, so either expose the port in the firewall, use a reverse proxy (like Caddy or such) or a VPN like Tailscale
- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

### Get auth tokens
Both locally and on the remote hub, obtain a short-lived code and exchange it for a token:

```bash
opencode api post /api/pair
```

```bash
curl -H 'Accept: application/json' http://127.0.0.1:49374/auth/connect/<local code>  # connect to local API
curl -H 'Accept: application/json' https://hub.example:49374/auth/connect/<hub code>  # connect to remote hub API
```

The token is then used as the HTTP basic-auth password (username `opencode`, or `OPENCODE_SERVER_USERNAME` if set on the server).

### Create the confing
Create `~/.config/opencode-sess-sync/config.json` from `config.example.json`.

```json
{
  "local": { "url": "http://127.0.0.1:49374", "token": "<local token>" },
  "hub": { "url": "https://hub.example:49374", "token": "<hub token>" }
}
```

### Optional: map directory paths
If the same project lives at different paths on the two machines, map them (local path -> hub path). Omit it if your paths match — sessions then land in the target server's default location.

```json
"directories": { "/home/me/code/foo": "/home/hubuser/code/foo" }
```

Sync state (used to detect deletions) is written to `state.json` next to the config.

## Usage

```bash
uv run main.py --dry-run                    # show the plan, touch nothing
uv run main.py                              # one reconcile pass, good for cron
uv run main.py --daemon --interval 60       # keep running
```

A failing run just exits non-zero (or retries on the next tick in `--daemon` mode). The next run re-derives the full plan from both instances. Sessions that are actively running on either side are skipped until they go idle.

## Developer notes
### Code formatting
```bash
uv run ruff check --fix && uv run ruff format .
```

### Purge session database
```bash
rm ~/.local/share/opencode/opencode.db*
```

## Alternatives
During my research to find a soluton for syncing OpenCode sessions across machines (until implemented natively, see [#54534](https://github.com/anomalyco/opencode/issues/54534)), I considered a bunch of alternatives.

The first draft was simply a bash script that would run on schedule to shut down the `opencode` service, run a [borg](https://www.borgbackup.org/) backup of the SQLite database (incl. incremental backupping, deduplication and compression) against a remote repo and afterwards restart the service again. While this worked in general, I suspected that I'd probably run into "mege conflicts" quite soon. Apart from that, it felt a quite "hacky" and dump.

Second alternative that I considered was to use [LiteFS](https://fly.io/blog/introducing-litefs/) to sync the SQLite in a somewhat more "database-aware" manner. But in my understanding, it wouldn't even have worked conceptually, as the LTX files used by LiteFS operate on individual SQLite pages, which, I thought, would be one level too "low". There wouldn't be a way to sensibly "merge" those in case of multiple writers.

Last, I ended up with this "high-level" approach of using what OpenCode provides through it's REST API, which, I think, is cleanest.
