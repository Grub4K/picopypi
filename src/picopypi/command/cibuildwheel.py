#!/usr/bin/env python
"""
Plumbing: Build a wheel using cibuildwheel.

It is expected that the build environment has `git` and `cibuildwheel` available.
In case emulation is required, Docker will be used.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import random
import shlex
import string
import subprocess
import sys

import picopypi.build
import picopypi.gitutil

MANYLINUX_ARMV7L_IMAGE = (
    "quay.io/pypa/manylinux_2_31_armv7l"
    "@sha256:3d1bb16c69d0acafcb90fdbaa5e1b9a2d6634089006d76e2427ca6cdae136be0"
)


def configure_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        "repository",
        help=(
            "a git repository url. "
            "If hosted on GitHub, the short form (yt-dlp/picopypi) can be used"
        ),
        type=picopypi.gitutil.repository,
    )
    parser.add_argument(
        "revision",
        help="sha1/sha256 revision to checkout",
        type=picopypi.gitutil.revision,
    )
    parser.add_argument(
        "target",
        choices=picopypi.build.Target,
        metavar="target",
        type=picopypi.build.Target,
        help="target to build the wheel for",
    )
    default = ",".join(abi.name.lower() for abi in picopypi.build.DEFAULT_ABIS)
    parser.add_argument(
        "--abi",
        action="append",
        choices=picopypi.build.Abi,
        type=picopypi.build.Abi,
        help=f"abi to build for; can be passed multiple times (default: {default})",
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
    repo_dir = args.repo_dir.resolve()
    abis = args.abi or picopypi.build.DEFAULT_ABIS
    picopypi.gitutil.create_ignored_folder(repo_dir)
    picopypi.gitutil.create_ignored_folder(args.output_dir)
    source = picopypi.gitutil.clone_or_fetch(repo_dir, args.repository)
    picopypi.gitutil.checkout(source, args.revision)

    print(f"Building {source.name} @ {args.revision}")
    output = args.output_dir.resolve()
    build(source, output, args.target, abis)


def build(
    source: pathlib.Path,
    output: pathlib.Path,
    target: picopypi.build.Target,
    abis: list[picopypi.build.Abi],
    lockfile: str | None = None,
):
    # TODO(Grub4K): Add ability to pass build arguments to builder
    args: list[str] = []

    more = {}
    if lockfile is not None:
        randkey = "".join(random.choices(string.hexdigits, k=20))
        file = f"/tmp/requirements-picopypi-{randkey}.txt"
        more["CIBW_BEFORE_ALL"] = f"echo {shlex.quote(lockfile)} >{file}"
        more["CIBW_BEFORE_BUILD"] = f"pip install --require-hashes --requirement {file}"
        args.append("--no-isolation")

    build_frontend = "build"
    if args:
        build_frontend += f"; args: {shlex.join(args)}"

    try:
        subprocess.check_call(
            ["cibuildwheel"],
            cwd=source,
            env={
                **os.environ,
                "CIBW_PLATFORM": target.platform(),
                "CIBW_ARCHS": target.arch(),
                "CIBW_BUILD": " ".join(target.expand_configuration(abis)),
                "CIBW_BUILD_FRONTEND": build_frontend,
                "CIBW_OUTPUT_DIR": str(output),
                "CIBW_MANYLINUX_ARMV7L_IMAGE": MANYLINUX_ARMV7L_IMAGE,
                **more,
            },
        )

    except FileNotFoundError:
        print("ERROR: cibuildwheel cannot be found", file=sys.stderr)
        sys.exit(1)

    except subprocess.CalledProcessError as error:
        print(f"ERROR: process exited with code {error.returncode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()
        configure_parser(parser)
        run(parser.parse_args())
    except KeyboardInterrupt:
        print("\nERROR: interrupted by user", file=sys.stderr)
        sys.exit(1)
