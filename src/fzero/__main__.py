# This file is part of F-Zero Editor, see <https://github.com/MestreLion/fzero>
# Copyright (C) 2023 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
# License: GPLv3 or later, at your choice. See <http://www.gnu.org/licenses/gpl>
"""
F-Zero SRAM Save Editor
"""
import logging
import sys
import typing as t

from . import sram
from . import util as u

__version__ = "0.2023.8"

log: logging.Logger = logging.getLogger(__package__)


def cli(argv: t.Optional[t.List[str]] = None) -> None:
    """Command-line argument handling and logging setup"""
    parser = u.ArgumentParser(description=__doc__, version=__version__)
    parser.add_argument(
        nargs="?",
        type=u.ArgumentParser.FileType("rb"),
        default="-",
        dest="file",
        metavar="FILE",
        help="File to export to or import from. [Default: stdout / stdin]"
    )
    args = parser.parse_args(argv)
    u.setup_logging(level=args.loglevel)
    log.debug(args)

#    with u.openstd(args.file, 'rb') as (fd, name):
#        log.debug("Reading from %s", name)
#        sram.parse(fd)

    log.debug("Reading from %s", args.file.name)
    sram.parse(args.file)


def run(argv: t.Optional[t.List[str]] = None) -> None:
    """CLI entry point, handling exceptions from cli() and setting exit code"""
    try:
        cli(argv)
    except u.FZeroError as err:
        log.critical(err)
        sys.exit(1)
    except Exception as err:
        log.exception(err)
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Aborting")
        sys.exit(2)  # signal.SIGINT.value, but not actually killed by SIGINT


run()
