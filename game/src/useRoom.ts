import { useCallback, useEffect, useRef, useState } from "react";
import type { ClientMsg, ServerMsg, View } from "../shared/protocol";

export interface Seat {
  code: string;
  name: string;
}

const KEY = "bluff.seat";

export function loadSeat(): Seat | null {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? "null");
    return s && s.code && s.name ? s : null;
  } catch {
    return null;
  }
}

export function saveSeat(seat: Seat | null) {
  try {
    if (seat) localStorage.setItem(KEY, JSON.stringify(seat));
    else localStorage.removeItem(KEY);
  } catch {
    // private mode: rejoin-on-reload just won't work
  }
}

// Holds one WebSocket to the room and reconnects when a phone sleeps or drops Wi-Fi.
// Close codes 4000-4002 mean the server doesn't want us back (bad room, replaced, kicked).
export function useRoom(seat: Seat | null, onFatal: (message: string) => void) {
  const [view, setView] = useState<View | null>(null);
  const [online, setOnline] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const fatal = useRef(onFatal);
  fatal.current = onFatal;

  useEffect(() => {
    if (!seat) return;
    let stop = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout>;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const sock = new WebSocket(
        `${proto}://${location.host}/api/rooms/${seat.code}/ws?name=${encodeURIComponent(seat.name)}`,
      );
      ws.current = sock;
      sock.onopen = () => {
        retry = 0;
        setOnline(true);
      };
      sock.onmessage = (e) => {
        const msg: ServerMsg = JSON.parse(e.data);
        if (msg.t === "view") setView(msg.view);
        else {
          setNotice(msg.message);
          setTimeout(() => setNotice(null), 3500);
        }
      };
      sock.onclose = (e) => {
        setOnline(false);
        if (stop) return;
        if (e.code >= 4000 && e.code < 4100) {
          fatal.current(e.reason || "Disconnected.");
          return;
        }
        timer = setTimeout(connect, Math.min(8000, 500 * 2 ** retry++));
      };
    };
    connect();
    const wake = () => {
      if (document.visibilityState === "visible" && ws.current?.readyState !== WebSocket.OPEN) {
        clearTimeout(timer);
        ws.current?.close();
        connect();
      }
    };
    document.addEventListener("visibilitychange", wake);
    return () => {
      stop = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", wake);
      ws.current?.close();
      setView(null);
    };
  }, [seat?.code, seat?.name]);

  const send = useCallback((msg: ClientMsg) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(msg));
  }, []);

  return { view, online, notice, send };
}

export function useCountdown(deadline: number | null) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!deadline) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [deadline]);
  return deadline ? Math.max(0, Math.ceil((deadline - now) / 1000)) : null;
}
