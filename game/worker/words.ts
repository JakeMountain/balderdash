import data from "../../data/words.json";
import type { Pos, Spice } from "../shared/protocol";

export interface Word {
  word: string;
  pos: Pos;
  definition: string;
  dealer_note: string | null;
  category: string | null;
  spice: Spice;
  decoys: string[];
}

export const WORDS: Word[] = (data as { words: Word[] }).words.filter((w) => w.definition);
export const CATEGORIES: string[] = [...new Set(WORDS.map((w) => w.category).filter((c): c is string => !!c))].sort();

const SPICE_RANK: Record<Spice, number> = { mild: 0, cheeky: 1, spicy: 2 };

// Indexes of words allowed by the room's settings.
export function eligible(maxSpice: Spice, categories: string[]): number[] {
  const out: number[] = [];
  WORDS.forEach((w, i) => {
    if (SPICE_RANK[w.spice] > SPICE_RANK[maxSpice]) return;
    if (categories.length && !(w.category && categories.includes(w.category))) return;
    out.push(i);
  });
  return out;
}
