#!/usr/bin/env python
"""
Render released wheels as simple repository API HTML.

Renders all wheels from release on a particular GitHub repository into
simple repository API html files to be hosted by GitHub Pages.
"""

from __future__ import annotations

import argparse
import collections
import collections.abc
import html
import pathlib
import shutil

import picopypi.releases

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


def render_html(
    packages: collections.abc.Mapping[
        str,
        collections.abc.Iterable[picopypi.releases.Wheel],
    ],
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

    target.mkdir(parents=True, exist_ok=True)
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
    packages = picopypi.releases.load_from_github_api(args.repository)
    render_html(packages, pathlib.Path(args.target).resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    configure_parser(parser)
    run(parser.parse_args())
