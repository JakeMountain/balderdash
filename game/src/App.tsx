import { useEffect, useState } from "react";
import { MAX_FAKE } from "../shared/format";
import type { ClientMsg, OptionView, Spice, View } from "../shared/protocol";
import { loadSeat, saveSeat, useCountdown, useRoom, type Seat } from "./useRoom";

type Send = (m: ClientMsg) => void;

export function App() {
  const [seat, setSeat] = useState<Seat | null>(loadSeat);
  const [bounced, setBounced] = useState<string | null>(null);
  const { view, online, notice, send } = useRoom(seat, (message) => {
    saveSeat(null);
    setSeat(null);
    setBounced(message);
  });
  const leave = () => {
    saveSeat(null);
    setSeat(null);
  };
  const phaseKey = view ? `${view.phase}:${view.round}` : "";
  useEffect(() => window.scrollTo(0, 0), [phaseKey]); // each phase starts at the top

  if (!seat) {
    return (
      <Home
        error={bounced}
        onSeat={(s) => {
          saveSeat(s);
          setBounced(null);
          setSeat(s);
        }}
      />
    );
  }
  if (!view) return <Shell><p className="muted center">Connecting to {seat.code}…</p></Shell>;
  const me = view.players.find((p) => p.id === view.you);
  return (
    <Shell code={view.code} online={online} onLeave={leave}>
      {notice && <div className="toast">{notice}</div>}
      <Phase view={view} host={!!me?.host} send={send} />
    </Shell>
  );
}

function Shell({ children, code, online, onLeave }: {
  children: React.ReactNode; code?: string; online?: boolean; onLeave?: () => void;
}) {
  return (
    <div className="app">
      <header>
        <span className="logo">Bluff Dictionary</span>
        {code && (
          <span className="room">
            <span className={online ? "dot on" : "dot"} />
            {code}
            <button className="link" onClick={() => confirm("Leave this room?") && onLeave?.()}>leave</button>
          </span>
        )}
      </header>
      <main>{children}</main>
    </div>
  );
}

function Home({ onSeat, error }: { onSeat: (s: Seat) => void; error: string | null }) {
  const [name, setName] = useState(() => loadSeat()?.name ?? localStorage.getItem("bluff.name") ?? "");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(error);
  const n = name.trim();
  const go = (c: string) => {
    localStorage.setItem("bluff.name", n);
    onSeat({ code: c.toUpperCase(), name: n });
  };
  const create = async () => {
    setBusy(true);
    try {
      const r = await fetch("/api/rooms", { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      go(((await r.json()) as { code: string }).code);
    } catch (e) {
      setErr(`Couldn't create a room: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Shell>
      <h1 className="hero">Real words.<br />Ridiculous definitions.<br /><em>Which one's true?</em></h1>
      {err && <p className="error">{err}</p>}
      <label>Your name
        <input value={name} maxLength={20} autoComplete="nickname" onChange={(e) => setName(e.target.value)} />
      </label>
      <div className="row">
        <input className="code" placeholder="CODE" value={code} maxLength={4} autoCapitalize="characters"
          onChange={(e) => setCode(e.target.value.replace(/[^a-z]/gi, "").toUpperCase())} />
        <button disabled={!n || code.length !== 4} onClick={() => go(code)}>Join</button>
      </div>
      <p className="muted center">or</p>
      <button className="primary" disabled={!n || busy} onClick={create}>Create a room</button>
    </Shell>
  );
}

function Phase({ view, host, send }: { view: View; host: boolean; send: Send }) {
  switch (view.phase) {
    case "lobby": return <Lobby view={view} host={host} send={send} />;
    case "writing": return <Writing view={view} host={host} send={send} />;
    case "voting": return <Voting view={view} host={host} send={send} />;
    case "reveal": return <Reveal view={view} host={host} send={send} />;
    case "scores": return <Scores view={view} host={host} send={send} />;
    case "final": return <Final view={view} host={host} send={send} />;
  }
}

function Players({ view, host, send, showDone }: { view: View; host?: boolean; send?: Send; showDone?: boolean }) {
  return (
    <ul className="players">
      {view.players.map((p) => (
        <li key={p.id} className={p.connected ? "" : "away"}>
          <span>
            {showDone && <span className="tick">{p.done ? "✓" : "…"}</span>}
            {p.name}{p.host && " ★"}{p.id === view.you && " (you)"}
          </span>
          <span className="score">
            {view.phase !== "lobby" && p.score}
            {host && p.id !== view.you && view.phase === "lobby" && (
              <button className="link" onClick={() => send?.({ t: "kick", player: p.id })}>remove</button>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

const SPICE_HELP: Record<Spice, string> = {
  mild: "Clean words only",
  cheeky: "Crude and bodily, nothing sexual",
  spicy: "Everything (PG-13)",
};

function Lobby({ view, host, send }: { view: View; host: boolean; send: Send }) {
  const s = view.settings;
  const set = (patch: Partial<typeof s>) => send({ t: "settings", settings: patch });
  const toggleCat = (c: string) =>
    set({ categories: s.categories.includes(c) ? s.categories.filter((x) => x !== c) : [...s.categories, c] });
  return (
    <>
      <p className="center big-code">Room <strong>{view.code}</strong></p>
      <p className="muted center">Others join with this code.</p>
      <Players view={view} host={host} send={send} />
      {host ? (
        <div className="settings">
          <label>Rounds
            <input type="number" min={1} max={30} value={s.rounds} onChange={(e) => set({ rounds: +e.target.value })} />
          </label>
          <label>Seconds to write
            <input type="number" min={20} max={300} step={10} value={s.writeSecs}
              onChange={(e) => set({ writeSecs: +e.target.value })} />
          </label>
          <div className="seg">
            {(["mild", "cheeky", "spicy"] as Spice[]).map((sp) => (
              <button key={sp} className={s.spice === sp ? "on" : ""} onClick={() => set({ spice: sp })}>{sp}</button>
            ))}
          </div>
          <p className="muted small">{SPICE_HELP[s.spice]}</p>
          <p className="small">Categories {s.categories.length ? "" : <span className="muted">(all)</span>}</p>
          <div className="chips">
            {view.categories.map((c) => (
              <button key={c} className={s.categories.includes(c) ? "chip on" : "chip"} onClick={() => toggleCat(c)}>
                {c.replace("_", " & ")}
              </button>
            ))}
          </div>
          <button className="primary" disabled={view.players.length < 2} onClick={() => send({ t: "start" })}>
            {view.players.length < 2 ? "Waiting for players…" : `Start (${view.players.length} players)`}
          </button>
        </div>
      ) : (
        <p className="muted center">
          Waiting for the host to start. {s.rounds} rounds, {s.spice}
          {s.categories.length ? `, ${s.categories.join(", ")}` : ""}.
        </p>
      )}
    </>
  );
}

function WordCard({ view }: { view: View }) {
  const left = useCountdown(view.deadline);
  return (
    <div className="card word">
      <div className="meta">
        <span>Round {view.round} of {view.settings.rounds}</span>
        {left !== null && <span className={left <= 10 ? "timer hurry" : "timer"}>{left}s</span>}
      </div>
      <h2>{view.word?.word}</h2>
      <p className="pos">{view.word?.pos}</p>
    </div>
  );
}

function Writing({ view, host, send }: { view: View; host: boolean; send: Send }) {
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  const submitted = view.myFake && !editing;
  return (
    <>
      <WordCard view={view} />
      {submitted ? (
        <div className="card">
          <p className="muted small">Your fake</p>
          <p className="fake">{view.myFake}</p>
          <button className="link" onClick={() => { setText(view.myFake ?? ""); setEditing(true); }}>edit</button>
        </div>
      ) : (
        <form onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) return;
          send({ t: "fake", text });
          setEditing(false);
        }}>
          <textarea autoFocus rows={3} maxLength={MAX_FAKE} placeholder="Write a definition that sounds real…"
            value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row between">
            <span className="muted small">{text.length}/{MAX_FAKE}</span>
            <button className="primary" disabled={!text.trim()}>Submit</button>
          </div>
        </form>
      )}
      <Players view={view} showDone />
      <div className="row between">
        <button className="link" onClick={() => confirm("Skip this word for everyone?") && send({ t: "knowIt" })}>
          I know this word
        </button>
        {host && <button className="link" onClick={() => send({ t: "next" })}>end writing now</button>}
      </div>
    </>
  );
}

function Voting({ view, host, send }: { view: View; host: boolean; send: Send }) {
  return (
    <>
      <WordCard view={view} />
      <p className="center">Which one is real?</p>
      <div className="options">
        {view.options?.map((o) => (
          <button key={o.id} disabled={o.mine}
            className={`option ${view.myVote === o.id ? "picked" : ""} ${o.mine ? "mine" : ""}`}
            onClick={() => send({ t: "vote", option: o.id })}>
            {o.text}
            {o.mine && <span className="tag">yours</span>}
          </button>
        ))}
      </div>
      <Players view={view} showDone />
      {host && <button className="link" onClick={() => send({ t: "next" })}>end voting now</button>}
    </>
  );
}

function RevealOption({ o, send }: { o: OptionView; send: Send }) {
  return (
    <div className={`card reveal ${o.kind}`}>
      <p className="fake">{o.text}</p>
      <p className="small">
        {o.kind === "real" ? <strong>The real definition</strong>
          : o.kind === "decoy" ? <span className="muted">A computer's bluff</span>
          : <>by <strong>{o.author}</strong></>}
        {" · "}
        {o.voters?.length ? `picked by ${o.voters.join(", ")}` : <span className="muted">no votes</span>}
      </p>
      {o.kind === "fake" && !o.mine && (
        <button className={o.laughedByMe ? "laugh on" : "laugh"} onClick={() => send({ t: "laugh", option: o.id })}>
          😂 {o.laughs || ""}
        </button>
      )}
      {o.kind === "fake" && o.mine && !!o.laughs && <span className="laugh static">😂 {o.laughs}</span>}
    </div>
  );
}

function Reveal({ view, host, send }: { view: View; host: boolean; send: Send }) {
  return (
    <>
      <div className="card word"><h2>{view.word?.word}</h2><p className="pos">{view.word?.pos}</p></div>
      <p className="muted center small">Tap 😂 on the funniest bluff. Most laughs gets a point.</p>
      {view.options?.map((o) => <RevealOption key={o.id} o={o} send={send} />)}
      {view.dealerNote && <p className="note">Fun fact: {view.dealerNote}</p>}
      {host ? <button className="primary" onClick={() => send({ t: "next" })}>Show scores</button>
        : <p className="muted center">The host moves on when everyone's done laughing.</p>}
    </>
  );
}

function Results({ view }: { view: View }) {
  return (
    <ul className="players results">
      {view.results?.map((r) => (
        <li key={r.name}>
          <span>{r.name}<span className="muted small"> {r.why.join(", ")}</span></span>
          <span className="score">+{r.gained}</span>
        </li>
      ))}
    </ul>
  );
}

function Scores({ view, host, send }: { view: View; host: boolean; send: Send }) {
  const last = view.round >= view.settings.rounds;
  return (
    <>
      <h2 className="center">This round</h2>
      <Results view={view} />
      <h2 className="center">Totals</h2>
      <Standings view={view} />
      {host ? <button className="primary" onClick={() => send({ t: "next" })}>{last ? "Final scores" : "Next word"}</button>
        : <p className="muted center">Waiting for the host…</p>}
    </>
  );
}

function Standings({ view }: { view: View }) {
  const sorted = [...view.players].sort((a, b) => b.score - a.score);
  return (
    <ol className="players standings">
      {sorted.map((p) => <li key={p.id}><span>{p.name}</span><span className="score">{p.score}</span></li>)}
    </ol>
  );
}

function Final({ view, host, send }: { view: View; host: boolean; send: Send }) {
  const top = Math.max(...view.players.map((p) => p.score));
  const winners = view.players.filter((p) => p.score === top).map((p) => p.name);
  return (
    <>
      <h1 className="center hero">{winners.join(" & ")} {winners.length > 1 ? "win" : "wins"}!</h1>
      <Standings view={view} />
      {host && <button className="primary" onClick={() => send({ t: "again" })}>Play again</button>}
    </>
  );
}
