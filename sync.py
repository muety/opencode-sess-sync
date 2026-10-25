import logging
from dataclasses import dataclass

from client import OpenCodeClient
from config import Config
from state import load_state, save_state

log = logging.getLogger('opencode-sess-sync')


@dataclass
class Plan:
    push: set[str]
    pull: set[str]
    delete_local: set[str]
    delete_hub: set[str]
    entries: dict[str, dict]
    conflicts: set[str]


def run_once(local: OpenCodeClient, hub: OpenCodeClient, config: Config, dry_run: bool) -> None:
    local.info()
    hub.info()

    state = load_state(config.state_path)
    local_sessions = local.list_sessions()
    hub_sessions = hub.list_sessions()
    active = {'local': local.active_session_ids(), 'hub': hub.active_session_ids()}

    plan = build_plan(local_sessions, hub_sessions, state, active)
    expand_cascades(plan, local_sessions, hub_sessions, active)
    _log_plan(plan)

    if dry_run:
        return

    for sid in plan.delete_hub:
        hub.delete_session(sid)
    for sid in plan.delete_local:
        local.delete_session(sid)

    push_dir = config.directories
    pull_dir = {target: source for target, source in config.directories.items()}

    synced = dict(plan.entries)
    push_synced = copy(local, hub, local_sessions, hub_sessions, plan.push, push_dir)
    synced.update({sid: {'local': s, 'hub': t} for sid, (s, t) in push_synced.items()})
    pull_synced = copy(hub, local, hub_sessions, local_sessions, plan.pull, pull_dir)
    synced.update({sid: {'local': t, 'hub': s} for sid, (s, t) in pull_synced.items()})

    save_state(config.state_path, synced)


def build_plan(local: dict, hub: dict, state: dict, active: dict) -> Plan:
    push: set[str] = set()
    pull: set[str] = set()
    delete_local: set[str] = set()
    delete_hub: set[str] = set()

    entries: dict[str, dict] = {}
    conflicts: set[str] = set()
    busy = active['local'] | active['hub']

    for sid in sorted(set(local) | set(hub)):
        local_session, hub_session = local.get(sid), hub.get(sid)
        local_updated = local_session['time']['updated'] if local_session else None
        hub_updated = hub_session['time']['updated'] if hub_session else None
        known = state.get(sid, {})
        known_local = known.get('local')
        known_hub = known.get('hub')

        if local_session and hub_session:
            if known_local is not None and known_hub is not None:
                local_changed = local_updated > known_local
                hub_changed = hub_updated > known_hub

                if local_changed and hub_changed:
                    conflicts.add(sid)
                    entries[sid] = known
                elif local_changed:
                    if sid in busy:
                        entries[sid] = known
                    else:
                        push.add(sid)
                elif hub_changed:
                    if sid in busy:
                        entries[sid] = known
                    else:
                        pull.add(sid)
                else:
                    entries[sid] = {'local': local_updated, 'hub': hub_updated}
            elif local_updated == hub_updated:
                entries[sid] = {'local': local_updated, 'hub': hub_updated}
            elif sid in busy:
                entries[sid] = {'local': local_updated, 'hub': hub_updated}
            elif local_updated > hub_updated:
                push.add(sid)
            else:
                pull.add(sid)
        elif local_session:
            if known.get('hub') is not None:
                delete_local.add(sid)  # deleted on the hub -> mirror the deletion here
            elif sid in busy:
                entries[sid] = {'local': local_updated, 'hub': None}
            else:
                push.add(sid)
        else:
            if known.get('local') is not None:
                delete_hub.add(sid)  # deleted locally -> mirror the deletion on the hub
            elif sid in busy:
                entries[sid] = {'local': None, 'hub': hub_updated}
            else:
                pull.add(sid)

    # sessions running on the target side cannot be deleted from it -> keep the old state entry so the deletion is retried next time
    for sid in delete_hub & active['hub']:
        entries[sid] = state[sid]
    for sid in delete_local & active['local']:
        entries[sid] = state[sid]
    delete_hub -= active['hub']
    delete_local -= active['local']

    plan = Plan(push, pull, delete_local, delete_hub, entries, conflicts)
    if conflicts:
        log.warning('skipped concurrent-modification conflicts: %s', sorted(conflicts))
    return plan


def expand_cascades(plan: Plan, local: dict, hub: dict, active: dict) -> None:
    # replacing a session deletes its whole subtree on the target (DELETE cascades to children), so every target-side descendant must be re-imported as well
    _expand(plan.push, hub, local, 'local', 'hub', active)
    _expand(plan.pull, local, hub, 'hub', 'local', active)


def copy(source: OpenCodeClient, target: OpenCodeClient, source_sessions: dict, target_sessions: dict, session_ids: set, directory_map: dict) -> dict[str, tuple[int, int]]:
    synced: dict[str, tuple[int, int]] = {}
    target_children = _map_children(target_sessions)
    cascaded_away: set = set()

    for sid in _sort_by_topology(source_sessions, session_ids):
        snapshot = source.export_session(sid)
        info = snapshot['info']

        # target session already exists -> delete and re-import
        if sid in target_sessions and sid not in cascaded_away:
            doomed = {sid} | _descendants(target_children, [sid])
            for doomed_sid in _sort_by_topology(target_sessions, doomed):
                target.delete_session(doomed_sid)
            cascaded_away |= doomed

        directory = directory_map.get(info['location']['directory'])
        imported = target.import_session(snapshot, directory)

        source_updated = info['time']['updated']
        target_updated = imported['time']['updated']
        synced[sid] = (source_updated, target_updated)

    return synced


def _expand(to_copy: set, target: dict, source: dict, source_side: str, target_side: str, active: dict) -> None:
    target_children = _map_children(target)

    for sid in list(to_copy):
        if sid not in target:
            continue
        for child in _descendants(target_children, [sid]):
            if child not in source:
                log.warning('%s is a child of replaced session %s only on %s side; it will be lost', child, sid, target_side)
            elif child not in active[source_side]:
                to_copy.add(child)


def _map_children(sessions: dict) -> dict:  # parent id -> [children ids]
    children: dict = {}
    for sid, session in sessions.items():
        parent = session.get('parentID')
        if parent:
            children.setdefault(parent, []).append(sid)
    return children


def _descendants(children: dict, roots: list) -> set:
    # collect all sessions in the subtrees under roots, incl. children, grandchildren, etc. (roots themselves are not included in the result)
    result: set = set()
    pending = list(roots)
    while pending:
        for child in children.get(pending.pop(), []):
            if child not in result:
                result.add(child)
                pending.append(child)
    return result


def _sort_by_topology(sessions: dict, session_ids) -> list:
    # import requires parents to exist first, so order by depth in the parent chain.
    def depth(sid: str) -> int:
        level, seen = 0, set()
        while True:
            parent = sessions.get(sid, {}).get('parentID')
            if not parent or parent not in sessions or parent in seen:
                return level
            seen.add(sid)
            sid = parent
            level += 1

    return sorted(session_ids, key=depth)


def _log_plan(plan: Plan) -> None:
    log.info('plan: %d push, %d pull, %d delete on hub, %d delete local, %d conflict', len(plan.push), len(plan.pull), len(plan.delete_hub), len(plan.delete_local), len(plan.conflicts))
    for name, sids in (('push', plan.push), ('pull', plan.pull), ('delete_hub', plan.delete_hub), ('delete_local', plan.delete_local)):
        if sids:
            log.debug('%s: %s', name, sorted(sids))
