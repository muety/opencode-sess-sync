import os
import re
from dataclasses import dataclass

_SEGMENT = '[^/]+'
_ONE = f'({_SEGMENT})'
_MANY = f'({_SEGMENT}(?:/{_SEGMENT})*)'


@dataclass(frozen=True)
class _Rule:
    local: re.Pattern
    hub: re.Pattern
    local_tokens: tuple[str, ...]
    hub_tokens: tuple[str, ...]


class DirectoryMap:
    """Ordered local <-> hub directory rules, first match wins."""

    def __init__(self, rules: list[_Rule]) -> None:
        self._rules = rules

    @classmethod
    def parse(cls, raw: dict[str, str]) -> 'DirectoryMap':
        rules: list[_Rule] = []
        seen_local: dict[str, str] = {}
        seen_hub: dict[str, str] = {}

        for local_raw, hub_raw in raw.items():
            local_tokens = _tokenize(os.path.expanduser(local_raw), local_raw)
            hub_tokens = _tokenize(hub_raw, hub_raw)  # '~' is only meaningful locally, hub's home directory is unknown here

            if _wildcards(local_tokens) != _wildcards(hub_tokens):
                raise ValueError(f'directories: wildcards of {local_raw!r} and {hub_raw!r} must match in kind and order')

            for seen, tokens, original in ((seen_local, local_tokens, local_raw), (seen_hub, hub_tokens, hub_raw)):
                skeleton = '/'.join('*' if t in ('*', '**') else t for t in tokens)
                if skeleton in seen:
                    raise ValueError(f'directories: {original!r} overlaps with {seen[skeleton]!r}')
                seen[skeleton] = original

            rules.append(_Rule(_compile(local_tokens), _compile(hub_tokens), local_tokens, hub_tokens))

        return cls(rules)

    def to_hub(self, directory: str) -> str | None:
        return self._resolve(directory, to_hub=True)

    def to_local(self, directory: str) -> str | None:
        return self._resolve(directory, to_hub=False)

    def _resolve(self, directory: str, to_hub: bool) -> str | None:
        directory = directory.rstrip('/') or '/'
        for rule in self._rules:
            pattern, tokens = (rule.local, rule.hub_tokens) if to_hub else (rule.hub, rule.local_tokens)
            match = pattern.fullmatch(directory)
            if match:
                return _rebuild(tokens, match.groups())
        return None


def _tokenize(pattern: str, original: str) -> tuple[str, ...]:
    if not pattern.startswith('/'):
        raise ValueError(f'directories: {original!r} must be an absolute path')
    tokens = tuple(pattern.rstrip('/').split('/')[1:])
    if not tokens or '' in tokens:
        raise ValueError(f'directories: {original!r} is empty or contains empty segments')
    for token in tokens:
        if '*' in token and token not in ('*', '**'):
            raise ValueError(f'directories: {original!r}: wildcards must be a whole path segment')
    if tokens.count('**') > 1:
        raise ValueError(f'directories: {original!r} may contain at most one "**"')
    return tokens


def _wildcards(tokens: tuple[str, ...]) -> list[str]:
    return [t for t in tokens if t in ('*', '**')]


def _compile(tokens: tuple[str, ...]) -> re.Pattern:
    parts = [_ONE if t == '*' else _MANY if t == '**' else re.escape(t) for t in tokens]
    return re.compile('/' + '/'.join(parts))


def _rebuild(tokens: tuple[str, ...], captures: tuple[str, ...]) -> str:
    remaining = iter(captures)
    return '/' + '/'.join(next(remaining) if t in ('*', '**') else t for t in tokens)
