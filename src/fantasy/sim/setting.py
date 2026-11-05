"""The FantasyCalc league setting (quarterbacks, teams, PPR step) a league maps to."""

import json
from dataclasses import dataclass

PPR_STEPS = (0.0, 0.5, 1.0)  # what the endpoint accepts


@dataclass(frozen=True)
class Setting:
    num_qbs: int
    num_teams: int
    ppr: float

    @property
    def key(self) -> str:
        return f"qb{self.num_qbs}_t{self.num_teams}_ppr{self.ppr:g}"


def setting_for(scoring_json: str, roster_positions: list[str], num_teams: int) -> Setting:
    rec = float(json.loads(scoring_json).get("rec", 0.0))
    ppr = min(PPR_STEPS, key=lambda step: abs(step - rec))
    return Setting(2 if "SUPER_FLEX" in roster_positions else 1, num_teams, ppr)
