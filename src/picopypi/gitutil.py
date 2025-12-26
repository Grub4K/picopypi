from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys

REMOTE_RE = re.compile(r"(?:https://github\.com/|git@github.com:)(\w+/\w+)(?:.git)?")
ALLOWED_DIGEST_LENGTHS = (hashlib.sha1().digest_size, hashlib.sha256().digest_size)
ALLOWED_DIGEST_RE = re.compile(
    "|".join(rf"[0-9a-fA-F]{{{length * 2}}}" for length in ALLOWED_DIGEST_LENGTHS)
)


def repository(value: str):
    if "/" not in value:
        msg = f"Invalid repository: {value!r}"
        raise ValueError(msg)
    if ":" not in value:
        value = f"https://github.com/{value}"
    return value


def revision(value: str):
    if not ALLOWED_DIGEST_RE.fullmatch(value):
        msg = f"Invalid digest: {value!r}"
        raise ValueError(msg)
    return value


def infer_repository() -> str:
    try:
        ref = _git(["symbolic-ref", "HEAD"])
        remote = _git(["for-each-ref", "--format=%(push:remotename)", "--", ref])
        url = _git(["ls-remote", "--get-url", "--", remote])
        if match := REMOTE_RE.fullmatch(url):
            return match.group(1)
    except subprocess.CalledProcessError:
        pass

    print(
        "ERROR: failed to infer upstream repository, please pass in via --repository",
        file=sys.stderr,
    )
    sys.exit(1)


def checkout(path: pathlib.Path, revision: str):
    subprocess.check_call(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "advice.detachedHead=false",
            "checkout",
            revision,
        ]
    )


def clone_or_fetch(path: pathlib.Path, url: str):
    repository = pathlib.PurePosixPath(url).stem

    git_dir = path / repository
    if not git_dir.is_dir():
        subprocess.check_call(["git", "-C", str(path), "clone", url])
    else:
        subprocess.check_call(["git", "-C", str(git_dir), "fetch"])

    return git_dir


def create_ignored_folder(path: pathlib.Path):
    path.mkdir(parents=True, exist_ok=True)
    ignore_path = path / ".gitignore"
    if ignore_path.exists():
        return
    ignore_path.write_bytes(b"*\n")


def _git(args: list[str]):
    return subprocess.check_output(["git", *args], text=True).removesuffix("\n")
