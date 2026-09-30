# Bluff Dictionary game

```
npm install
npm run dev      # builds the client, serves everything from wrangler dev on port 8787 (0.0.0.0, so phones on the Wi-Fi can join)
npm run smoke    # with dev running: 3 bots play 3 rounds and check the rules
npm run dev:ui   # hot-reloading client on 5173; run `npx wrangler dev` alongside for /api
npm run deploy   # vite build + wrangler deploy; then BASE=https://<worker url> npm run smoke
```

- `worker/room.ts`: the Durable Object, one per room code. It holds all state and timers (alarms), persists to storage, and sends each phone a redacted view.
- `shared/`: the message protocol, and `tidy()`, the formatting applied to every ballot option, the real one included.
- `src/`: one React app. The host is just a player with extra buttons.
