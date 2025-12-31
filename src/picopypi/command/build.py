#!/usr/bin/env python
"""
Build all missing wheels from the supplied build jsonc file.
"""

from __future__ import annotations

import argparse
import ast
import collections.abc
import dataclasses
import itertools
import pathlib
import re

import packaging.version

import picopypi.build
import picopypi.command.cibuildwheel
import picopypi.gitutil
import picopypi.releases


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="only check what would be built, do not perform the actual build",
    )
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
        "--repo-dir",
        help="directory where the repositories will be cloned to (default: %(default)s)",
        type=pathlib.Path,
        default=pathlib.Path("repos"),
    )
    parser.add_argument(
        "--output-dir",
        help="directory to which the finished wheels will be written (default: %(default)s)",
        type=pathlib.Path,
        default=pathlib.Path("wheels"),
    )


def run(args: argparse.Namespace):
    repository = args.repository or picopypi.gitutil.infer_repository()
    releases = picopypi.releases.load_from_github_api(repository)

    builds = gather_build_infos(releases, args.builds)
    groups = list(group_builds(builds))
    if not groups:
        print("Nothing to build!")
        return

    targets = [
        build_pass.target
        for group in groups
        for build in group.builds
        for build_pass in build.passes
    ]
    targetss = len(targets)
    native_targets = sum(1 for target in targets if target.native())
    if not args.dry_run and not native_targets:
        print(f"All build passes ({targetss}) have been skipped!")
        return

    print(f"Build passes to be performed: {native_targets} / {targetss}")
    repos = args.repo_dir.resolve()
    source = pathlib.Path()
    output = args.output_dir.resolve()
    if not args.dry_run:
        picopypi.gitutil.create_ignored_folder(repos)
        picopypi.gitutil.create_ignored_folder(output)

    for group in groups:
        print(f"Building {group.package}")
        if not args.dry_run:
            source = picopypi.gitutil.clone_or_fetch(repos, group.repository)

        for build in group.builds:
            print(f"=> Building {build.version} ({build.revision})")
            if not args.dry_run:
                picopypi.gitutil.checkout(source, build.revision)

            for build_pass in build.passes:
                native = build_pass.target.native()
                message = "Build" if native else "Skip (non native)"
                print(
                    f"=> => {message}: {build_pass.target} with",
                    ", ".join(abi.value for abi in build_pass.abis),
                )
                if not native:
                    continue
                if not args.dry_run:
                    picopypi.command.cibuildwheel.build(
                        source,
                        output,
                        build_pass.target,
                        build_pass.abis,
                    )


@dataclasses.dataclass(slots=True)
class BuildGroup:
    package: str
    repository: str

    builds: list[Build]


@dataclasses.dataclass(slots=True)
class Build:
    version: packaging.version.Version
    revision: str
    passes: list[BuildPass]


@dataclasses.dataclass(slots=True)
class BuildPass:
    target: picopypi.build.Target
    abis: list[picopypi.build.Abi]


def group_builds(build_infos: collections.abc.Iterable[BuildInfo]):
    def build_group_key(build_info: BuildInfo):
        return build_info.package, build_info.repository

    def build_key(build_info: BuildInfo):
        return build_info.version, build_info.revision

    def pass_key(build_info: BuildInfo):
        return build_info.target

    def sort_key(build_info: BuildInfo):
        return (
            build_group_key(build_info)
            + build_key(build_info)
            + (pass_key(build_info),)
        )

    build_infos = sorted(build_infos, key=sort_key)
    for (package, repository), group_infos in itertools.groupby(
        build_infos,
        key=build_group_key,
    ):
        builds: list[Build] = []
        for (version, revision), build_infos in itertools.groupby(
            group_infos,
            key=build_key,
        ):
            passes: list[BuildPass] = []
            for target, pass_infos in itertools.groupby(
                build_infos,
                key=pass_key,
            ):
                passes.append(
                    BuildPass(
                        target,
                        sorted(info.abi for info in pass_infos),
                    )
                )

            builds.append(Build(version, revision, passes))

        yield BuildGroup(package, repository, builds)


@dataclasses.dataclass(slots=True)
class BuildInfo:
    package: str
    repository: str

    revision: str
    version: packaging.version.Version

    target: picopypi.build.Target
    abi: picopypi.build.Abi


def gather_build_infos(
    releases: collections.abc.Mapping[
        str,
        collections.abc.Iterable[picopypi.releases.Wheel],
    ],
    build_file: pathlib.Path,
):
    string = build_file.read_text(encoding="utf-8")
    data = ast.literal_eval(string)

    wheels = itertools.chain.from_iterable(releases.values())
    provided = expand_wheels(wheels)

    for build_group in data["build"]:
        package = build_group["package"]
        repository = build_group["repository"]
        for build in build_group["builds"]:
            revision = build["revision"]
            version = packaging.version.parse(build["version"])
            targets = build["targets"]
            abis = build["abis"]

            for target, abi in itertools.product(targets, abis):
                key = _SatisfactionKey(package, version, target)
                abis = provided.get(key, ())
                satisfied = abi in abis or (
                    # The tag could be satisfied by `abi3`
                    abi.startswith("cp3")
                    and not abi.endswith(("t", "m"))
                    and "abi3" in abis
                )

                if not satisfied:
                    yield BuildInfo(
                        package=package,
                        version=version,
                        repository=repository,
                        revision=revision,
                        target=picopypi.build.Target(target),
                        abi=picopypi.build.Abi(abi),
                    )


@dataclasses.dataclass(order=True, frozen=True, slots=True)
class _SatisfactionKey:
    package: str
    version: packaging.version.Version
    target: str


_PLATFORM_RE = re.compile(
    "|".join(
        [
            "manylinux",
            "musllinux",
            "macosx",
        ]
    )
)


def expand_wheels(wheels: collections.abc.Iterable[picopypi.releases.Wheel]):
    result: dict[_SatisfactionKey, set[str]] = collections.defaultdict(set)

    # TODO(Grub4K): Expand this when more targets get added
    for wheel in wheels:
        for tag in wheel.tags:
            match = _PLATFORM_RE.match(tag.platform)
            if not match:
                msg = f"Unhandled platform tag during expansion: {tag.platform}"
                raise ValueError(msg)

            key = _SatisfactionKey(
                wheel.package,
                wheel.version,
                "_".join(
                    (
                        tag.platform[: match.end()],
                        tag.platform.rpartition("_")[2],
                    )
                ),
            )
            result[key].add(tag.abi)

    return dict(result)
