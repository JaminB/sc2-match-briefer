from datetime import datetime, timedelta
from typing import List, Optional, Dict
from pydantic import BaseModel
import httpx

from shared import PreviousStats, CurrentStats
from character import Character
from enums import Region, TeamFormat, TeamType
from utils import create_team_legacy_uid


class Members(BaseModel):
    protossGamesPlayed: Optional[int] = 0
    terranGamesPlayed: Optional[int] = 0
    zergGamesPlayed: Optional[int] = 0
    randomGamesPlayed: Optional[int] = 0

    character: Character
    account: Dict
    clan: Optional[Dict] = None
    raceGames: Dict[str, int]


class SC2CharacterResult(BaseModel):
    leagueMax: int
    ratingMax: int
    totalGamesPlayed: int

    previousStats: PreviousStats
    currentStats: CurrentStats
    members: Members

    def legacy_uid(
        self,
        queue_type: TeamFormat,
        team_type: TeamType = TeamType.ARRANGED,
    ) -> str:
        region_enum = Region[self.members.character.region]
        return create_team_legacy_uid(
            queue_type=queue_type,
            team_type=team_type,
            region=region_enum,
            members=[self.members],
        )


class Player(BaseModel):
    id: int
    name: str
    type: str
    race: str
    result: str

    def matches(self) -> List[SC2CharacterResult]:
        url = f"https://sc2pulse.nephest.com/sc2/api/characters?query={self.name}"

        with httpx.Client(timeout=10.0) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()

        return [SC2CharacterResult.model_validate(entry) for entry in data]

    def get_best_match(self) -> SC2CharacterResult:
        candidates = self.matches()
        best = candidates[0]
        newest = datetime.min

        for match in candidates:
            for team in match.members.character.teams():
                if team.lastPlayed:
                    dt = datetime.fromisoformat(team.lastPlayed.replace("Z", ""))
                    if dt > newest:
                        best = match
                        newest = dt

        return best


