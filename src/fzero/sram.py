# This file is part of F-Zero Editor, see <https://github.com/MestreLion/fzero>
# Copyright (C) 2023 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
# License: GPLv3 or later, at your choice. See <http://www.gnu.org/licenses/gpl>
"""
SRAM Parser and Writer

Data reference: https://datacrystal.romhacking.net/wiki/F-Zero:SRAM_map
"""

from __future__ import annotations

import logging
import typing as t

from . import util as u

log: logging.Logger = logging.getLogger(__name__)

# Constants ------------------------------------------------------------------
SRAM_SIZE: int = 2048
SIGNATURE: bytes = b"FZERO"  # Header and Footer
LEAGUES: int = 3
TRACKS: int = 5  # Per league
RECORDS: int = 11  # Per track, 10 best races + 1 best lap
RECORD_SIZE: int = 3  # mode+car+minutes, seconds, centiseconds
CHECKSUM_SIZE: int = 2
UNLOCKS_SIZE: int = 1  # Leagues' Master difficulty unlock status
LEAGUE_INFO: t.Dict[str, t.Tuple[str, str, str, str, str]] = {
    "Knight": (
        "Mute City I",
        "Big Blue",
        "Sand Ocean",
        "Death Wind I",
        "Silence",
    ),
    "Queen": (
        "Mute City II",
        "Port Town I",
        "Red Canyon I",
        "White Land I",
        "White Land II",
    ),
    "King": (
        "Mute City III",
        "Death Wind II",
        "Port Town II",
        "Red Canyon II",
        "Fire Field",
    )
}
assert len(LEAGUE_INFO) == LEAGUES
assert ((_ := set(len(_) for _ in LEAGUE_INFO.values())).pop() == TRACKS and not _)

# Derived constants ----------------------------------------------------------
# Data size can be derived from above:
# 5 header
# 3 leagues * ((5 tracks * 11 records * 3 bytes) + 2 checksum)
# 1 master unlocks
# 5 footer
DATA_SIZE: int = 512


class Mode(u.Enum):
    GRAND_PRIX = 0
    PRACTICE   = 1

    def pretty(self) -> str:
        # for "type: ignore", see https://github.com/python/mypy/issues/10910
        return "*" if self is self.PRACTICE else " "  # type: ignore

    def __str__(self) -> str:
        return super().__str__()[0]


class Car(u.Enum):
    BLUE_FALCON   = 0
    WILD_GOOSE    = 1
    GOLDEN_FOX    = 2
    FIRE_STINGRAY = 3


class Record:
    def __init__(
            self,
            minutes: int  = 9,
            seconds: int  = 59,
            cents:   int  = 99,
            car:     Car  = Car.BLUE_FALCON,
            mode:    Mode = Mode.GRAND_PRIX,
            display: bool = False,
    ):
        self.minutes = minutes
        self.seconds = seconds
        self.cents = cents
        self.car = car
        self.mode = mode
        self.display = display

    @classmethod
    def from_data(cls, data: bytes) -> Record:
        record = tuple(unpack(data, 8, 8, 4, 2, 1, 1))
        return cls(
            cents   = record[0],
            seconds = record[1],
            minutes = record[2],
            car     = Car(record[3]),
            mode    = Mode(record[4]),
            display = bool(record[5]),
        )

    # Could also be __bytes__
    def to_data(self) -> bytes:
        return pack(
            (self.cents,   8),
            (self.seconds, 8),
            (self.minutes, 4),
            (self.car,     2),
            (self.mode,    1),
            (self.display, 1),
        )

    @property
    def time(self) -> Time:
        return Time(self.minutes, self.seconds, self.cents)

    def pretty(self) -> str:
        if not self.display:
            return "-"
        return f"{self.time.pretty()} {self.mode.pretty()} {self.car.pretty()}"

    def __str__(self) -> str:
        text = f"{self.time} {self.mode} {self.car}"
        if not self.display:
            text = f"* {text}"
        return text

    def __repr__(self) -> str:
        return "<{}({})>".format(self.__class__.__name__, vars(self))


class Time(t.NamedTuple):
    minutes: int = 9
    seconds: int = 59
    cents:   int = 99

    def pretty(self) -> str:
        # noinspection GrazieInspection
        return "{0.minutes}’{0.seconds:02}”{0.cents:02}".format(self)

    def __repr__(self) -> str:
        return "{0.minutes:0}:{0.seconds:02}.{0.cents:02}".format(self)

    def __int__(self) -> int:
        return 100 * (60 * self.minutes + self.seconds) + self.cents


class League:
    def __init__(self, records: t.Iterable[Record] = (), name: str = ""):
        self.records: t.List[Record] = list(records)
        self.name = name

    @classmethod
    def from_data(cls, data: bytes, name: str = "", raise_on_checksum: bool = False) -> League:
        self = cls(name=name)
        offset = 0
        for i in range(TRACKS):
            for r in range(RECORDS):
                record = Record.from_data(u.sliced(data, offset, RECORD_SIZE))
                log.debug("%04X: Track %02s, record %02s: [%s] %r",
                          offset, i, r, record.to_data().hex(":"), record)
                self.records.append(record)
                offset += RECORD_SIZE

        checksum = Checksum.parse(u.sliced(data, offset, CHECKSUM_SIZE))
        expected = Checksum.from_data(u.sliced(data, 0, offset))
        if checksum == expected:
            log.debug("League checksum OK [%s]", checksum)
        else:
            args = "League checksum FAIL: %s, expected %s", checksum, expected
            if raise_on_checksum:
                raise u.BadData(*args)
            else:
                log.warning(*args)
        return self

    def to_data(self) -> bytes:
        data = b''.join(_.to_data() for _ in self.records)
        return data + Checksum.from_data(data).to_data()

    @property
    def checksum(self) -> bytes:
        return self.to_data()[-CHECKSUM_SIZE:]

    @property
    def tracks(self):
        return LEAGUE_INFO.get(self.name) or tuple(f"Track {_ + 1}" for _ in range(TRACKS))

    def pretty(self, level: int = 0, show_hidden: bool = False) -> str:
        msg = ""
        indent = level * "\t"
        tracks = self.tracks
        for track, records in enumerate(u.chunked(self.records, RECORDS)):
            msg += f"{indent}{tracks[track]}\n"
            for r, record in enumerate(records, 1):
                if record.display or show_hidden:
                    msg += f"{indent}\t{r:2}: {record.pretty()}\n"
        return msg


class Checksum(int):
    @classmethod
    def parse(cls, checksum: bytes) -> Checksum:
        return cls.from_bytes(checksum, 'little')

    @classmethod
    def from_data(cls, data: bytes) -> Checksum:
        return cls(sum(data))

    def to_data(self) -> bytes:
        return self.to_bytes(CHECKSUM_SIZE, 'little')

    def __str__(self) -> str:
        return self.to_data().hex().upper()


def unpack(data: t.Union[bytes, int], *bit_lengths: int) -> t.Iterable[int]:
    num: int = int.from_bytes(data, 'big') if isinstance(data, bytes) else data
    for bits in bit_lengths:
        yield int("{:x}".format(num & ((1 << bits) - 1)))
        num >>= bits


def pack(*values: t.Tuple[t.SupportsInt, int]) -> bytes:
    num = shift = 0
    for value, bits in values:
        num += (int(str(int(value)), 16) & ((1 << bits) - 1)) << shift
        shift += bits
    return num.to_bytes((shift + 7) // 8, 'big')


def parse(fd: t.BinaryIO) -> None:
    log.info("Header (%s): %s", SIGNATURE, fd.read(len(SIGNATURE)))

    for league in LEAGUE_INFO:
        log.info("%s League:", league)
        data = fd.read(TRACKS * RECORDS * RECORD_SIZE + CHECKSUM_SIZE)
        log.info(League.from_data(data, league, raise_on_checksum=False).pretty(level=1))

    data = fd.read(1)
    flags, checksum = unpack(data, 4, 4)
    if not flags == checksum:
        log.warning("Invalid Master Unlocks value: %s", data.hex())
    unlocks = (list(LEAGUE_INFO)[i] for i, v in enumerate(unpack(data, 1, 1, 1)) if v)
    log.info("Master Unlocks: %s [%s]", ", ".join(unlocks), data.hex())
    log.info("Footer (%s): %s", SIGNATURE, fd.read(len(SIGNATURE)))
