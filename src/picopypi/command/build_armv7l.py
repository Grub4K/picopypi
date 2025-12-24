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


def _revision(value: str):
    if not ALLOWED_DIGEST_RE.fullmatch(value):
        msg = f"Invalid digest: {value!r}"
        raise ValueError(msg)
    return value


def _repository(value: str):
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
            "Use yt-dlp/picopypi (for GitHub) or full url for other git providers"
        ),
        type=_repository,
    )
    parser.add_argument(
        "revision",
        help="sha1/sha256 revision to checkout",
        type=_revision,
    )
    parser.add_argument(
        "--python",
        help="python version to build for",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="arguments to pass to setuptools build command",
    )


def run(args: argparse.Namespace):
    if os.environ.get(ENV_VAR_NAME) is None:
        # We strip the `picopypi armv7l` part and run this file directly
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

    else:
        build_wheel_armv7l(
            args.repository,
            args.revision,
            python=args.python,
            args=args.args or None,
        )


def build_wheel_armv7l(
    url: str,
    revision: str,
    /,
    python: str | None = None,
    args: list[str] | None = None,
):
    repository = pathlib.PurePosixPath(url).name
    msg = f"Building repository {repository}"
    if python is not None:
        msg += f" for Python {python}"
    print(msg)

    if args is None:
        config_setting_arg = ()
    else:
        config_setting_arg = (
            f"--config-setting=--build-option=build {shlex.join(args)}",
        )

    python_arg = () if python is None else ("--python", python, "--managed-python")
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
            *python_arg,
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
