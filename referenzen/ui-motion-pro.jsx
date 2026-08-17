// ui-motion-pro.jsx — REFERENZ: UI/UX-MOTION
//
// Lehrmaterial fuer die Kategorie "UI/UX-Animation". Zeigt, wie man ein
// Produkt LEBENDIG wirken laesst, ohne das ganze Dashboard einzublenden.
// Das ist oft wirkungsvoller als ein Screenshot: der Zuschauer sieht, wie
// sich die Software ANFUEHLT.
//
// DIE FUENF TECHNIKEN:
//
// 1) CURSOR, DER KLICKT — der Cursor faehrt mit Ease-Out zum Ziel (nie
//    linear, das wirkt robotisch), der Klick ist ein kurzer Scale-Dip +
//    eine ausbreitende Ripple-Welle. Das Auge folgt dem Cursor, dadurch
//    steuert man die Aufmerksamkeit.
//
// 2) BUTTON-ZUSTAENDE — Ruhe -> Hover (heller, leicht angehoben) ->
//    Aktiv (gedrueckt) -> Laden (Spinner) -> Erfolg (Haken). Diese Kette
//    erzaehlt eine Mini-Geschichte in 2 Sekunden.
//
// 3) FORMULARFELD, DAS SICH TIPPT — Zeichen fuer Zeichen mit blinkendem
//    Cursor. Vermittelt "das geht schnell und einfach".
//
// 4) TOAST-MELDUNG — kommt von unten mit Overshoot, bleibt kurz, geht
//    wieder. Der Bestaetigungs-Moment.
//
// 5) SKELETON -> INHALT — pulsierende Platzhalter, die sich in echten
//    Inhalt verwandeln. Zeigt Ladevorgang ohne Wartegefuehl.
//
// Alle Techniken sind zeitlich versetzt, sodass immer etwas passiert.

import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { BRAND } from "../brand.js";

export const meta = {
  dauerSek: 9,
  defaultProps: { titel: "So einfach", titelAkzent: "geht das." },
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };
const smooth = (t) => t * t * (3 - 2 * t);
const ease = (f, von, bis, a, b) => {
  const t = interpolate(f, [von, bis], [0, 1], clamp);
  return a + (b - a) * smooth(t);
};

/* ══════════════════════════════════════════════════
   TECHNIK 1: Cursor mit Klick-Ripple
   ══════════════════════════════════════════════════ */
const Cursor = ({ frame, punkte, p }) => {
  // punkte: [{ frame, x, y, klick }] — der Cursor faehrt sie nacheinander an
  let x = punkte[0].x, y = punkte[0].y;
  for (let i = 0; i < punkte.length - 1; i++) {
    const a = punkte[i], b = punkte[i + 1];
    if (frame >= a.frame && frame <= b.frame) {
      const t = smooth(interpolate(frame, [a.frame, b.frame], [0, 1], clamp));
      x = a.x + (b.x - a.x) * t;
      y = a.y + (b.y - a.y) * t;
    } else if (frame > b.frame) { x = b.x; y = b.y; }
  }
  // Klick-Effekt: kurzer Scale-Dip am Cursor
  const klickPunkte = punkte.filter((pt) => pt.klick);
  const naechsterKlick = klickPunkte.find((pt) => Math.abs(frame - pt.frame) < 30);
  const dip = naechsterKlick
    ? interpolate(frame, [naechsterKlick.frame - 2, naechsterKlick.frame + 3, naechsterKlick.frame + 10],
        [1, 0.82, 1], clamp)
    : 1;
  const op = interpolate(frame, [punkte[0].frame - 10, punkte[0].frame + 6], [0, 1], clamp);

  return (
    <>
      {/* Ripple-Wellen an den Klickpunkten */}
      {klickPunkte.map((pt, i) => {
        const r = interpolate(frame, [pt.frame, pt.frame + 34], [4, 52], clamp);
        const rop = interpolate(frame, [pt.frame, pt.frame + 34], [0.5, 0], clamp);
        if (rop <= 0.01) return null;
        return (
          <div key={i} style={{
            position: "absolute", left: pt.x, top: pt.y,
            width: r * 2, height: r * 2, marginLeft: -r, marginTop: -r,
            borderRadius: "50%", border: `2px solid ${p.akzent}`,
            opacity: rop, pointerEvents: "none",
          }} />
        );
      })}
      {/* Der Cursor selbst */}
      <div style={{
        position: "absolute", left: x, top: y, opacity: op,
        transform: `scale(${dip})`, transformOrigin: "top left",
        pointerEvents: "none", zIndex: 20,
        filter: "drop-shadow(0 3px 8px rgba(0,0,0,0.6))",
      }}>
        <svg width="26" height="30" viewBox="0 0 26 30">
          <path d="M2 2 L2 22 L7.5 17 L11 26 L15 24 L11.5 15.5 L19 15 Z"
            fill="#FFFFFF" stroke="#0b1016" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      </div>
    </>
  );
};

/* ══════════════════════════════════════════════════
   TECHNIK 2: Button mit Zustandskette
   ══════════════════════════════════════════════════ */
const ZustandsButton = ({ frame, start, x, y, breite, hoehe, p }) => {
  // Ruhe -> Hover -> Klick -> Laden -> Erfolg
  const hover = interpolate(frame, [start, start + 12], [0, 1], clamp);
  const klick = interpolate(frame, [start + 20, start + 25, start + 32], [0, 1, 0], clamp);
  const laden = interpolate(frame, [start + 26, start + 34], [0, 1], clamp)
              * interpolate(frame, [start + 78, start + 88], [1, 0], clamp);
  const erfolg = interpolate(frame, [start + 84, start + 98], [0, 1], clamp);
  const op = interpolate(frame, [start - 14, start], [0, 1], clamp);

  const spinnerRot = (frame - start - 26) * 7;

  return (
    <div style={{
      position: "absolute", left: x, top: y, width: breite, height: hoehe,
      opacity: op,
      transform: `translateY(${-hover * 2 + klick * 3}px) scale(${1 + hover * 0.02 - klick * 0.03})`,
      borderRadius: hoehe * 0.28,
      background: erfolg > 0.5
        ? `linear-gradient(135deg, ${p.akzent}, ${p.akzent}cc)`
        : `linear-gradient(135deg, ${p.akzent}${hover > 0.5 ? "" : "dd"}, ${p.akzent}aa)`,
      boxShadow: `0 ${4 + hover * 8}px ${14 + hover * 16}px ${p.akzent}${hover > 0.5 ? "44" : "22"}`,
      display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
      color: "#0b1016", fontFamily: BRAND.fonts.display,
      fontSize: hoehe * 0.34, fontWeight: 700, letterSpacing: "-0.01em",
    }}>
      {laden > 0.5 ? (
        <svg width={hoehe * 0.4} height={hoehe * 0.4} viewBox="0 0 24 24"
          style={{ transform: `rotate(${spinnerRot}deg)` }}>
          <circle cx="12" cy="12" r="9" fill="none" stroke="#0b1016"
            strokeWidth="3" strokeOpacity="0.25" />
          <path d="M12 3 a9 9 0 0 1 9 9" fill="none" stroke="#0b1016"
            strokeWidth="3" strokeLinecap="round" />
        </svg>
      ) : erfolg > 0.5 ? (
        <>
          <svg width={hoehe * 0.36} height={hoehe * 0.36} viewBox="0 0 24 24">
            <path d="M5 13 L10 18 L19 6" fill="none" stroke="#0b1016" strokeWidth="3.4"
              strokeLinecap="round" strokeLinejoin="round"
              strokeDasharray="30"
              strokeDashoffset={30 * (1 - interpolate(frame, [start + 86, start + 104], [0, 1], clamp))} />
          </svg>
          Erledigt
        </>
      ) : "Mahnung senden"}
    </div>
  );
};

/* ══════════════════════════════════════════════════
   TECHNIK 3: Feld, das sich tippt
   ══════════════════════════════════════════════════ */
const TippFeld = ({ frame, start, x, y, breite, hoehe, text, label, p }) => {
  const zeichen = Math.round(interpolate(frame, [start, start + text.length * 2.6],
    [0, text.length], clamp));
  const sichtbar = text.slice(0, zeichen);
  const fertig = zeichen >= text.length;
  // Cursor blinkt, solange getippt wird
  const blink = fertig ? 0 : (Math.floor(frame / 16) % 2 === 0 ? 1 : 0.15);
  const op = interpolate(frame, [start - 16, start - 2], [0, 1], clamp);
  const fokus = interpolate(frame, [start - 6, start + 6], [0, 1], clamp)
              * interpolate(frame, [start + text.length * 2.6 + 20, start + text.length * 2.6 + 34], [1, 0], clamp);

  return (
    <div style={{ position: "absolute", left: x, top: y, width: breite, opacity: op }}>
      <div style={{
        fontFamily: BRAND.fonts.sans, fontSize: hoehe * 0.3,
        color: "#7f95a6", letterSpacing: "0.1em", marginBottom: 8,
      }}>{label}</div>
      <div style={{
        height: hoehe, borderRadius: 10,
        background: "rgba(255,255,255,0.04)",
        border: `1px solid ${fokus > 0.3 ? p.akzent + "88" : "rgba(255,255,255,0.1)"}`,
        boxShadow: fokus > 0.3 ? `0 0 0 3px ${p.akzent}1a` : "none",
        display: "flex", alignItems: "center", padding: `0 ${hoehe * 0.34}px`,
        fontFamily: BRAND.fonts.sans, fontSize: hoehe * 0.36, color: "#e4f2fb",
      }}>
        {sichtbar}
        <span style={{
          display: "inline-block", width: 2, height: hoehe * 0.44,
          background: p.akzent, marginLeft: 2, opacity: blink,
        }} />
      </div>
    </div>
  );
};

/* ══════════════════════════════════════════════════
   TECHNIK 4: Toast-Meldung
   ══════════════════════════════════════════════════ */
const Toast = ({ frame, start, x, y, breite, hoehe, text, p }) => {
  // kommt von unten mit Overshoot, bleibt, geht wieder
  const rein = interpolate(frame, [start, start + 22], [0, 1],
    { easing: Easing.out(Easing.back(1.6)), ...clamp });
  const raus = interpolate(frame, [start + 88, start + 106], [0, 1],
    { easing: Easing.in(Easing.cubic), ...clamp });
  const yOff = (1 - rein) * hoehe * 1.8 + raus * hoehe * 1.8;
  const op = rein * (1 - raus);
  if (op <= 0.01) return null;
  return (
    <div style={{
      position: "absolute", left: x, top: y, width: breite, height: hoehe,
      transform: `translateY(${yOff}px)`, opacity: op,
      borderRadius: 12,
      background: "linear-gradient(150deg, rgba(255,255,255,0.08), rgba(10,16,22,0.9))",
      border: `1px solid ${p.akzent}44`,
      backdropFilter: "blur(20px)",
      boxShadow: `0 16px 44px rgba(0,0,0,0.5), 0 0 30px ${p.akzent}1a`,
      display: "flex", alignItems: "center", gap: hoehe * 0.3,
      padding: `0 ${hoehe * 0.36}px`,
    }}>
      <div style={{
        width: hoehe * 0.44, height: hoehe * 0.44, borderRadius: "50%",
        background: `${p.akzent}22`, border: `1px solid ${p.akzent}66`,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <svg width={hoehe * 0.24} height={hoehe * 0.24} viewBox="0 0 24 24">
          <path d="M5 13 L10 18 L19 6" fill="none" stroke={p.akzent} strokeWidth="3.4"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <span style={{
        fontFamily: BRAND.fonts.sans, fontSize: hoehe * 0.3, color: "#e4f2fb",
      }}>{text}</span>
    </div>
  );
};

/* ══════════════════════════════════════════════════
   TECHNIK 5: Skeleton -> Inhalt
   ══════════════════════════════════════════════════ */
const SkeletonListe = ({ frame, start, x, y, breite, zeilenH, anzahl, p }) => {
  const op = interpolate(frame, [start - 14, start], [0, 1], clamp);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: breite, opacity: op,
      display: "flex", flexDirection: "column", gap: zeilenH * 0.5 }}>
      {Array.from({ length: anzahl }).map((_, i) => {
        // jede Zeile wechselt zeitversetzt von Skeleton zu Inhalt
        const wechsel = interpolate(frame, [start + 30 + i * 12, start + 46 + i * 12],
          [0, 1], clamp);
        // Skeleton pulsiert, solange es laedt
        const puls = 0.5 + Math.sin((frame - start - i * 8) / 12) * 0.22;
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: zeilenH * 0.5 }}>
            <div style={{
              width: zeilenH, height: zeilenH, borderRadius: "50%",
              background: wechsel > 0.5
                ? `${[p.akzent, "#5DCAA5", "#8FAFFF"][i % 3]}33`
                : `rgba(255,255,255,${0.06 + puls * 0.05})`,
              border: wechsel > 0.5
                ? `1px solid ${[p.akzent, "#5DCAA5", "#8FAFFF"][i % 3]}66` : "none",
              flexShrink: 0,
            }} />
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: zeilenH * 0.2 }}>
              <div style={{
                height: zeilenH * 0.3, width: `${wechsel > 0.5 ? 62 - i * 6 : 55}%`,
                borderRadius: 4,
                background: wechsel > 0.5 ? "rgba(228,242,251,0.85)"
                  : `rgba(255,255,255,${0.07 + puls * 0.06})`,
              }} />
              <div style={{
                height: zeilenH * 0.22, width: `${wechsel > 0.5 ? 40 - i * 4 : 34}%`,
                borderRadius: 4,
                background: wechsel > 0.5 ? "rgba(127,149,166,0.6)"
                  : `rgba(255,255,255,${0.05 + puls * 0.04})`,
              }} />
            </div>
          </div>
        );
      })}
    </div>
  );
};

/* ══════════════════════════════════════════════════
   HAUPTKOMPONENTE
   ══════════════════════════════════════════════════ */
export const Komponente = ({
  palette = "dunkel",
  titel = "So einfach",
  titelAkzent = "geht das.",
}) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;

  /* Verteilung ueber 9s = 540 Frames:
       0-50     Fenster + Titel
       40-120   Feld tippt sich
       130-250  Button-Zustandskette (Hover -> Klick -> Laden -> Erfolg)
       210-330  Toast
       270-420  Skeleton -> Inhalt
       430-500  Abschluss-Text
       durchgehend: Cursor, Kamera-Push                                   */

  const fensterOp = interpolate(frame, [0, 24], [0, 1], clamp);
  const fensterY = ease(frame, 0, 46, 30, 0);
  const titelOp = interpolate(frame, [10, 36], [0, 1], clamp);

  const fazitOp = interpolate(frame, [432, 468], [0, 1], clamp);
  const fazitY = ease(frame, 432, 492, 24, 0);

  const camPush = ease(frame, 0, 540, 0.98, 1.025);

  // Fensterflaeche
  const fw = W * 0.62, fh = H * 0.6;
  const fx = (W - fw) / 2, fy = H * 0.17;

  // Cursor-Pfad: zum Feld, dann zum Button
  const cursorPunkte = [
    { frame: 20,  x: fx + fw * 0.85, y: fy + fh * 0.9 },
    { frame: 46,  x: fx + fw * 0.3,  y: fy + fh * 0.3, klick: true },
    { frame: 130, x: fx + fw * 0.3,  y: fy + fh * 0.32 },
    { frame: 152, x: fx + fw * 0.66, y: fy + fh * 0.58, klick: true },
    { frame: 300, x: fx + fw * 0.66, y: fy + fh * 0.58 },
    { frame: 340, x: fx + fw * 0.88, y: fy + fh * 0.95 },
  ];

  return (
    <AbsoluteFill style={{ background: "#05070a", overflow: "hidden" }}>
      <AbsoluteFill style={{
        background: `radial-gradient(ellipse 62% 56% at 50% 42%, ${p.akzent}10 0%, transparent 62%),
                     linear-gradient(165deg, #0c131a 0%, #05070a 100%)`,
      }} />

      <AbsoluteFill style={{ transform: `scale(${camPush})` }}>
        {/* Titel */}
        <div style={{
          position: "absolute", left: fx, top: H * 0.075,
          opacity: titelOp, display: "flex", alignItems: "baseline", gap: H * 0.012,
        }}>
          <span style={{
            fontFamily: BRAND.fonts.display, fontSize: H * 0.05, fontWeight: 700,
            color: "#FFFFFF", letterSpacing: "-0.03em",
          }}>{titel}</span>
          <span style={{
            fontFamily: BRAND.fonts.akzent, fontStyle: "italic",
            fontSize: H * 0.054, fontWeight: 400, color: p.akzent,
            textShadow: `0 0 28px ${p.akzent}44`,
          }}>{titelAkzent}</span>
        </div>

        {/* App-Fenster */}
        <div style={{
          position: "absolute", left: fx, top: fy, width: fw, height: fh,
          opacity: fensterOp, transform: `translateY(${fensterY}px)`,
          borderRadius: 16,
          background: "linear-gradient(160deg, rgba(255,255,255,0.045), rgba(8,13,19,0.9))",
          border: "1px solid rgba(255,255,255,0.09)",
          backdropFilter: "blur(20px)",
          boxShadow: `0 40px 100px rgba(0,0,0,0.7), 0 0 60px ${p.akzent}0d`,
          overflow: "hidden",
        }}>
          {/* Fensterleiste */}
          <div style={{
            height: fh * 0.09, borderBottom: "1px solid rgba(255,255,255,0.06)",
            display: "flex", alignItems: "center", padding: `0 ${fw * 0.025}px`, gap: 7,
          }}>
            {["#ff5f57", "#febc2e", "#28c840"].map((c, i) => (
              <div key={i} style={{ width: 10, height: 10, borderRadius: "50%", background: c, opacity: 0.75 }} />
            ))}
            <div style={{
              flex: 1, textAlign: "center", marginRight: 40,
              fontFamily: BRAND.fonts.sans, fontSize: fh * 0.035, color: "#6f8798",
            }}>Mahnflow</div>
          </div>
        </div>

        {/* TECHNIK 3: Feld tippt sich */}
        <TippFeld frame={frame} start={48} x={fx + fw * 0.08} y={fy + fh * 0.2}
          breite={fw * 0.55} hoehe={fh * 0.11} label="RECHNUNGSNUMMER"
          text="RE-2026-0847" p={p} />

        {/* TECHNIK 2: Button-Zustandskette */}
        <ZustandsButton frame={frame} start={134}
          x={fx + fw * 0.52} y={fy + fh * 0.52}
          breite={fw * 0.34} hoehe={fh * 0.12} p={p} />

        {/* TECHNIK 5: Skeleton -> Inhalt */}
        <SkeletonListe frame={frame} start={272}
          x={fx + fw * 0.08} y={fy + fh * 0.44}
          breite={fw * 0.38} zeilenH={fh * 0.075} anzahl={3} p={p} />

        {/* TECHNIK 4: Toast */}
        <Toast frame={frame} start={214}
          x={fx + fw * 0.42} y={fy + fh * 0.82}
          breite={fw * 0.5} hoehe={fh * 0.12}
          text="Mahnung versendet" p={p} />

        {/* TECHNIK 1: Cursor */}
        <Cursor frame={frame} punkte={cursorPunkte} p={p} />

        {/* Fazit */}
        <div style={{
          position: "absolute", left: fx, top: fy + fh + H * 0.045,
          opacity: fazitOp, transform: `translateY(${fazitY}px)`,
          display: "flex", alignItems: "baseline", gap: H * 0.01,
        }}>
          <span style={{
            fontFamily: BRAND.fonts.display, fontSize: H * 0.036, fontWeight: 700,
            color: "#FFFFFF", letterSpacing: "-0.02em",
          }}>Drei Klicks —</span>
          <span style={{
            fontFamily: BRAND.fonts.akzent, fontStyle: "italic",
            fontSize: H * 0.04, fontWeight: 400, color: p.akzent,
          }}>fertig.</span>
        </div>
      </AbsoluteFill>

      <AbsoluteFill style={{
        background: "radial-gradient(ellipse at 50% 46%, transparent 54%, rgba(0,0,0,0.58) 100%)",
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
};

export default Komponente;
