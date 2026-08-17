// infografik-pro.jsx — REFERENZ: DATEN IN BEWEGUNG
//
// Lehrmaterial fuer die Kategorie "Infografik-Animation". Zeigt vier
// Techniken, die man immer wieder braucht — als lesbares Vorbild, NICHT
// als fertiger Baukasten. Baue eigene Varianten nach diesen Prinzipien.
//
// DIE VIER TECHNIKEN:
//
// 1) ZAHL, DIE HOCHZAEHLT — mit Ease-Out, damit sie am Ende "ankommt"
//    statt linear durchzurattern. Dazu ein kurzer Scale-Puls beim Erreichen
//    des Zielwerts (der Moment, an dem das Auge hinschaut).
//
// 2) BALKEN, DIE WACHSEN — gestaffelt, nicht gleichzeitig. Jeder Balken
//    startet 4-6 Frames nach dem vorherigen. Der Hoechstwert bekommt eine
//    andere Farbe und einen Glow — so entsteht eine Aussage statt nur Daten.
//
// 3) VERGLEICH VORHER/NACHHER — die eigentliche Botschaft. Zwei Werte,
//    ein Pfeil dazwischen. Der schlechte Wert schrumpft, der gute waechst.
//    Das ist Storytelling mit Zahlen.
//
// 4) RING, DER SICH FUELLT — strokeDasharray-Trick. Der Umfang wird als
//    Dasharray gesetzt, der Dashoffset animiert von voll auf null.
//
// Alle vier haben gemeinsam: nach dem Eintritt geht die Bewegung WEITER
// (Puls, Drift, Sweep), und die Ereignisse sind ueber die volle Dauer
// verteilt — kein Stillstand in der zweiten Haelfte.

import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { BRAND } from "../brand.js";

export const meta = {
  dauerSek: 8,
  defaultProps: {
    titel: "Deine Zeit",
    titelAkzent: "zurück.",
    vorher: 15,
    nachher: 3,
  },
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };
const smooth = (t) => t * t * (3 - 2 * t);
const ease = (f, von, bis, a, b) => {
  const t = interpolate(f, [von, bis], [0, 1], clamp);
  return a + (b - a) * smooth(t);
};

/* ══════════════════════════════════════════════════
   TECHNIK 1: Zahl, die hochzaehlt
   ══════════════════════════════════════════════════ */
const ZaehlZahl = ({ frame, start, ziel, suffix = "", groesse, farbe, p }) => {
  // Ease-Out: schnell anfangen, sanft ankommen. Linear wirkt mechanisch.
  const wert = interpolate(frame, [start, start + 70], [0, ziel],
    { easing: Easing.out(Easing.cubic), ...clamp });
  // Puls genau im Moment des Ankommens — lenkt das Auge dorthin
  const ankunftPuls = interpolate(frame, [start + 66, start + 74, start + 88],
    [1, 1.07, 1], clamp);
  // danach ruhiges Weiteratmen
  const leben = Math.max(0, frame - (start + 90));
  const atem = 1 + Math.sin(leben / 30) * 0.012;
  const glow = 0.5 + Math.sin(leben / 30) * 0.35;
  const op = interpolate(frame, [start, start + 16], [0, 1], clamp);
  return (
    <span style={{
      fontFamily: BRAND.fonts.display, fontSize: groesse, fontWeight: 700,
      color: farbe, letterSpacing: "-0.04em", lineHeight: 1,
      opacity: op,
      display: "inline-block",
      transform: `scale(${ankunftPuls * atem})`,
      textShadow: `0 0 ${34 * glow}px ${farbe}66`,
    }}>{Math.round(wert)}{suffix}</span>
  );
};

/* ══════════════════════════════════════════════════
   TECHNIK 2: Balken, die gestaffelt wachsen
   ══════════════════════════════════════════════════ */
const BalkenGruppe = ({ frame, start, werte, hoehe, breite, p }) => {
  const maxWert = Math.max(...werte);
  const maxIdx = werte.indexOf(maxWert);
  return (
    <div style={{
      display: "flex", alignItems: "flex-end", gap: breite * 0.035,
      height: hoehe, width: breite,
    }}>
      {werte.map((v, i) => {
        // GESTAFFELT: jeder Balken startet spaeter als der vorherige
        const s = start + i * 5;
        const h = interpolate(frame, [s, s + 34], [0.04, v / maxWert],
          { easing: Easing.out(Easing.cubic), ...clamp });
        const istMax = i === maxIdx;
        // Der Hoechstwert lebt weiter — er traegt die Aussage
        const leben = Math.max(0, frame - (s + 40));
        const puls = istMax ? 1 + Math.sin(leben / 26) * 0.03 : 1;
        const glow = istMax ? 0.5 + Math.sin(leben / 26) * 0.4 : 0;
        return (
          <div key={i} style={{
            flex: 1, height: `${h * 100}%`,
            borderRadius: 4,
            background: istMax
              ? `linear-gradient(180deg, ${p.akzent}, ${p.akzent}aa)`
              : "linear-gradient(180deg, rgba(255,255,255,0.16), rgba(255,255,255,0.06))",
            transform: `scaleY(${puls})`, transformOrigin: "bottom",
            boxShadow: istMax ? `0 0 ${22 * glow}px ${p.akzent}88` : "none",
          }} />
        );
      })}
    </div>
  );
};

/* ══════════════════════════════════════════════════
   TECHNIK 4: Ring, der sich fuellt
   ══════════════════════════════════════════════════ */
const FuellRing = ({ frame, start, prozent, groesse, farbe }) => {
  const r = 42, umfang = 2 * Math.PI * r;
  const fuell = interpolate(frame, [start, start + 62], [0, prozent / 100],
    { easing: Easing.out(Easing.cubic), ...clamp });
  const op = interpolate(frame, [start, start + 18], [0, 1], clamp);
  const leben = Math.max(0, frame - (start + 66));
  const glow = 0.4 + Math.sin(leben / 32) * 0.35;
  return (
    <svg viewBox="0 0 100 100" style={{ width: groesse, height: groesse, opacity: op }}>
      <circle cx="50" cy="50" r={r} fill="none"
        stroke="rgba(255,255,255,0.08)" strokeWidth="7" />
      <circle cx="50" cy="50" r={r} fill="none"
        stroke={farbe} strokeWidth="7" strokeLinecap="round"
        strokeDasharray={umfang}
        strokeDashoffset={umfang * (1 - fuell)}
        transform="rotate(-90 50 50)"
        style={{ filter: `drop-shadow(0 0 ${7 * glow}px ${farbe})` }} />
    </svg>
  );
};

/* ══════════════════════════════════════════════════
   HAUPTKOMPONENTE
   ══════════════════════════════════════════════════ */
export const Komponente = ({
  palette = "dunkel",
  titel = "Deine Zeit",
  titelAkzent = "zurück.",
  vorher = 15,
  nachher = 3,
}) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;

  /* Ereignisse ueber die VOLLE Dauer (8s = 480 Frames) verteilt:
       0-60    Titel
       50-140  Vergleich vorher/nachher
       150-250 Balken
       240-330 Ring
       340-420 Fazit-Zahl
       durchgehend: Kamera-Push, Sweeps                                   */

  const titelOp = interpolate(frame, [4, 30], [0, 1], clamp);
  const titelY = ease(frame, 4, 44, 28, 0);

  // TECHNIK 3: Vergleich — der schlechte Wert schrumpft, der gute waechst
  const vergleichOp = interpolate(frame, [54, 84], [0, 1], clamp);
  const vorherScale = ease(frame, 84, 140, 1, 0.72);   // schrumpft
  const vorherOp = ease(frame, 84, 140, 1, 0.45);
  const nachherScale = ease(frame, 96, 152, 0.8, 1.14); // waechst
  const pfeilZeichnung = interpolate(frame, [88, 130], [0, 1],
    { easing: Easing.inOut(Easing.cubic), ...clamp });

  const balkenOp = interpolate(frame, [148, 176], [0, 1], clamp);
  const ringOp = interpolate(frame, [238, 266], [0, 1], clamp);
  const fazitOp = interpolate(frame, [338, 372], [0, 1], clamp);
  const fazitY = ease(frame, 338, 396, 26, 0);

  // durchgehende Kamera — nichts steht je still
  const camPush = ease(frame, 0, 480, 0.97, 1.03);
  const camDrift = interpolate(frame, [0, 480], [0, -H * 0.012], clamp);
  // zwei Sweeps, zeitlich versetzt
  const sweep1 = interpolate(frame, [130, 200], [-25, 125],
    { easing: Easing.inOut(Easing.cubic), ...clamp });
  const sweep2 = interpolate(frame, [330, 420], [-25, 125],
    { easing: Easing.inOut(Easing.cubic), ...clamp });

  const zahlGroesse = H * 0.15;

  return (
    <AbsoluteFill style={{ background: "#05070a", overflow: "hidden" }}>

      {/* Hintergrund */}
      <AbsoluteFill style={{
        background: `radial-gradient(ellipse 66% 60% at ${48 + Math.sin(frame / 120) * 6}% 44%,
                     ${p.akzent}12 0%, transparent 62%),
                     linear-gradient(165deg, #0c131a 0%, #05070a 100%)`,
      }} />

      <AbsoluteFill style={{
        transform: `scale(${camPush}) translateY(${camDrift}px)`,
        justifyContent: "center", alignItems: "center",
        flexDirection: "column", gap: H * 0.045,
        padding: `0 ${W * 0.09}px`,
      }}>

        {/* Titel in Sans/Serif-Mischung */}
        <div style={{
          opacity: titelOp, transform: `translateY(${titelY}px)`,
          display: "flex", alignItems: "baseline", gap: H * 0.014,
        }}>
          <span style={{
            fontFamily: BRAND.fonts.display, fontSize: H * 0.058, fontWeight: 700,
            color: "#FFFFFF", letterSpacing: "-0.03em",
          }}>{titel}</span>
          <span style={{
            fontFamily: BRAND.fonts.akzent, fontStyle: "italic",
            fontSize: H * 0.062, fontWeight: 400, color: p.akzent,
            textShadow: `0 0 30px ${p.akzent}44`,
          }}>{titelAkzent}</span>
        </div>

        {/* TECHNIK 3: Vergleich vorher -> nachher */}
        <div style={{
          opacity: vergleichOp,
          display: "flex", alignItems: "center", gap: W * 0.045,
        }}>
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
            transform: `scale(${vorherScale})`, opacity: vorherOp,
          }}>
            <ZaehlZahl frame={frame} start={58} ziel={vorher} suffix="h"
              groesse={zahlGroesse} farbe="#ff7b7b" p={p} />
            <span style={{
              fontFamily: BRAND.fonts.sans, fontSize: H * 0.026,
              color: "#8fa3b3", letterSpacing: "0.14em",
            }}>OHNE BÜROFLOW</span>
          </div>

          {/* Pfeil zeichnet sich */}
          <svg width={W * 0.09} height={H * 0.06} style={{ overflow: "visible" }}>
            <line x1="0" y1="50%" x2="100%" y2="50%"
              stroke={p.akzent} strokeWidth="3" strokeLinecap="round"
              strokeDasharray={W * 0.09}
              strokeDashoffset={W * 0.09 * (1 - pfeilZeichnung)}
              style={{ filter: `drop-shadow(0 0 8px ${p.akzent})` }} />
            <polyline points={`${W * 0.09 - 14},${H * 0.03 - 9} ${W * 0.09},${H * 0.03} ${W * 0.09 - 14},${H * 0.03 + 9}`}
              fill="none" stroke={p.akzent} strokeWidth="3"
              strokeLinecap="round" strokeLinejoin="round"
              opacity={interpolate(pfeilZeichnung, [0.75, 1], [0, 1], clamp)} />
          </svg>

          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
            transform: `scale(${nachherScale})`,
          }}>
            <ZaehlZahl frame={frame} start={96} ziel={nachher} suffix="h"
              groesse={zahlGroesse} farbe={p.akzent} p={p} />
            <span style={{
              fontFamily: BRAND.fonts.sans, fontSize: H * 0.026,
              color: p.akzent, letterSpacing: "0.14em",
            }}>MIT BÜROFLOW</span>
          </div>
        </div>

        {/* TECHNIK 2 + 4: Balken und Ring nebeneinander */}
        <div style={{
          display: "flex", alignItems: "flex-end", gap: W * 0.06,
          marginTop: H * 0.01,
        }}>
          <div style={{ opacity: balkenOp, display: "flex", flexDirection: "column", gap: 10 }}>
            <span style={{
              fontFamily: BRAND.fonts.sans, fontSize: H * 0.022,
              color: "#7f95a6", letterSpacing: "0.16em",
            }}>STUNDEN PRO MONAT</span>
            <BalkenGruppe frame={frame} start={152}
              werte={[8, 11, 7, 13, 9, 15, 10]}
              hoehe={H * 0.16} breite={W * 0.3} p={p} />
          </div>

          <div style={{ opacity: ringOp, display: "flex", alignItems: "center", gap: W * 0.014 }}>
            <FuellRing frame={frame} start={242} prozent={80}
              groesse={H * 0.17} farbe={p.akzent} />
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{
                fontFamily: BRAND.fonts.display, fontSize: H * 0.05, fontWeight: 700,
                color: "#FFFFFF", letterSpacing: "-0.03em", lineHeight: 1,
              }}>80%</span>
              <span style={{
                fontFamily: BRAND.fonts.sans, fontSize: H * 0.022,
                color: "#7f95a6", letterSpacing: "0.1em",
              }}>weniger Aufwand</span>
            </div>
          </div>
        </div>

        {/* Fazit */}
        <div style={{
          opacity: fazitOp, transform: `translateY(${fazitY}px)`,
          display: "flex", alignItems: "baseline", gap: H * 0.012,
          marginTop: H * 0.015,
        }}>
          <span style={{
            fontFamily: BRAND.fonts.display, fontSize: H * 0.042, fontWeight: 700,
            color: "#FFFFFF", letterSpacing: "-0.02em",
          }}>Das sind</span>
          <ZaehlZahl frame={frame} start={352} ziel={144} suffix="h"
            groesse={H * 0.058} farbe={p.akzent} p={p} />
          <span style={{
            fontFamily: BRAND.fonts.akzent, fontStyle: "italic",
            fontSize: H * 0.046, fontWeight: 400, color: p.akzent,
          }}>pro Jahr.</span>
        </div>
      </AbsoluteFill>

      {/* Zwei zeitversetzte Sweeps */}
      {[sweep1, sweep2].map((s, i) => (
        <div key={i} style={{
          position: "absolute", top: "-20%", left: `${s}%`,
          width: "15%", height: "140%",
          background: `linear-gradient(100deg, transparent, ${p.akzent}1a, #ffffff10, transparent)`,
          transform: "skewX(-15deg)", filter: "blur(14px)", pointerEvents: "none",
        }} />
      ))}

      <AbsoluteFill style={{
        background: "radial-gradient(ellipse at 50% 48%, transparent 52%, rgba(0,0,0,0.6) 100%)",
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
};

export default Komponente;
