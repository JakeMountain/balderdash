import { DurableObject } from "cloudflare:workers";
import { sameText, tidy } from "../shared/format";
import type { ClientMsg, OptionView, Phase, RoundResult, ServerMsg, Settings, View } from "../shared/protocol";
import type { Env } from "./index";
import { CATEGORIES, WORDS, eligible } from "./words";

const MAX_PLAYERS = 12;
const DECOYS_UNDER = 5; // AI decoys only join the ballot with fewer players than this
const ROOM_TTL_MS = 24 * 3600 * 1000;

interface Player {
  id: string;
  name: string;
  score: number;
  host: boolean;
}

interface Option {
  id: string;
  text: string;
  kind: "real" | "fake" | "decoy";
  author?: string; // player id, for fakes
}

interface State {
  code: string;
  created: number;
  phase: Phase;
  players: Player[];
  settings: Settings;
  round: number;
  deadline: number | null;
  word: number | null; // index into WORDS
  used: number[];
  fakes: Record<string, string>;
  options: Option[];
  votes: Record<string, string>; // player id -> option id
  laughs: Record<string, string[]>; // option id -> player ids
  results: RoundResult[] | null;
}

const DEFAULT_SETTINGS: Settings = { rounds: 5, spice: "cheeky", categories: [], writeSecs: 90, voteSecs: 60 };

function shuffle<T>(xs: T[]): T[] {
  const a = [...xs];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const rid = () => crypto.randomUUID().slice(0, 8);

export class Room extends DurableObject<Env> {
  s: State | null = null;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      this.s = (await ctx.storage.get<State>("s")) ?? null;
    });
  }

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/create") {
      const { code } = (await req.json()) as { code: string };
      if (this.s && Date.now() - this.s.created < ROOM_TTL_MS) return new Response("taken", { status: 409 });
      await this.ctx.storage.deleteAll();
      this.s = {
        code, created: Date.now(), phase: "lobby", players: [], settings: { ...DEFAULT_SETTINGS }, round: 0,
        deadline: null, word: null, used: [], fakes: {}, options: [], votes: {}, laughs: {}, results: null,
      };
      await this.save();
      return new Response("ok");
    }
    if (req.headers.get("Upgrade") !== "websocket") return new Response("expected websocket", { status: 426 });
    const name = (url.searchParams.get("name") ?? "").replace(/\s+/g, " ").trim().slice(0, 20);
    const [client, server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server);
    const fail = (message: string) => {
      server.send(JSON.stringify({ t: "error", message } satisfies ServerMsg));
      server.close(4000, message);
      return new Response(null, { status: 101, webSocket: client });
    };
    const s = this.s;
    if (!s || Date.now() - s.created > ROOM_TTL_MS) return fail("No room with that code.");
    if (!name) return fail("Pick a name first.");
    let p = s.players.find((x) => x.name.toLowerCase() === name.toLowerCase());
    if (!p) {
      if (s.players.length >= MAX_PLAYERS) return fail("Room is full.");
      p = { id: rid(), name, score: 0, host: s.players.length === 0 };
      s.players.push(p);
    } else {
      // Rejoin by name: the newest phone takes the seat.
      for (const ws of this.ctx.getWebSockets()) {
        if (ws !== server && this.pidOf(ws) === p.id) ws.close(4001, "Joined from another device.");
      }
    }
    server.serializeAttachment({ pid: p.id });
    await this.save();
    this.broadcast();
    return new Response(null, { status: 101, webSocket: client });
  }

  pidOf(ws: WebSocket): string | undefined {
    return (ws.deserializeAttachment() as { pid?: string } | null)?.pid;
  }

  connectedIds(): Set<string> {
    const ids = new Set<string>();
    for (const ws of this.ctx.getWebSockets()) {
      const pid = this.pidOf(ws);
      if (pid && ws.readyState === WebSocket.OPEN) ids.add(pid);
    }
    return ids;
  }

  async webSocketMessage(ws: WebSocket, raw: string | ArrayBuffer) {
    const s = this.s;
    const pid = this.pidOf(ws);
    if (!s || !pid || typeof raw !== "string") return;
    const me = s.players.find((p) => p.id === pid);
    if (!me) return;
    let msg: ClientMsg;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    const err = (message: string) => ws.send(JSON.stringify({ t: "error", message } satisfies ServerMsg));

    switch (msg.t) {
      case "settings": {
        if (!me.host || s.phase !== "lobby") return;
        const n = msg.settings;
        const clamp = (v: unknown, lo: number, hi: number, d: number) =>
          typeof v === "number" && Number.isFinite(v) ? Math.min(hi, Math.max(lo, Math.round(v))) : d;
        s.settings = {
          rounds: clamp(n.rounds, 1, 30, s.settings.rounds),
          spice: n.spice && ["mild", "cheeky", "spicy"].includes(n.spice) ? n.spice : s.settings.spice,
          categories: Array.isArray(n.categories) ? n.categories.filter((c) => CATEGORIES.includes(c)) : s.settings.categories,
          writeSecs: clamp(n.writeSecs, 20, 300, s.settings.writeSecs),
          voteSecs: clamp(n.voteSecs, 15, 180, s.settings.voteSecs),
        };
        break;
      }
      case "start":
        if (!me.host || s.phase !== "lobby") return;
        if (s.players.length < 2) return err("Need at least 2 players.");
        if (!eligible(s.settings.spice, s.settings.categories).length) return err("No words match those settings.");
        for (const p of s.players) p.score = 0;
        s.round = 1;
        this.startWriting();
        break;
      case "knowIt":
        if (s.phase !== "writing") return;
        this.startWriting(); // same round, new word; fakes so far are thrown away
        break;
      case "fake": {
        if (s.phase !== "writing") return;
        const text = tidy(String(msg.text ?? ""));
        if (!text) return;
        s.fakes[pid] = text;
        this.maybeAdvance();
        break;
      }
      case "vote": {
        if (s.phase !== "voting") return;
        const opt = s.options.find((o) => o.id === msg.option);
        if (!opt || opt.author === pid) return;
        s.votes[pid] = opt.id;
        this.maybeAdvance();
        break;
      }
      case "laugh": {
        if (s.phase !== "reveal") return;
        const opt = s.options.find((o) => o.id === msg.option);
        if (!opt || opt.author === pid) return;
        const who = (s.laughs[opt.id] ??= []);
        const i = who.indexOf(pid);
        if (i >= 0) who.splice(i, 1);
        else who.push(pid);
        break;
      }
      case "next":
        if (!me.host) return;
        if (s.phase === "writing" || s.phase === "voting") this.advance(); // host can cut a timer short
        else if (s.phase === "reveal") this.score();
        else if (s.phase === "scores") {
          if (s.round >= s.settings.rounds) {
            s.phase = "final";
            s.deadline = null;
          } else {
            s.round++;
            this.startWriting();
          }
        }
        break;
      case "kick": {
        if (!me.host || msg.player === pid) return;
        s.players = s.players.filter((p) => p.id !== msg.player);
        for (const w of this.ctx.getWebSockets()) if (this.pidOf(w) === msg.player) w.close(4002, "Removed by the host.");
        this.maybeAdvance();
        break;
      }
      case "again":
        if (!me.host || s.phase !== "final") return;
        s.phase = "lobby";
        s.round = 0;
        s.results = null;
        break;
      default:
        return;
    }
    await this.save();
    this.broadcast();
  }

  async webSocketClose(ws: WebSocket) {
    ws.close();
    if (!this.s) return;
    this.maybeAdvance(); // a dropped phone shouldn't hold up everyone else
    await this.save();
    this.broadcast();
  }

  async webSocketError(ws: WebSocket) {
    await this.webSocketClose(ws);
  }

  async alarm() {
    const s = this.s;
    if (!s || s.deadline === null) return;
    if (Date.now() < s.deadline) {
      await this.ctx.storage.setAlarm(s.deadline);
      return;
    }
    this.advance();
    await this.save();
    this.broadcast();
  }

  // --- phase changes -------------------------------------------------------------------------

  startWriting() {
    const s = this.s!;
    let pool = eligible(s.settings.spice, s.settings.categories);
    let fresh = pool.filter((i) => !s.used.includes(i) && i !== s.word);
    if (!fresh.length) {
      s.used = []; // ran through the list: start over
      fresh = pool.filter((i) => i !== s.word);
      if (!fresh.length) fresh = pool;
    }
    s.word = fresh[Math.floor(Math.random() * fresh.length)];
    s.used.push(s.word);
    s.phase = "writing";
    s.fakes = {};
    s.options = [];
    s.votes = {};
    s.laughs = {};
    s.results = null;
    this.setDeadline(s.settings.writeSecs);
  }

  setDeadline(secs: number | null) {
    const s = this.s!;
    s.deadline = secs === null ? null : Date.now() + secs * 1000;
    if (s.deadline === null) this.ctx.storage.deleteAlarm();
    else this.ctx.storage.setAlarm(s.deadline);
  }

  // Everyone who's here has done their part: move on without waiting for the timer.
  maybeAdvance() {
    const s = this.s!;
    const here = [...this.connectedIds()].filter((id) => s.players.some((p) => p.id === id));
    if (!here.length) return;
    if (s.phase === "writing" && here.every((id) => s.fakes[id])) this.advance();
    else if (s.phase === "voting" && here.every((id) => s.votes[id] || !this.canVote(id))) this.advance();
  }

  canVote(pid: string) {
    return this.s!.options.some((o) => o.author !== pid);
  }

  advance() {
    const s = this.s!;
    if (s.phase === "writing") {
      const w = WORDS[s.word!];
      const opts: Option[] = [{ id: rid(), text: tidy(w.definition), kind: "real" }];
      for (const [author, text] of Object.entries(s.fakes)) {
        if (!s.players.some((p) => p.id === author)) continue;
        if (opts.some((o) => sameText(o.text, text))) continue; // exact duplicates would give the game away
        opts.push({ id: rid(), text, kind: "fake", author });
      }
      if (s.players.length < DECOYS_UNDER) {
        for (const d of w.decoys ?? []) {
          const text = tidy(d);
          if (text && !opts.some((o) => sameText(o.text, text))) opts.push({ id: rid(), text, kind: "decoy" });
        }
      }
      s.options = shuffle(opts);
      s.votes = {};
      s.phase = "voting";
      this.setDeadline(s.settings.voteSecs);
    } else if (s.phase === "voting") {
      s.phase = "reveal";
      s.laughs = {};
      this.setDeadline(null);
    }
  }

  score() {
    const s = this.s!;
    const gain = new Map<string, { n: number; why: string[] }>(s.players.map((p) => [p.id, { n: 0, why: [] }]));
    const add = (pid: string | undefined, n: number, why: string) => {
      const g = pid ? gain.get(pid) : undefined;
      if (!g) return;
      g.n += n;
      g.why.push(why);
    };
    const real = s.options.find((o) => o.kind === "real")!;
    for (const [pid, oid] of Object.entries(s.votes)) {
      if (oid === real.id) add(pid, 2, "found the real one");
    }
    for (const o of s.options) {
      if (o.kind !== "fake") continue;
      const n = Object.values(s.votes).filter((v) => v === o.id).length;
      if (n) add(o.author, n, `fooled ${n}`);
    }
    const fakes = s.options.filter((o) => o.kind === "fake");
    const most = Math.max(0, ...fakes.map((o) => s.laughs[o.id]?.length ?? 0));
    if (most > 0) for (const o of fakes) if ((s.laughs[o.id]?.length ?? 0) === most) add(o.author, 1, "funniest");
    s.results = s.players.map((p) => {
      const g = gain.get(p.id)!;
      p.score += g.n;
      return { name: p.name, gained: g.n, why: g.why };
    });
    s.results.sort((a, b) => b.gained - a.gained);
    s.phase = "scores";
    this.setDeadline(null);
  }

  // --- views ---------------------------------------------------------------------------------

  view(pid: string): View {
    const s = this.s!;
    const here = this.connectedIds();
    const name = (id?: string) => s.players.find((p) => p.id === id)?.name ?? "someone";
    const v: View = {
      code: s.code, you: pid, phase: s.phase, settings: s.settings, categories: CATEGORIES, round: s.round,
      deadline: s.deadline,
      players: s.players.map((p) => ({
        id: p.id, name: p.name, score: p.score, host: p.host, connected: here.has(p.id),
        done: s.phase === "writing" ? !!s.fakes[p.id] : s.phase === "voting" ? !!s.votes[p.id] : false,
      })),
    };
    if (s.word !== null && s.phase !== "lobby" && s.phase !== "final") {
      const w = WORDS[s.word];
      v.word = { word: w.word, pos: w.pos };
      v.myFake = s.fakes[pid];
      if (s.phase === "voting") {
        v.options = s.options.map((o) => ({ id: o.id, text: o.text, mine: o.author === pid }));
        v.myVote = s.votes[pid];
      } else if (s.phase === "reveal" || s.phase === "scores") {
        // Fakes first, most-voted last among them; the real one closes the reveal.
        const votersOf = (o: Option) => Object.entries(s.votes).filter(([, x]) => x === o.id).map(([p]) => name(p));
        const order = [...s.options].sort((a, b) =>
          (a.kind === "real" ? 1 : 0) - (b.kind === "real" ? 1 : 0) || votersOf(a).length - votersOf(b).length);
        v.options = order.map((o): OptionView => ({
          id: o.id, text: o.text, mine: o.author === pid, kind: o.kind,
          author: o.kind === "fake" ? name(o.author) : undefined,
          voters: votersOf(o), laughs: s.laughs[o.id]?.length ?? 0, laughedByMe: !!s.laughs[o.id]?.includes(pid),
        }));
        v.myVote = s.votes[pid];
        v.dealerNote = w.dealer_note;
      }
    }
    if (s.results && (s.phase === "scores" || s.phase === "final")) v.results = s.results;
    return v;
  }

  broadcast() {
    for (const ws of this.ctx.getWebSockets()) {
      const pid = this.pidOf(ws);
      if (!pid || !this.s!.players.some((p) => p.id === pid)) continue;
      try {
        ws.send(JSON.stringify({ t: "view", view: this.view(pid) } satisfies ServerMsg));
      } catch {
        // socket already gone; webSocketClose will clean up
      }
    }
  }

  async save() {
    await this.ctx.storage.put("s", this.s);
  }
}
