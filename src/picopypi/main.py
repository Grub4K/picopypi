from __future__ import annotations

import argparse
import sys
import types

import picopypi.command.build_armv7l
import picopypi.command.render


def get_doc(module: types.ModuleType):
    doc = module.__doc__
    if not doc:
        return None, None

    lines = doc.splitlines()
    for index, line in enumerate(lines):
        if line:
            return line, "\n".join(lines[index:])

    return None, None


def _main():
    parser = argparse.ArgumentParser(
        prog="picopypi",
        description="PICO PYthon Package Incubator",
        suggest_on_error=True,
    )
    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="action",
        required=True,
        metavar="<subcommand>",
    )

    parsers = {}

    def _add_parser(module: types.ModuleType):
        name = module.__name__.rpartition(".")[2].replace("_", "-")
        help, description = get_doc(module)
        parser = subparsers.add_parser(name, help=help, description=description)
        module.configure_parser(parser)
        parsers[name] = module.run

    _add_parser(picopypi.command.build_armv7l)
    _add_parser(picopypi.command.render)

    args = parser.parse_args()
    parsers[args.action](args)


def main():
    try:
        _main()
    except KeyboardInterrupt:
        print("\nERROR: interrupted by user", file=sys.stderr)
        sys.exit(1)
