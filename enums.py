from enum import Enum


class Region(Enum):
    US = "US"
    EU = "EU"
    KR = "KR"
    CN = "CN"


class RaceCode(Enum):
    TERRAN = 1
    PROTOSS = 2
    ZERG = 3
    RANDOM = 4


class TeamFormat(Enum):
    _1V1 = 201
    _2V2 = 202
    _3V3 = 203
    _4V4 = 204
    ARCHON = 206


class TeamType(Enum):
    ARRANGED = 0
    RANDOM = 1
