from __future__ import annotations

from pydantic import BaseModel

from smurfsniper.analyze import BaseAnalysis
from smurfsniper.models.player import Player
from smurfsniper.models.team import Team
from smurfsniper.utils import human_friendly_duration


class TeamAnalysis(BaseAnalysis, BaseModel):
    team: Team

    @property
    def match_history(self):
        return self.team.match_history

    @classmethod
    def from_team(cls, team: Team) -> "TeamAnalysis":
        return cls(team=team)

    @classmethod
    def from_players(cls, players: list[Player]) -> "TeamAnalysis":
        player_stats = [p.get_player_stats() for p in players]
        ids = sorted(ps.members.character.battlenetId for ps in player_stats)

        found = []
        for ps in player_stats:
            for t in ps.members.character.teams:
                tids = sorted(m.character.battlenetId for m in t.members)
                if tids == ids:
                    found.append(t)

        return cls(team=Team.merge(found))

    @classmethod
    def from_player_names(cls, names: list[str]) -> "TeamAnalysis":
        players = [Player.from_player_name(n) for n in names]
        return cls.from_players(players)

    @property
    def name(self) -> str:
        names = [m.character.name for m in self.team.members]
        if len(names) == 0:
            return ""
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return ", ".join(names[:-1]) + f", and {names[-1]}"

    def summary(self) -> dict:
        team = self.team
        first = self.first_game_played
        last = self.last_game_played

        member_races = []
        for m in team.members:
            rg = m.raceGames or {}
            best = max(rg, key=rg.get) if rg else "unknown"
            member_races.append(
                {
                    "name": m.character.name,
                    "primary_race": best,
                    "protoss": m.protossGamesPlayed,
                    "terran": m.terranGamesPlayed,
                    "zerg": m.zergGamesPlayed,
                    "random": m.randomGamesPlayed,
                    "total_games": (
                        (m.protossGamesPlayed or 0)
                        + (m.terranGamesPlayed or 0)
                        + (m.zergGamesPlayed or 0)
                        + (m.randomGamesPlayed or 0)
                    ),
                }
            )

        return {
            "Team": self.name,
            "Members": [m.character.name for m in team.members],
            "Member Races": member_races,
            "Playing For": (
                f"{human_friendly_duration(first)} ({first})" if first else "unknown"
            ),
            "Most Recent Game": last,
            "Current Rating": team.rating,
            "League": getattr(team.league, "name", str(team.league)),
            "Trend": self.mmr_trend,
            "Wins (1d)": self.wins_last_day,
            "Losses (1d)": self.losses_last_day,
            "Wins (3d)": self.wins_last_3_days,
            "Losses (3d)": self.losses_last_3_days,
            "Wins (7d)": self.wins_last_week,
            "Losses (7d)": self.losses_last_week,
            "Wins (30d)": self.wins_last_month,
            "Losses (30d)": self.losses_last_month,
            "Lifetime Wins": self.wins_lifetime,
            "Lifetime Losses": self.losses_lifetime,
            "Region": team.region,
            "Division ID": team.divisionId,
            "Legacy ID": team.legacyId,
            "Legacy UID": team.legacyUid,
            "Season": team.season,
        }
