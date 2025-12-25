from __future__ import annotations

import re
import subprocess
import sys

REMOTE_RE = re.compile(r"(?:https://github\.com/|git@github.com:)(\w+/\w+)(?:.git)?")


def git(args: list[str]):
    return subprocess.check_output(["git", *args], text=True).removesuffix("\n")


def infer_repository() -> str:
    try:
        ref = git(["symbolic-ref", "HEAD"])
        remote = git(["for-each-ref", "--format=%(push:remotename)", "--", ref])
        url = git(["ls-remote", "--get-url", "--", remote])
        if match := REMOTE_RE.fullmatch(url):
            return match.group(1)
    except subprocess.CalledProcessError:
        pass

    print(
        "ERROR: failed to infer upstream repository, please pass in via --repository",
        file=sys.stderr,
    )
    sys.exit(1)


def repository(value: str) -> str:
    if "/" not in value:
        raise ValueError
    return value
