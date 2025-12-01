from __future__ import annotations

from datetime import datetime
from typing import Optional

import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout

from pydantic import BaseModel

from sc_match_briefer.models.player import Player, PlayerStats
from sc_match_briefer.enums import League, RaceCode
from sc_match_briefer.overlay_manager import register_overlay, close_all_overlays


class PlayerAnalysis(BaseModel):
    current_race: Optional[str] = None
    player_stats: PlayerStats

    @classmethod
    def from_player_name(cls, str_player_name: str) -> PlayerAnalysis:
        str_player_name = str_player_name.strip()
        return cls.from_player(Player(id=1, name=str_player_name, type="user", result="Undecided", race="Unknown"))

    @classmethod
    def from_player(cls, player: Player) -> "PlayerAnalysis":
        best_match = player.get_best_match()
        stats = PlayerStats.model_validate(best_match)
        return cls(player_stats=stats)

    @classmethod
    def from_player_stats(cls, player_stats: PlayerStats, player: Optional[Player] = None) -> "PlayerAnalysis":
        current_race = "Unknown"
        if player.race is not None:
            current_race = RaceCode.from_alias(player.race).name
        return cls(player_stats=player_stats, current_race=current_race)

    @property
    def name(self) -> str:
        return self.player_stats.members.character.name

    @property
    def max_league(self) -> str:
        return League.from_int(self.player_stats.leagueMax).name

    @property
    def current_mmr(self) -> Optional[int]:
        return (
                self.player_stats.currentStats.rating
                or self.player_stats.previousStats.rating
        )

    @property
    def previous_mmr(self) -> Optional[int]:
        return self.player_stats.previousStats.rating

    @property
    def mmr_trend(self) -> str:
        """
        Computes a real regression slope over the last ~100 MMR samples.
        No numpy required. Uses least squares slope calculation:

            slope = Σ((x - x̄)(y - ȳ)) / Σ((x - x̄)^2)

        Then maps slope to a human-readable trend string.
        """

        hist = self.player_stats.match_history
        if not hist or len(hist.ratings) < 5:
            return "unknown"

        y = hist.ratings[-100:]
        n = len(y)
        x = list(range(n))

        # Means
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        # Numerator & denominator for slope
        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den = sum((xi - mean_x) ** 2 for xi in x)

        if den == 0:
            return "unknown"

        slope = num / den

        if slope > 1.5:
            return "strong rising"
        if slope > 0.4:
            return "rising"
        if slope < -1.5:
            return "strong falling"
        if slope < -0.4:
            return "falling"
        return "flat"

    @property
    def total_games(self) -> int:
        return self.player_stats.totalGamesPlayed

    @property
    def most_played_race(self) -> str:
        races = self.player_stats.members.raceGames
        if not races:
            return "unknown"
        key = max(races, key=lambda r: races.get(r, 0))
        return RaceCode[key].name

    @property
    def smurf_warning(self) -> Optional[str]:
        """
        Pure win-rate–based smurf heuristic.

        Heuristic rules:
          • Last 3 days winrate >= 80% → "Likely Smurf"
          • Last 7 days winrate >= 75% → "Possible Smurf"
          • Lifetime winrate >= 70%    → "Suspiciously strong"
        """

        h = self.player_stats.match_history
        if not h:
            return None

        w3, l3 = h.wins_last_3_days, h.losses_last_3_days
        if (w3 + l3) >= 5:
            winrate3 = w3 / (w3 + l3)
            if winrate3 >= 0.80:
                return "⚠️ Likely Smurf (3d winrate ≥ 80%)"

        w7, l7 = h.wins_last_week, h.losses_last_week
        if (w7 + l7) >= 8:
            winrate7 = w7 / (w7 + l7)
            if winrate7 >= 0.75:
                return "⚠️ Possible Smurf (7d winrate ≥ 75%)"

        wl, ll = h.wins_lifetime, h.losses_lifetime
        if (wl + ll) >= 30:
            winrate_lf = wl / (wl + ll)
            if winrate_lf >= 0.70:
                return "⚠️ Suspiciously strong lifetime winrate"

        return None

    @property
    def wins_last_day(self) -> int:
        return self.player_stats.match_history.wins_last_day

    @property
    def losses_last_day(self) -> int:
        return self.player_stats.match_history.losses_last_day

    @property
    def wins_last_3_days(self) -> int:
        return self.player_stats.match_history.wins_last_3_days

    @property
    def losses_last_3_days(self) -> int:
        return self.player_stats.match_history.losses_last_3_days

    @property
    def wins_last_week(self) -> int:
        return self.player_stats.match_history.wins_last_week

    @property
    def losses_last_week(self) -> int:
        return self.player_stats.match_history.losses_last_week

    @property
    def wins_last_month(self) -> int:
        return self.player_stats.match_history.wins_last_month

    @property
    def losses_last_month(self) -> int:
        return self.player_stats.match_history.losses_last_month

    @property
    def wins_lifetime(self) -> int:
        return self.player_stats.match_history.wins_lifetime

    @property
    def losses_lifetime(self) -> int:
        return self.player_stats.match_history.losses_lifetime

    @property
    def last_played(self) -> Optional[datetime]:
        timestamps = self.player_stats.match_history.timestamps
        if not timestamps:
            return None
        return max(timestamps)

    @property
    def teammates(self) -> dict[str, dict[str, Optional[datetime]]]:
        result = {}
        my_name = self.name
        history = self.player_stats.match_history

        if not history:
            return {}

        for team in self.player_stats.members.character.teams:
            ts = (
                datetime.fromisoformat(team.lastPlayed.replace("Z", ""))
                if team.lastPlayed
                else None
            )
            if not ts:
                continue

            for member in team.members:
                n = member.character.name
                if n == my_name:
                    continue
                entry = result.setdefault(
                    n, {"count": 0, "last_played": None}
                )
                entry["count"] += 1
                if entry["last_played"] is None or ts > entry["last_played"]:
                    entry["last_played"] = ts

        return result

    def summary(self) -> dict:
        partners_readable = {
            name: {
                "last_played": (
                    info["last_played"].isoformat()
                    if isinstance(info.get("last_played"), datetime)
                    else "unknown"
                ),
                "games": info.get("count", 0),
            }
            for name, info in self.teammates.items()
        }

        return {
            "Player": self.name,
            "Max League": self.max_league,
            "Current MMR": self.current_mmr,
            "Trend": self.mmr_trend,
            "Smurf Warning": self.smurf_warning,
            "Current Race": self.current_race,
            "Most Played Race": self.most_played_race,
            "Total Games": self.total_games,
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
            "Last Played": self.last_played.isoformat() if self.last_played else None,
            "Frequent Teammates": partners_readable,
        }

    def pretty_print(self) -> None:
        table = self.summary()
        print("\n=== Player Analysis ===")
        for k, v in table.items():
            print(f"{k:22}: {v}")
        print("========================\n")

    def show_overlay(self, duration_seconds: int = 30):
        summary = self.summary()

        trend_symbol = {
            "strong rising": "▲▲",
            "rising": "▲",
            "falling": "▼",
            "strong falling": "▼▼",
            "flat": "→",
            "unknown": "?"
        }.get(self.mmr_trend, "")

        primary_race = summary["Most Played Race"]
        current_race = summary["Current Race"]

        race_note = ""
        if current_race and primary_race and current_race != primary_race:
            race_note = f" (deviating from {primary_race})"

        smurf_note = self.smurf_warning or ""

        lines = [
            f"Player: {summary['Player']}",
            f"Highest League: {summary['Max League']}",
            f"MMR: {summary['Current MMR']}  {trend_symbol}",
            f"Race: {current_race}{race_note}",
        ]

        if smurf_note:
            lines.append(f"Smurf Check: {smurf_note}")

        lines.extend([
            f"Last Played: {summary['Last Played']}",
            "",
            "Performance:",
            f" 1d   W:{summary['Wins (1d)']}  L:{summary['Losses (1d)']}",
            f" 3d   W:{summary['Wins (3d)']}  L:{summary['Losses (3d)']}",
            f" 7d   W:{summary['Wins (7d)']}  L:{summary['Losses (7d)']}",
            f"30d   W:{summary['Wins (30d)']} L:{summary['Losses (30d)']}",
            f"LFT   W:{summary['Lifetime Wins']} L:{summary['Lifetime Losses']}",
            "",
            "Recent Teammates:",
        ])

        teammate_rows = []
        for name, info in self.teammates.items():
            ts = info.get("last_played")
            ts_str = ts.isoformat() if ts else "unknown"
            teammate_rows.append(f"  {name:<14} {ts_str}")

        text = "\n".join(lines + teammate_rows)

        app = QApplication.instance()
        created = False
        if not app:
            app = QApplication(sys.argv)
            created = True

        overlay = QWidget()
        register_overlay(overlay)
        overlay.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        overlay.setAttribute(Qt.WA_TranslucentBackground)
        overlay.setAttribute(Qt.WA_ShowWithoutActivating)

        layout = QVBoxLayout()
        label = QLabel(text)

        label.setStyleSheet("""
            color: #FFFFFF;
            background-color: rgba(10, 10, 10, 220);
            padding: 16px 22px;
            border-radius: 12px;
            font-family: 'Segoe UI';
            font-size: 14px;
            font-weight: 500;
            line-height: 155%;
            text-shadow: 0 0 6px rgba(0,0,0,0.85);
        """)

        layout.addWidget(label)
        overlay.setLayout(layout)

        screen = app.primaryScreen().geometry()
        overlay.adjustSize()
        overlay.move(screen.width() - overlay.width() - 30, 40)

        overlay.show()

        QTimer.singleShot(duration_seconds * 1000, overlay.close)

        if created:
            app.exec()

class Team2v2Analysis(BaseModel):
    p1: PlayerAnalysis
    p2: PlayerAnalysis

    @property
    def team_name(self) -> str:
        """Combine players as a duo name."""
        return f"{self.p1.name} + {self.p2.name}"

    @property
    def races(self) -> str:
        """Terr + Prot + deviation."""
        r1 = self.p1.current_race or "Unknown"
        r2 = self.p2.current_race or "Unknown"
        return f"{r1} + {r2}"

    @property
    def average_mmr(self) -> Optional[int]:
        mmrs = [self.p1.current_mmr, self.p2.current_mmr]
        mmrs = [m for m in mmrs if m is not None]
        return sum(mmrs) // len(mmrs) if mmrs else None

    @property
    def combined_league(self) -> str:
        """Take strongest league between them."""
        leagues = [self.p1.max_league, self.p2.max_league]
        # approximate league strength ordering
        order = [
            "BRONZE", "SILVER", "GOLD", "PLATINUM",
            "DIAMOND", "MASTER", "GRANDMASTER"
        ]
        ranked = sorted(leagues, key=lambda L: order.index(L))
        return ranked[-1]

    @property
    def p1_winrate_lifetime(self) -> float:
        w = self.p1.wins_lifetime
        l = self.p1.losses_lifetime
        return w / (w + l) if (w + l) > 0 else 0.0

    @property
    def p2_winrate_lifetime(self) -> float:
        w = self.p2.wins_lifetime
        l = self.p2.losses_lifetime
        return w / (w + l) if (w + l) > 0 else 0.0

    @property
    def combined_winrate(self) -> float:
        """Average winrate; simple team indicator."""
        return (self.p1_winrate_lifetime + self.p2_winrate_lifetime) / 2

    @property
    def smurf_warning(self) -> Optional[str]:
        """
        Team-level smurf heuristic:
          • if either player is flagged → show strongest warning
          • if both are suspicious → escalate severity
        """
        s1 = self.p1.smurf_warning
        s2 = self.p2.smurf_warning

        if s1 and s2:
            return f"⚠️⚠️ BOTH players exhibit smurf indicators\n  - {s1}\n  - {s2}"
        if s1:
            return f"⚠️ {self.p1.name}: {s1}"
        if s2:
            return f"⚠️ {self.p2.name}: {s2}"
        return None

    def summary(self) -> dict:
        return {
            "Team": self.team_name,
            "Races": self.races,
            "MMR (Avg)": self.average_mmr,
            "Combined League": self.combined_league,
            "Player 1 Trend": self.p1.mmr_trend,
            "Player 2 Trend": self.p2.mmr_trend,
            "Player 1 Winrate": round(self.p1_winrate_lifetime * 100, 1),
            "Player 2 Winrate": round(self.p2_winrate_lifetime * 100, 1),
            "Combined Winrate": round(self.combined_winrate * 100, 1),
            "Team Smurf Warning": self.smurf_warning,
        }

    def pretty_print(self):
        s = self.summary()
        print("\n=== TEAM ANALYSIS ===")
        for k, v in s.items():
            print(f"{k:22}: {v}")
        print("======================\n")



class Team2V2Analysis:
    def __init__(self, p1: PlayerAnalysis, p2: PlayerAnalysis):
        self.p1 = p1
        self.p2 = p2

    def _build_teammate_table(self, p: PlayerAnalysis) -> str:
        """
        Builds a clean aligned teammate table:
        Name | Last Played | Games
        """
        rows = []
        for name, info in p.teammates.items():
            ts = info.get("last_played")
            ts_str = ts.isoformat() if isinstance(ts, datetime) else "unknown"
            games = info.get("count", 0)

            rows.append(f"{name:<14}  {ts_str:<22}  {games:>2}g")

        if not rows:
            return "  (no teammate history)"

        return "\n".join("  " + r for r in rows)

    def _build_player_block(self, p: PlayerAnalysis) -> str:
        """
        Formats a compact block of text for one player.
        """
        s = p.summary()

        trend_symbol = {
            "strong rising": "▲▲",
            "rising": "▲",
            "falling": "▼",
            "strong falling": "▼▼",
            "flat": "→",
            "unknown": "?",
        }.get(p.mmr_trend, "")

        race_note = ""
        if s["Current Race"] != s["Most Played Race"]:
            race_note = f" (→ {s['Most Played Race']})"

        smurf_note = p.smurf_warning or ""

        block = [
            f"{s['Player']}",
            f"MMR: {s['Current MMR']}  {trend_symbol}",
            f"Race: {s['Current Race']}{race_note}",
        ]

        if smurf_note:
            block.append(f"⚠ {smurf_note}")

        block.extend([
            "",
            "Perf:",
            f"1d  {s['Wins (1d)']}W/{s['Losses (1d)']}L",
            f"3d  {s['Wins (3d)']}W/{s['Losses (3d)']}L",
            f"7d  {s['Wins (7d)']}W/{s['Losses (7d)']}L",
            f"30d {s['Wins (30d)']}W/{s['Losses (30d)']}L",
            f"LFT {s['Lifetime Wins']}W/{s['Lifetime Losses']}L",
        ])

        return "\n".join(block)

    def show_overlay(self, duration_seconds: int = 40):
        """
        Displays a modern team HUD (right side) for 2v2,
        including recent teammate tables for each player.
        """

        # Build player blocks
        left_text = self._build_player_block(self.p1)
        right_text = self._build_player_block(self.p2)

        # Build teammates sub-tables
        left_teammates = self._build_teammate_table(self.p1)
        right_teammates = self._build_teammate_table(self.p2)

        # Combine final blocks
        left_full = left_text + "\n\nTeammates:\n" + left_teammates
        right_full = right_text + "\n\nTeammates:\n" + right_teammates

        app = QApplication.instance()
        created = False
        if not app:
            app = QApplication(sys.argv)
            created = True

        overlay = QWidget()
        register_overlay(overlay)
        overlay.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        overlay.setAttribute(Qt.WA_TranslucentBackground)
        overlay.setAttribute(Qt.WA_ShowWithoutActivating)

        # ------------ Layout (Vertical Stack) ------------
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        style = """
            color: #FFFFFF;
            background-color: rgba(15, 15, 15, 215);
            padding: 16px;
            border-radius: 12px;
            font-family: 'Segoe UI';
            font-size: 14px;
            font-weight: 500;
            line-height: 160%;
            min-width: 260px;
        """

        left_label = QLabel(left_full)
        left_label.setStyleSheet(style)

        right_label = QLabel(right_full)
        right_label.setStyleSheet(style)

        main_layout.addWidget(left_label)
        main_layout.addWidget(right_label)

        overlay.setLayout(main_layout)

        # ------------ Position HUD ON THE RIGHT SIDE ------------
        screen = app.primaryScreen().geometry()
        overlay.adjustSize()
        overlay.move(
            screen.width() - overlay.width() - 40,  # right-aligned
            40  # slight top margin
        )

        overlay.show()

        QTimer.singleShot(duration_seconds * 1000, overlay.close)

        if created:
            app.exec()

