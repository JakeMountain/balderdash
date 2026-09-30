import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run dev:ui` gives hot reload; run `npx wrangler dev` alongside it for the /api side.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://localhost:8787", ws: true } } },
});
