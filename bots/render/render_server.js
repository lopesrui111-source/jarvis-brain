// Render-Server fuer das JARVIS Studio-Team
// - Lauscht auf Redis-Queue bot:render:inbox
// - Rendert eine Remotion-Komposition zu MP4 (immer 60fps)
// - Legt das Video in /app/vault/videos ab, meldet den Pfad zurueck
//
// Auftrag (JSON): { id, komposition, props, format, dauer_sek, vorschau }
//   komposition: "kinetic-tiktok" | "kinetic-linkedin" | "kinetic-quadrat"
//   props:       { zeilen: [...], akzent: "#5DCAA5" }  (an die Komposition)
//   dauer_sek:   optionale Laenge (Default aus Komposition)
//   vorschau:    true = schneller Grob-Render zum Selbstpruefen (klein, hoher CRF).
//                Dauert nur einen Bruchteil, damit der Regie-Bot oft iterieren
//                kann statt nach jedem Blindflug 10+ Minuten zu warten.

const { createClient } = require("redis");
const { execFile } = require("child_process");
const fs = require("fs");
const path = require("path");

const REDIS_HOST = process.env.REDIS_HOST || "redis";
const REDIS_PORT = process.env.REDIS_PORT || "6379";
const INBOX = "bot:render:inbox";
const VIDEO_DIR = "/app/vault/videos";

function log(m) { console.log("  " + m); }

async function main() {
  fs.mkdirSync(VIDEO_DIR, { recursive: true });
  const r = createClient({ url: `redis://${REDIS_HOST}:${REDIS_PORT}` });
  r.on("error", (e) => log("[redis] " + e.message));
  await r.connect();
  log("[redis] verbunden");
  log("Render-Server bereit.\n");

  while (true) {
    try {
      const res = await r.blPop(INBOX, 5);
      if (!res) continue;
      let msg;
      try { msg = JSON.parse(res.element); } catch { continue; }

      const id = msg.id || String(Date.now());
      const komposition = msg.komposition || "kinetic-tiktok";
      const props = msg.props || {};
      const vorschau = !!msg.vorschau;
      const replyQ = `bot:render:reply:${id}`;

      log(`Render-Auftrag: ${komposition} (id=${id})${vorschau ? " [VORSCHAU]" : ""}`);

      const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const outName = `${ts}_${komposition}${vorschau ? "_vorschau" : ""}.mp4`;
      const outPath = path.join(VIDEO_DIR, outName);

      const args = [
        "remotion", "render", "src/index.js", komposition, outPath,
        "--props", JSON.stringify(props),
        "--codec", "h264",
        "--public-dir", "/app/public",
      ];

      if (vorschau) {
        // Grob-Render: 40% Aufloesung, starke Kompression, schnelles Encoding.
        // Bewegung und Komposition bleiben beurteilbar, der Render dauert aber
        // nur einen Bruchteil.
        args.push("--scale", "0.4");
        args.push("--crf", "34");
        args.push("--jpeg-quality", "60");
        args.push("--concurrency", "2");
      }

      // Story-Kompositionen bestimmen ihre Dauer selbst (calculateMetadata) —
      // hier NIE --frames setzen, sonst wird die Story abgeschnitten.
      const istStory = komposition.startsWith("story");
      if (msg.dauer_sek && !istStory) {
        args.push("--frames", `0-${Math.round(msg.dauer_sek * 60) - 1}`);
      }

      const start = Date.now();
      // Vorschau bekommt ein kuerzeres Timeout — wenn sie so lange braucht,
      // stimmt etwas nicht.
      const timeoutMs = vorschau ? 1000 * 60 * 6 : 1000 * 60 * 20;

      execFile("npx", args, { cwd: "/app", timeout: timeoutMs },
        async (err, stdout, stderr) => {
          if (err) {
            log(`[render] Fehler: ${err.message}`);
            log(stderr ? stderr.slice(-400) : "");
            const detail = (stderr || err.message || "").slice(-700);
            await antwort(r, replyQ, `FEHLER beim Render: ${detail}`);
            return;
          }
          const sek = ((Date.now() - start) / 1000).toFixed(1);
          log(`[render] fertig in ${sek}s -> ${outName}`);
          await antwort(r, replyQ,
            `Video gerendert (${sek}s)${vorschau ? " [VORSCHAU — niedrige Qualitaet, nur zum Pruefen]" : ""}: vault/videos/${outName}`);
        });
    } catch (e) {
      log("[loop] " + e.message);
      await new Promise((res) => setTimeout(res, 3000));
    }
  }
}

async function antwort(r, queue, text) {
  try {
    await r.rPush(queue, text);
    await r.expire(queue, 600);
  } catch (e) {
    log("[reply] " + e.message);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
