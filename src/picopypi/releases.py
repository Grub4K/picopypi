from __future__ import annotations

import collections
import collections.abc
import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.request

import packaging.tags
import packaging.utils

REMOTE_RE = re.compile(r"(?:https://github\.com/|git@github\.com:)?(\w+/\w+)(?:\.git)?")


class _InverseSorter:
    def __init__(self, obj, /):
        self.obj = obj

    def __lt__(self, other, /):
        if not isinstance(other, _InverseSorter):
            return NotImplemented
        return other.obj <= self.obj

    def __eq__(self, other, /):
        if not isinstance(other, _InverseSorter):
            return NotImplemented
        return other.obj == self.obj

    def __hash__(self, /):
        return hash(self.obj)

    def __repr__(self, /):
        return f"<{type(self).__name__} of {self.obj!r}>"


def _sort_tag(tag: packaging.tags.Tag):
    interpreter = tag.interpreter[:2]
    version = tag.interpreter[2:]
    variant = ""
    for index, char in enumerate(version):
        if not char.isdecimal():
            version = version[:index]
            variant = version[index:]
            break

    major, minor = int(version[0]), int(version[1:])
    return (interpreter, major, minor, variant, tag.abi)


@dataclasses.dataclass
class Wheel:
    name: str
    url: str
    hash: str
    datetime: dt.datetime

    def __post_init__(
        self,
    ):
        parsed = packaging.utils.parse_wheel_filename(self.name)
        self._package, self._version, _, self._tags = parsed
        self._sort_key = (
            self.package,
            _InverseSorter(self.version),
            tuple(sorted(set(map(_sort_tag, self._tags)))),
        )

    @property
    def package(self, /):
        return self._package

    @property
    def version(self, /):
        return self._version

    @property
    def tags(self, /):
        return self._tags

    def __lt__(self, other, /):
        if not isinstance(other, type(self)):
            return NotImplemented
        return self._sort_key < other._sort_key


def load_from_github_api(repository: str):
    match = REMOTE_RE.fullmatch(repository)
    if not match:
        print(f"Invalid GitHub repository URL: {repository!r}", file=sys.stderr)
        sys.exit(1)

    url = f"https://api.github.com/repos/{match.group(1)}/releases"
    request = urllib.request.urlopen(
        urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    )
    with contextlib.closing(request) as file:
        data = json.load(file)

    return parse(data)


def parse(data) -> collections.abc.Mapping[str, collections.abc.Iterable[Wheel]]:
    packages: dict[str, list[Wheel]] = collections.defaultdict(list)
    for release in data:
        for asset in release["assets"] or ():
            if not asset["name"].endswith(".whl"):
                continue

            algorithm, _, digest = asset["digest"].partition(":")
            if algorithm not in hashlib.algorithms_guaranteed:
                print(f"unsupported hash format: {algorithm!r}", file=sys.stderr)
                continue

            try:
                wheel = Wheel(
                    name=asset["name"],
                    url=asset["browser_download_url"],
                    hash=f"{algorithm}={digest}",
                    datetime=dt.datetime.fromisoformat(asset["created_at"]).astimezone(
                        dt.UTC
                    ),
                )

            except ValueError as error:
                print(error, file=sys.stderr)
                continue

            else:
                packages[wheel.package].append(wheel)

    return packages
