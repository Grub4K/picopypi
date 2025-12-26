from __future__ import annotations

import collections.abc
import enum


class Abi(enum.StrEnum):
    CP310 = "cp310"
    CP311 = "cp311"
    CP312 = "cp312"
    CP313 = "cp313"
    CP313T = "cp313t"
    CP314 = "cp314"
    CP314T = "cp314t"

    def parts(self, /):
        minor = self.value[3:]
        special = ""
        if self.value.endswith(("t", "m")):
            special = self.value[-1]
            minor = minor[:-1]
        return self.value[:2], int(self.value[2]), int(minor), special

    def __lt__(self, other, /):
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.parts() < other.parts()

    def __eq__(self, other, /):
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.value == other.value

    def __hash__(self, /):
        return hash(self.value)


class Target(enum.StrEnum):
    MANYLINUX_ARM7 = "manylinux_armv7l"
    MACOS = "macosx_universal2"

    def arch(self, /):
        return {
            self.MANYLINUX_ARM7: "armv7l",
            self.MACOS: "universal2",
        }[self]

    def platform(self, /):
        return {
            self.MANYLINUX_ARM7: "linux",
            self.MACOS: "macos",
        }[self]

    def expand_configuration(self, abis: collections.abc.Iterable[Abi], /):
        for abi in abis:
            yield f"{abi}-{self.value}"


DEFAULT_ABIS = [abi for abi in Abi if not abi.value.endswith(("t", "m"))]
