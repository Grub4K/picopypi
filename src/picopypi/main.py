import argparse

import picopypi.command.build_armv7l
import picopypi.command.render


def main():
    parser = argparse.ArgumentParser(
        prog=__name__.partition(".")[0],
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    parsers = {}

    def _add_parser(module):
        name = module.__name__.rpartition(".")[2].replace("_", "-")
        parser = subparsers.add_parser(name)
        module.configure_parser(parser)
        parsers[name] = module.run

    _add_parser(picopypi.command.build_armv7l)
    _add_parser(picopypi.command.render)

    args = parser.parse_args()
    parsers[args.action](args)
