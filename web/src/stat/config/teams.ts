/**
 * The 32 teams as the play-by-play data names them (`posteam` / `defteam`), the same in every
 * season the data has (2021 on). `nickname` is what people say ("Chiefs").
 */
export interface Team {
  id: string;
  name: string;
  nickname: string;
}

export const TEAMS: readonly Team[] = [
  { id: "ARI", name: "Arizona Cardinals", nickname: "Cardinals" },
  { id: "ATL", name: "Atlanta Falcons", nickname: "Falcons" },
  { id: "BAL", name: "Baltimore Ravens", nickname: "Ravens" },
  { id: "BUF", name: "Buffalo Bills", nickname: "Bills" },
  { id: "CAR", name: "Carolina Panthers", nickname: "Panthers" },
  { id: "CHI", name: "Chicago Bears", nickname: "Bears" },
  { id: "CIN", name: "Cincinnati Bengals", nickname: "Bengals" },
  { id: "CLE", name: "Cleveland Browns", nickname: "Browns" },
  { id: "DAL", name: "Dallas Cowboys", nickname: "Cowboys" },
  { id: "DEN", name: "Denver Broncos", nickname: "Broncos" },
  { id: "DET", name: "Detroit Lions", nickname: "Lions" },
  { id: "GB", name: "Green Bay Packers", nickname: "Packers" },
  { id: "HOU", name: "Houston Texans", nickname: "Texans" },
  { id: "IND", name: "Indianapolis Colts", nickname: "Colts" },
  { id: "JAX", name: "Jacksonville Jaguars", nickname: "Jaguars" },
  { id: "KC", name: "Kansas City Chiefs", nickname: "Chiefs" },
  { id: "LA", name: "Los Angeles Rams", nickname: "Rams" },
  { id: "LAC", name: "Los Angeles Chargers", nickname: "Chargers" },
  { id: "LV", name: "Las Vegas Raiders", nickname: "Raiders" },
  { id: "MIA", name: "Miami Dolphins", nickname: "Dolphins" },
  { id: "MIN", name: "Minnesota Vikings", nickname: "Vikings" },
  { id: "NE", name: "New England Patriots", nickname: "Patriots" },
  { id: "NO", name: "New Orleans Saints", nickname: "Saints" },
  { id: "NYG", name: "New York Giants", nickname: "Giants" },
  { id: "NYJ", name: "New York Jets", nickname: "Jets" },
  { id: "PHI", name: "Philadelphia Eagles", nickname: "Eagles" },
  { id: "PIT", name: "Pittsburgh Steelers", nickname: "Steelers" },
  { id: "SEA", name: "Seattle Seahawks", nickname: "Seahawks" },
  { id: "SF", name: "San Francisco 49ers", nickname: "49ers" },
  { id: "TB", name: "Tampa Bay Buccaneers", nickname: "Buccaneers" },
  { id: "TEN", name: "Tennessee Titans", nickname: "Titans" },
  { id: "WAS", name: "Washington Commanders", nickname: "Commanders" },
];

const BY_ID = new Map(TEAMS.map((t) => [t.id, t]));

export const getTeamById = (id: string): Team | undefined => BY_ID.get(id);
