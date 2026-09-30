// End-to-end smoke test: three bots play a 3-round game over real WebSockets.
//   npm run dev            (in one terminal)
//   npm run smoke          (in another; BASE=https://your.workers.dev npm run smoke for a deployed Worker)
// Covers: create/join, settings, "I know it" reroll, can't vote for your own, rejoin by name mid-round,
// a writing timer expiring with one fake missing, laugh points, and the scoring rules.
const BASE = process.env.BASE ?? "http://localhost:8787";
const WS = BASE.replace(/^http/, "ws");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
const check = (ok, what) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
  if (!ok) failures++;
};

class Bot {
  constructor(code, name) {
    this.code = code;
    this.name = name;
    this.view = null;
    this.waiters = [];
  }
  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(`${WS}/api/rooms/${this.code}/ws?name=${encodeURIComponent(this.name)}`);
      this.ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.t === "view") {
          this.view = m.view;
          this.waiters = this.waiters.filter((w) => !w(m.view));
        } else this.lastError = m.message;
      };
      this.ws.onopen = () => resolve(this);
      this.ws.onerror = reject;
    });
  }
  send(msg) {
    this.ws.send(JSON.stringify(msg));
  }
  until(pred, ms = 40000) {
    if (this.view && pred(this.view)) return Promise.resolve(this.view);
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error(`${this.name}: timed out waiting (phase ${this.view?.phase})`)), ms);
      this.waiters.push((v) => (pred(v) ? (clearTimeout(t), resolve(v), true) : false));
    });
  }
  close() {
    this.ws.close();
  }
}

const res = await fetch(`${BASE}/api/rooms`, { method: "POST" });
const { code } = await res.json();
check(/^[A-Z]{4}$/.test(code), `created room ${code}`);

const bots = [];
for (const n of ["Ada", "Bea", "Cy"]) bots.push(await new Bot(code, n).connect());
const [host] = bots;
await host.until((v) => v.players.length === 3);
check(host.view.players.find((p) => p.name === "Ada").host, "first player is host");

host.send({ t: "settings", settings: { rounds: 3, writeSecs: 20, spice: "spicy" } });
await host.until((v) => v.settings.rounds === 3 && v.settings.writeSecs === 20);
host.send({ t: "start" });
await Promise.all(bots.map((b) => b.until((v) => v.phase === "writing")));

for (let round = 1; round <= 3; round++) {
  if (round === 1) {
    const before = host.view.word.word;
    bots[1].send({ t: "knowIt" });
    await host.until((v) => v.word.word !== before);
    check(true, `"I know it" rerolled ${before} -> ${host.view.word.word}`);
  }
  let skipper = null;
  if (round === 2) {
    // Cy's phone drops mid-round and rejoins by name.
    const id = bots[2].view.you;
    bots[2].close();
    await sleep(300);
    bots[2] = await new Bot(code, "Cy").connect();
    await bots[2].until((v) => v.phase === "writing");
    check(bots[2].view.you === id, "rejoin by name keeps the same seat");
  }
  if (round === 3) skipper = bots[2]; // Cy doesn't write: the timer has to move things on
  const t0 = Date.now();
  for (const b of bots) if (b !== skipper) b.send({ t: "fake", text: `  ${b.name.toLowerCase()} bluff for round ${round}  ` });
  await Promise.all(bots.map((b) => b.until((v) => v.phase === "voting")));
  if (skipper) check(Date.now() - t0 > 15000, `writing timer expired and moved on (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  const opts = host.view.options;
  check(opts.some((o) => o.text === `Ada bluff for round ${round}.`), "fakes are tidied (trimmed, capitalized, period)");
  check(opts.length === (skipper ? 3 : 4), `ballot has ${opts.length} options (real + fakes)`);

  // Try to vote for your own fake: must be ignored.
  const own = opts.find((o) => o.mine);
  host.send({ t: "vote", option: own.id });
  await sleep(200);
  check(!host.view.myVote, "can't vote for your own fake");

  for (const b of bots) {
    const choices = b.view.options.filter((o) => !o.mine);
    b.send({ t: "vote", option: choices[(round + b.name.length) % choices.length].id });
  }
  await Promise.all(bots.map((b) => b.until((v) => v.phase === "reveal")));
  const reveal = host.view.options;
  check(reveal.at(-1).kind === "real", "real definition is revealed last");

  // Everyone laughs at Bea's fake (Bea can't laugh at her own).
  const beas = reveal.find((o) => o.author === "Bea");
  for (const b of bots) if (b.name !== "Bea") b.send({ t: "laugh", option: beas.id });
  await host.until((v) => v.options.find((o) => o.id === beas.id).laughs === 2);

  const expected = Object.fromEntries(bots.map((b) => [b.name, 0]));
  for (const o of host.view.options) {
    for (const voter of o.voters) if (o.kind === "real") expected[voter] += 2;
    if (o.kind === "fake") expected[o.author] += o.voters.length;
  }
  expected.Bea += 1; // most laughs
  const totalsBefore = Object.fromEntries(host.view.players.map((p) => [p.name, p.score]));
  host.send({ t: "next" });
  await Promise.all(bots.map((b) => b.until((v) => v.phase === "scores")));
  const got = Object.fromEntries(host.view.results.map((r) => [r.name, r.gained]));
  check(JSON.stringify(got, Object.keys(expected).sort()) === JSON.stringify(expected, Object.keys(expected).sort()),
    `round ${round} scoring ${JSON.stringify(got)}`);
  check(host.view.players.every((p) => p.score === totalsBefore[p.name] + expected[p.name]), "totals add up");
  host.send({ t: "next" });
  await Promise.all(bots.map((b) => b.until((v) => v.phase === (round === 3 ? "final" : "writing") && v.round >= round)));
}
check(host.view.phase === "final", "final scores after 3 rounds: " +
  host.view.players.map((p) => `${p.name} ${p.score}`).join(", "));
bots.forEach((b) => b.close());
console.log(failures ? `${failures} FAILED` : "all passed");
process.exit(failures ? 1 : 0);
