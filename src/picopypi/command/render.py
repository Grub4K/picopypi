#!/usr/bin/env python
"""
Render all released wheels into repository API html files to be hosted by GitHub Pages.
"""

from __future__ import annotations

import argparse
import collections
import collections.abc
import contextlib
import dataclasses
import datetime as dt
import hashlib
import html
import itertools
import json
import pathlib
import re
import shutil
import urllib.request

import packaging.tags
import packaging.utils

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
  <title>{title}</title>
</head>
<body>
  <h1>{title}</h1>
  <ul>
{items}  </ul>
</body>
</html>
"""
FILE_TEMPLATE = """\
    <li><a href="{href}#{sha}">
      {name}
    </a></li>
"""
PACKAGE_TEMPLATE = """\
    <li>
      <a href="{href}/">{name}</a>
      <span> (latest: {latest})</span>
    </li>
"""


class _InverseSorter:
    def __init__(self, obj, /):
        self.obj = obj

    def __lt__(self, other, /):
        if not isinstance(other, _InverseSorter):
            return NotImplemented
        return other.obj < self.obj

    def __repr__(self, /):
        return f"<{type(self).__name__} of {self.obj!r}>"


DIGIT_RE = re.compile(r"(\d+)")


def _natural_sort_key(s: str):
    return tuple(
        (int(val) if num else val)
        for val, num in zip(DIGIT_RE.split(s), itertools.cycle((False, True)))
    )


def _sort_tag(tag: packaging.tags.Tag):
    interpreter = tag.interpreter[:2]
    version = tag.interpreter[2:]
    variant = ""
    for index, char in enumerate(version):
        if not char.isdecimal():
            version = version[:index]
            variant[index:]
            break

    major, minor = int(version[0]), int(version[1:])
    return (interpreter, major, minor, variant)


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


def load_from_github_api(url: str):
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

    packages: dict[str, list[Wheel]] = collections.defaultdict(list)
    for release in data:
        for asset in release["assets"] or ():
            algorithm, _, digest = asset["digest"].partition(":")
            if algorithm not in hashlib.algorithms_guaranteed:
                msg = f"unsupported hash format: {algorithm}"
                raise ValueError(msg)

            wheel = Wheel(
                name=asset["name"],
                url=asset["browser_download_url"],
                hash=f"{algorithm}={digest}",
                datetime=dt.datetime.fromisoformat(asset["created_at"]).astimezone(
                    dt.UTC
                ),
            )
            packages[wheel.package].append(wheel)

    return packages


def render_html(
    packages: collections.abc.Mapping[str, collections.abc.Iterable[Wheel]],
    target: pathlib.Path,
):
    packages = {name: sorted(packages[name]) for name in sorted(packages)}

    shutil.rmtree(target, ignore_errors=True)
    for package, files in packages.items():
        package_path = target / package
        package_path.mkdir(parents=True)
        (package_path / "index.html").write_text(
            HTML_TEMPLATE.format(
                title=html.escape(package),
                items="".join(
                    FILE_TEMPLATE.format(
                        name=html.escape(file.name),
                        href=html.escape(file.url, quote=True),
                        sha=html.escape(file.hash, quote=True),
                    )
                    for file in files
                ),
            ),
            encoding="utf-8",
            newline="\n",
        )

    (target / "index.html").write_text(
        HTML_TEMPLATE.format(
            title=html.escape("Available packages"),
            items="".join(
                PACKAGE_TEMPLATE.format(
                    name=html.escape(package),
                    href=html.escape(package, quote=True),
                    latest=html.escape(str(files[0].version), quote=True),
                )
                for package, files in packages.items()
            ),
        ),
        encoding="utf-8",
        newline="\n",
    )


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        "repository",
        help="github repository to read the release assets from",
    )
    parser.add_argument(
        "target",
        help="target directory to write rendered html to",
    )


def run(args: argparse.Namespace):
    url = f"https://api.github.com/repos/{args.repository}/releases"
    target = pathlib.Path(args.target).resolve()

    packages = load_from_github_api(url)
    render_html(packages, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    configure_parser(parser)
    run(parser.parse_args())
