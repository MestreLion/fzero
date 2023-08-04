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
    def tracks(self) -> t.Tuple[str, ...]:
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


class Save:
    SIGNATURE_SIZE: int = len(SIGNATURE)
    LEAGUE_SIZE: int = RECORD_SIZE * RECORDS * TRACKS + CHECKSUM_SIZE
    DATA_SIZE: int = LEAGUE_SIZE * LEAGUES + 2 * SIGNATURE_SIZE + UNLOCKS_SIZE
    assert DATA_SIZE == 512

    def __init__(
        self,
        leagues: t.Iterable[League] = (),
        unlocks: t.Iterable[bool] = (),
    ):
        self.leagues: t.List[League] = list(leagues)[:LEAGUES]
        self.unlocks: t.List[bool]   = list(unlocks)[:LEAGUES]

    @classmethod
    def from_sram(cls, path: u.PathLike) -> Save:
        with u.openstd(path, 'rb') as fd:
            log.debug("Reading from %s", fd.name)
            data = fd.read(cls.DATA_SIZE)
        return cls.from_data(data)

    @classmethod
    def from_data(cls, data: bytes) -> Save:
        self = cls()
        cls._check_signature(data, 0, "Header")
        offset = cls.SIGNATURE_SIZE
        for i, league in enumerate(LEAGUE_INFO):
            log.debug("Parsing %s League", league)
            self.leagues.append(League.from_data(data=u.sliced(data, offset, cls.LEAGUE_SIZE),
                                                 name=league))
            offset += cls.LEAGUE_SIZE
        self.unlocks = cls._parse_unlocks(u.sliced(data, offset, UNLOCKS_SIZE))
        cls._check_signature(data, offset + UNLOCKS_SIZE, "Footer")
        return self

    @classmethod
    def _check_signature(cls, data: bytes, offset: int, label: str) -> bool:
        signature = u.sliced(data, offset, cls.SIGNATURE_SIZE)
        check = signature == SIGNATURE
        if check:
            log.debug("%s signature at 0x%04X OK!", label, offset)
        else:
            log.warning("%s signature mismatch at 0x%04X: %s, expected %s",
                        label, offset, signature, SIGNATURE)
        return check

    @classmethod
    def _parse_unlocks(cls, data: bytes) -> t.List[bool]:
        bits = UNLOCKS_SIZE * 8
        unlocks, mirror = u.chunked(list(unpack(data, *(bits * [1]))), bits // 2)
        if unlocks == mirror and set(unlocks[LEAGUES:]) == {0}:
            log.debug("Master Unlocks OK! [%s], %s", data.hex().upper(), unlocks)
        else:
            log.warning("Invalid Master Unlocks data: [%s]", data.hex().upper())
            unlocks = []
        return [bool(_) for _ in unlocks][:LEAGUES]

    def to_data(self) -> bytes:
        data = (
            SIGNATURE +
            b''.join(_.to_data() for _ in self.leagues) +
            self._pack_unlocks() +
            SIGNATURE
        )
        return data + b'\0' * (SRAM_SIZE - len(data))

    def _pack_unlocks(self) -> bytes:
        bits = UNLOCKS_SIZE * 8 // 2
        unlocks = 2 * (self.unlocks + (bits - len(self.unlocks)) * [False])[:bits]
        return pack(*zip(unlocks, len(unlocks) * [1]))

    def pretty(self) -> str:
        msg = ""
        for league in self.leagues:
            msg += f"{league.name} League\n{league.pretty(level=1)}\n"
        unlocks = ", ".join(list(LEAGUE_INFO)[i] for i, v in enumerate(self.unlocks) if v)
        return msg + f"Master difficulty unlocked for leagues: {unlocks}"


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
