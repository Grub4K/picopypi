#!/usr/bin/env python
"""
Build a armv7l wheel using Docker.

This file will be copied into the image and ran as the entrypoiny using Python 3.10.
The Docker instance should support running linux/arm/v7 images.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
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


INTERPRETERS = [
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


def _python_from_abi(abi: str):
    version = abi.rstrip("tm")
    return f"/opt/python/{version}-{abi}/bin/python"


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
        "--abi",
        help="abi version to build for (default: %(default)s)",
        choices=INTERPRETERS,
        metavar="...",
        default="cp3120",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="arguments to pass to setuptools build command",
    )


def run(args: argparse.Namespace):
    if os.environ.get(ENV_VAR_NAME) is None:
        # Strip `picopypi armv7l` args and rerun this file using docker
        remaining = sys.argv[2:]
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
                *remaining,
            ]
        )
        return

    build_wheel_armv7l(
        args.repository,
        args.revision,
        _python_from_abi(args.abi),
        args=args.args or None,
    )


def build_wheel_armv7l(
    url: str,
    revision: str,
    python: str,
    /,
    args: list[str] | None = None,
):
    repository = pathlib.PurePosixPath(url).name

    msg = f"Building repository {repository}"
    if python is not None:
        msg += f" using Python {python}"
    print(msg)

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

    _run_cmd(["git", "-C", str(git_dir), "checkout", revision])
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
    parser = argparse.ArgumentParser()
    configure_parser(parser)
    run(parser.parse_args())
