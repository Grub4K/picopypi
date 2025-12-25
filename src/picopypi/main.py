from __future__ import annotations

import argparse
import types

import picopypi.command.build_armv7l
import picopypi.command.render


def get_simple_doc(module: types.ModuleType):
    doc = module.__doc__
    if not doc:
        return None

    return next(line for line in doc.splitlines() if line)


def main():
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
        parser = subparsers.add_parser(name, help=get_simple_doc(module))
        module.configure_parser(parser)
        parsers[name] = module.run

    _add_parser(picopypi.command.build_armv7l)
    _add_parser(picopypi.command.render)

    args = parser.parse_args()
    parsers[args.action](args)
