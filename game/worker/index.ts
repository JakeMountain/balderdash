export { Room } from "./room";

export interface Env {
  ROOMS: DurableObjectNamespace;
  ASSETS: Fetcher;
}

const LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ"; // no I, L or O: easy to read aloud and type

function newCode() {
  const b = crypto.getRandomValues(new Uint8Array(4));
  return [...b].map((x) => LETTERS[x % LETTERS.length]).join("");
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/api/rooms" && req.method === "POST") {
      for (let i = 0; i < 10; i++) {
        const code = newCode();
        const stub = env.ROOMS.get(env.ROOMS.idFromName(code));
        const r = await stub.fetch("https://room/create", { method: "POST", body: JSON.stringify({ code }) });
        if (r.ok) return Response.json({ code });
      }
      return new Response("couldn't find a free room code", { status: 503 });
    }
    const m = url.pathname.match(/^\/api\/rooms\/([A-Za-z]{4})\/ws$/);
    if (m) {
      const code = m[1].toUpperCase();
      return env.ROOMS.get(env.ROOMS.idFromName(code)).fetch(req);
    }
    if (url.pathname.startsWith("/api/")) return new Response("not found", { status: 404 });
    return env.ASSETS.fetch(req);
  },
};
