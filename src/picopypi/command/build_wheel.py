#!/usr/bin/env python
"""
Plumbing: Build a armv7l/macos universal2 wheel.

It is expected that the build environment has `git`, `uv` and `auditwheel` (linux) or `delocate` (macos) available.
If using Docker the used image contains those already, however the instance must support running linux/arm/v7 images.
When building for armv7l `build_wheel.py` will be copied into the image and ran as the entrypoiny using Python 3.10.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import pathlib
import platform
import re
import shlex
import subprocess
import sys

BASE = pathlib.Path().resolve()
REPOS = BASE.joinpath("repos")
DIST = BASE.joinpath("dist")

ENV_VAR_NAME = "PICOPYPI_BUILDER_DOCKER"

ALLOWED_DIGEST_LENGTHS = (hashlib.sha1().digest_size, hashlib.sha256().digest_size)
ALLOWED_DIGEST_RE = re.compile(
    "|".join(rf"[0-9a-fA-F]{{{length * 2}}}" for length in ALLOWED_DIGEST_LENGTHS)
)

MANYLINUX_ABI_VERSIONS = [
    "cp38",
    "cp39",
    "cp310",
    "cp311",
    "cp312",
    "cp313",
    "cp313t",
    "cp314",
    "cp314t",
]


def manylinux_python_from_abi(abi: str):
    version = abi.rstrip("tm")
    return f"/opt/python/{version}-{abi}/bin/python"


@dataclasses.dataclass(slots=True)
class Platform:
    system: str
    machine: str

    def tag(self, /):
        return f"{self.system}@{self.machine}"

    def __str__(self, /):
        return f"{self.system} on {self.machine}"


ARMV7L = Platform("Linux", "armv7l")
MACOS = Platform("Darwin", "arm64")

PLATFORMS = {platform.tag(): platform for platform in (ARMV7L, MACOS)}


def revision(value: str):
    if not ALLOWED_DIGEST_RE.fullmatch(value):
        msg = f"Invalid digest: {value!r}"
        raise ValueError(msg)
    return value


def repository(value: str):
    if "/" not in value:
        msg = f"Invalid repository: {value!r}"
        raise ValueError(msg)
    if ":" not in value:
        value = f"https://github.com/{value}"
    return value


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        "repository",
        help=(
            "a git repository url. "
            "If hosted on GitHub, the short form (yt-dlp/picopypi) can be used"
        ),
        type=repository,
    )
    parser.add_argument(
        "revision",
        help="sha1/sha256 revision to checkout",
        type=revision,
    )
    parser.add_argument(
        "platform",
        choices=PLATFORMS,
        metavar="platform",
        help="the platform to build the wheel for",
    )
    parser.add_argument(
        "python",
        help="path to the python to use for building",
    )
    parser.add_argument(
        "--no-resolve-abi",
        help="do not resolve the python argument as abi tag for a manylinux python binary",
        action="store_true",
    )
    # TODO(Grub4K): Fix this to allow passing all args
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="arguments to pass to setuptools build command",
    )


def run(args: argparse.Namespace):
    python = args.python
    if not args.no_resolve_abi and args.python in MANYLINUX_ABI_VERSIONS:
        python = manylinux_python_from_abi(args.python)

    build(
        args.repository,
        args.revision,
        PLATFORMS[args.platform],
        python,
        args=args.args or None,
    )


def build(
    url: str,
    revision: str,
    expected: Platform,
    python: str,
    /,
    args: list[str] | None = None,
):
    current = Platform(
        platform.system(),
        platform.machine().lower(),
    )

    if expected != current:
        # If we target linux/arm/v7 we can restart into docker for emulation
        if expected.machine == "armv7l":
            if os.environ.get(ENV_VAR_NAME) is not None:
                # We already restarted and it didn't fix it, strange
                print(
                    "ERROR: Successfully restarted into Docker "
                    "but machine and system still mismatch, exiting!",
                    file=sys.stderr,
                )
                sys.exit(1)

            _run_cmd(
                [
                    "docker",
                    "compose",
                    "run",
                    "--build",
                    "--rm",
                    "--env",
                    f"{ENV_VAR_NAME}=1",
                    "--",
                    "build",
                    url,
                    revision,
                    expected.tag(),
                    python,
                    *(args or ()),
                ]
            )
            return

        print(
            f"ERROR: mismatching build platform, expected {expected}, got {current}",
            file=sys.stderr,
        )
        sys.exit(1)

    if python in MANYLINUX_ABI_VERSIONS:
        python = manylinux_python_from_abi(python)

    repository = pathlib.PurePosixPath(url).name

    print(f"Building repository {repository} using Python {python}")

    if args is None:
        config_setting_arg = ()
    else:
        config_setting_arg = (
            f"--config-setting=--build-option=build {shlex.join(args)}",
        )

    git_dir = REPOS / repository

    if not git_dir.is_dir():
        git_dir.mkdir(exist_ok=True)
        _run_cmd(["git", "-C", str(REPOS), "clone", url])
    else:
        _run_cmd(["git", "-C", str(git_dir), "fetch"])

    _run_cmd(
        [
            "git",
            "-C",
            str(git_dir),
            "-c",
            "advice.detachedHead=false",
            "checkout",
            revision,
        ]
    )
    _run_cmd(
        [
            "uv",
            "build",
            "--wheel",
            f"--out-dir={DIST}",
            "--python",
            python,
            *config_setting_arg,
            str(git_dir),
        ]
    )
    _run_cmd(["auditwheel", "repair", *map(str, DIST.glob("*.whl"))])


def _run_cmd(args: list[str], fail=True):
    print(f"Running {shlex.join(args)}")
    process = subprocess.run(args, check=False)
    if fail and process.returncode:
        print(f"ERROR: process exited with code {process.returncode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()
        configure_parser(parser)
        run(parser.parse_args())
    except KeyboardInterrupt:
        print("\nERROR: interrupted by user", file=sys.stderr)
        sys.exit(1)
