#!/usr/bin/env python
"""
Build all missing wheels from the supplied build jsonc file.
"""

from __future__ import annotations

import argparse
import ast
import collections.abc
import dataclasses
import pathlib

import picopypi.command.build_wheel
import picopypi.gitutil
import picopypi.releases


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--repository",
        type=picopypi.gitutil.repository,
        help="github repository to read the release assets from (default: infer)",
    )
    parser.add_argument(
        "--builds",
        help="file to read desired builds from (default: %(default)s)",
        type=pathlib.Path,
        default="builds.jsonc",
    )
    parser.add_argument(
        "mode",
        help="file to read desired builds from (default: %(default)s)",
        choices=("armv7l", "re-fuse", "macos"),
    )


def run(args: argparse.Namespace):
    repository = args.repository or picopypi.gitutil.infer_repository()
    releases = picopypi.releases.load_from_github_api(repository)
    required_builds = calculate_builds(releases, args.builds)
    if not required_builds:
        print("Nothing to build!")
        return

    print(
        "Builds to be performed:",
        ", ".join(
            f"{build.package} v{build.version} for {build.abi}"
            for build in required_builds
        ),
    )
    for build in required_builds:
        print(f"Building {build.package} v{build.version} for {build.abi}")
        picopypi.command.build_wheel.build(
            build.repository,
            build.revision,
            build.platform,
            build.interpreter,
        )


@dataclasses.dataclass(slots=True)
class Build:
    platform: picopypi.command.build_wheel.Platform
    package: str
    repository: str
    revision: str
    version: str
    interpreter: str
    abi: str


def calculate_builds(
    releases: collections.abc.Mapping[
        str,
        collections.abc.Iterable[picopypi.releases.Wheel],
    ],
    build_file: pathlib.Path,
):
    string = build_file.read_text(encoding="utf-8")
    data = ast.literal_eval(string)

    provided = set()
    # Fuck optimizations; all my homies hate optimizations.
    for wheels in releases.values():
        for wheel in wheels:
            for tag in wheel.tags:
                provided.add((wheel.package, str(wheel.version), tag.abi))

    builds: list[Build] = []
    for package in data["armv7l"]:
        for revision in package["revisions"]:
            for interpreter, abi in revision["builds"].items():
                key = (package["name"], revision["version"], abi)
                if key not in provided:
                    builds.append(
                        Build(
                            platform=picopypi.command.build_wheel.ARMV7L,
                            package=package["name"],
                            repository=package["repository"],
                            revision=revision["revision"],
                            version=revision["version"],
                            interpreter=interpreter,
                            abi=abi,
                        )
                    )

    return builds
