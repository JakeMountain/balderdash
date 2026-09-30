// Messages between the phone client and the room's Durable Object. The server sends each player a
// full view after every change; the view is redacted per player (no one sees fakes' authors or the
// real definition before the reveal).

export type Phase = "lobby" | "writing" | "voting" | "reveal" | "scores" | "final";
export type Spice = "mild" | "cheeky" | "spicy";
export type Pos = "noun" | "verb" | "adjective" | "adverb" | "interjection";

export interface Settings {
  rounds: number;
  spice: Spice; // highest tier allowed: mild = mild only, cheeky = mild + cheeky, spicy = everything
  categories: string[]; // empty = all
  writeSecs: number;
  voteSecs: number;
}

export interface PlayerView {
  id: string;
  name: string;
  score: number;
  connected: boolean;
  host: boolean;
  done: boolean; // submitted (writing) or voted (voting)
}

export interface OptionView {
  id: string;
  text: string;
  mine: boolean;
  // Filled in at reveal:
  kind?: "real" | "fake" | "decoy";
  author?: string; // player name for fakes
  voters?: string[];
  laughs?: number;
  laughedByMe?: boolean;
}

export interface RoundResult {
  name: string;
  gained: number;
  why: string[];
}

export interface View {
  code: string;
  you: string; // your player id
  phase: Phase;
  players: PlayerView[];
  settings: Settings;
  categories: string[]; // every category in the word list, for the settings screen
  round: number;
  deadline: number | null; // epoch ms
  word?: { word: string; pos: Pos };
  myFake?: string;
  options?: OptionView[];
  myVote?: string;
  dealerNote?: string | null;
  results?: RoundResult[];
  error?: string;
}

export type ClientMsg =
  | { t: "settings"; settings: Partial<Settings> }
  | { t: "start" }
  | { t: "knowIt" }
  | { t: "fake"; text: string }
  | { t: "vote"; option: string }
  | { t: "laugh"; option: string }
  | { t: "next" } // host: reveal -> scores -> next round
  | { t: "kick"; player: string }
  | { t: "again" }; // host: back to lobby after final scores

export type ServerMsg = { t: "view"; view: View } | { t: "error"; message: string };
