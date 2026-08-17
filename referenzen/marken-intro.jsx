// marken-intro.jsx — INTRO IM SIMO-STIL, in Bueroflow-Farben
//
// Der Einstieg, wie in simo.mp4:
//   Phase 1 (0-0,7s):  Sattes Farbfeld mit weichen, wandernden Verlaeufen
//   Phase 2 (0,5-1,5s): Logo rast ins Bild — kommt MIT Bewegungsunschaerfe an,
//                       bremst ab, wird scharf, ueberschwingt minimal
//   Phase 3 (1,5-2,6s): Text fegt seitlich durch — schnell, mit Motion Blur
//   Phase 4 (2,6-3,5s): Alles zieht weiter raus, Farbe kippt ins Dunkle
//                       (Uebergabe an das Dashboard-Segment)
//
// DAS PRAEGENDE ist die BEWEGUNGSUNSCHAERFE, gekoppelt an die Geschwindigkeit:
// je schneller sich etwas bewegt, desto staerker der Blur. Dinge RASEN ins
// Bild und bremsen ab — sie blenden nicht sanft ein.
//
// props: logoText, claim, farbe ("limette" | "dunkel")

import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing, Img, staticFile } from "remotion";
import { BRAND, logoFuer } from "../brand.js";

export const meta = {
  dauerSek: 3.5,
  defaultProps: {
    logoText: "Büroflow",
    claim: "Schluss mit dem",
    claimAkzent: "Papierkram.",
  },
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

// Geschwindigkeits-gekoppelter Motion Blur:
// wir leiten die Bewegung numerisch ab und blurren proportional dazu.
function mitBlur(frameFn, frame, faktor = 0.5, max = 26) {
  const jetzt = frameFn(frame);
  const davor = frameFn(frame - 1);
  const speed = Math.abs(jetzt - davor);
  return { wert: jetzt, blur: Math.min(max, speed * faktor) };
}

export const Komponente = ({
  palette = "dunkel",
  logoText = "Büroflow",
  claim = "Schluss mit dem",
  claimAkzent = "Papierkram.",
}) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;

  /* ═══ PHASE 1: Farbfeld ═══
     Kein flaches Gruen wie bei Spotify (waere zu grell fuer die Marke),
     sondern tiefes Anthrazit mit kraeftigem, wanderndem Limette-Verlauf. */
  const glowX = 38 + Math.sin(frame / 52) * 14;
  const glowY = 44 + Math.cos(frame / 64) * 11;
  const glowStaerke = interpolate(frame, [0, 40, 150, 210], [0.5, 1, 1, 0.35], clamp);
  // Farbe kippt am Ende ins Dunkle — Uebergabe ans naechste Segment
  const abdunkeln = interpolate(frame, [156, 210], [0, 1], clamp);

  /* ═══ PHASE 2: Logo rast herein ═══ */
  const logoX = (f) => interpolate(f, [26, 62], [W * 0.42, 0],
    { easing: Easing.out(Easing.cubic), ...clamp });
  const logoScale = (f) => interpolate(f, [26, 68], [1.5, 1],
    { easing: Easing.out(Easing.cubic), ...clamp });
  const lx = mitBlur(logoX, frame, 0.34);
  const lsc = logoScale(frame);
  const logoOp = interpolate(frame, [24, 40], [0, 1], clamp);
  // minimales Nachschwingen, damit es nicht tot stehen bleibt
  const logoNach = Math.sin(Math.max(0, frame - 68) / 26) * 1.6;
  // Logo verlaesst das Bild am Ende wieder
  const logoRaus = interpolate(frame, [150, 200], [0, -W * 0.5],
    { easing: Easing.in(Easing.cubic), ...clamp });
  const logoRausBlur = interpolate(frame, [150, 176], [0, 20], clamp);

  /* ═══ PHASE 3: Text legt sich per Maske frei (links -> rechts) ═══ */
  const reveal = interpolate(frame, [88, 142], [0, 1],
    { easing: Easing.inOut(Easing.cubic), ...clamp });
  const textOp = interpolate(frame, [86, 96], [0, 1], clamp);

  /* Gruppen-Choreografie: sobald der Text erscheint, oeffnet sich die Gruppe
     (Abstand waechst) und das Logo rueckt nach hinten. Beide bewegen sich
     dadurch als EINE Einheit statt als zwei getrennte Elemente. */
  const gruppeOeffnen = interpolate(frame, [84, 140], [0, 1],
    { easing: Easing.inOut(Easing.cubic), ...clamp });
  // die ganze Gruppe hebt sich dabei leicht an
  const gruppeY = interpolate(frame, [84, 150], [0, -H * 0.03],
    { easing: Easing.inOut(Easing.cubic), ...clamp });

  /* ═══ Licht-Sweep, der ueber alles laeuft ═══ */
  const sweep = interpolate(frame, [58, 118], [-30, 130],
    { easing: Easing.inOut(Easing.cubic), ...clamp });

  const logoGroesse = H * 0.115;

  return (
    <AbsoluteFill style={{ background: "#0a0d11", overflow: "hidden" }}>

      {/* ── Farbfeld: tiefer Grund + wandernder Marken-Glow ── */}
      <AbsoluteFill style={{
        background: `
          radial-gradient(ellipse 70% 80% at ${glowX}% ${glowY}%,
            ${p.akzent}${Math.round(glowStaerke * 58).toString(16).padStart(2, "0")} 0%,
            ${p.akzent}1e 34%, transparent 68%),
          radial-gradient(ellipse 60% 70% at ${100 - glowX}% ${100 - glowY * 0.7}%,
            #5DCAA5${Math.round(glowStaerke * 30).toString(16).padStart(2, "0")} 0%, transparent 58%),
          linear-gradient(155deg, #101821 0%, #070a0e 100%)`,
      }} />
      {/* Feine Textur, damit die Flaeche nicht steril wirkt */}
      <AbsoluteFill style={{
        opacity: 0.045,
        backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)'/%3E%3C/svg%3E\")",
      }} />

      {/* ── LOGO + TEXT als EINE Einheit ──
          Nicht mehr starr untereinander: das Logo kommt zuerst mittig gross,
          und sobald der Text sich freilegt, RUECKT ES NACH HINTEN (kleiner,
          leicht nach oben, etwas transparenter). Beide bewegen sich als
          zusammenhaengende Gruppe — dadurch wirkt es wie eine Choreografie
          statt wie zwei getrennte Elemente. */}
      <AbsoluteFill style={{
        justifyContent: "center", alignItems: "center",
        perspective: `${W}px`,
      }}>
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: H * (0.03 + gruppeOeffnen * 0.045),
          transform: `translateX(${logoRaus}px) translateY(${gruppeY}px)`,
          filter: logoRausBlur > 0.5 ? `blur(${logoRausBlur.toFixed(1)}px)` : "none",
          transformStyle: "preserve-3d",
        }}>

          {/* Logo — rueckt beim Textauftritt nach hinten */}
          <div style={{
            opacity: logoOp * (1 - gruppeOeffnen * 0.22),
            transform: `translateX(${lx.wert}px) translateY(${logoNach}px) ` +
                       `scale(${lsc * (1 - gruppeOeffnen * 0.26)}) ` +
                       `translateZ(${-gruppeOeffnen * 120}px)`,
            filter: lx.blur > 0.5 ? `blur(${lx.blur.toFixed(1)}px)` : "none",
            willChange: "transform, filter",
          }}>
            <Img src={staticFile(logoFuer(palette))}
              style={{ height: logoGroesse, filter: `drop-shadow(0 0 34px ${p.akzent}55)` }} />
          </div>

          {/* Claim — legt sich per Maske von links nach rechts frei.
              TYPOGRAFIE: Hauptteil in kraeftiger Sans, das betonte Wort in
              eleganter kursiver Serif und Akzentfarbe. Diese Mischung ist
              der schnellste Weg von "selbstgebaut" zu "professionell". */}
          <div style={{ position: "relative", opacity: textOp }}>
            <div style={{
              display: "flex", alignItems: "baseline", gap: H * 0.016,
              whiteSpace: "nowrap",
              WebkitMaskImage: `linear-gradient(90deg, #000 0%, #000 ${reveal * 100}%,
                                transparent ${Math.min(100, reveal * 100 + 4)}%, transparent 100%)`,
              maskImage: `linear-gradient(90deg, #000 0%, #000 ${reveal * 100}%,
                          transparent ${Math.min(100, reveal * 100 + 4)}%, transparent 100%)`,
            }}>
              <span style={{
                fontFamily: BRAND.fonts.display,
                fontSize: H * 0.062, fontWeight: 700,
                color: "#FFFFFF", letterSpacing: "-0.03em",
                textShadow: "0 4px 40px rgba(0,0,0,0.7)",
              }}>{claim}</span>
              <span style={{
                fontFamily: BRAND.fonts.akzent,
                fontStyle: "italic",
                fontSize: H * 0.066,           // Serif wirkt optisch kleiner
                fontWeight: 400,
                color: p.akzent, letterSpacing: "-0.01em",
                textShadow: `0 0 34px ${p.akzent}44, 0 4px 40px rgba(0,0,0,0.7)`,
              }}>{claimAkzent}</span>
            </div>
            {reveal > 0.01 && reveal < 0.99 && (
              <div style={{
                position: "absolute", top: "-12%", bottom: "-12%",
                left: `${reveal * 100}%`, width: 3,
                background: `linear-gradient(180deg, transparent, ${p.akzent}, transparent)`,
                boxShadow: `0 0 22px ${p.akzent}, 0 0 46px ${p.akzent}88`,
              }} />
            )}
          </div>
        </div>
      </AbsoluteFill>

      {/* ── Licht-Sweep ── */}
      <div style={{
        position: "absolute", top: "-25%", left: `${sweep}%`,
        width: "22%", height: "150%",
        background: `linear-gradient(102deg, transparent, ${p.akzent}26, #ffffff1c, transparent)`,
        transform: "skewX(-16deg)", filter: "blur(16px)", pointerEvents: "none",
      }} />

      {/* ── Abdunkeln am Ende: Uebergabe ans naechste Segment ── */}
      <AbsoluteFill style={{
        background: "#04060a", opacity: abdunkeln, pointerEvents: "none",
      }} />

      {/* ── Vignette ── */}
      <AbsoluteFill style={{
        background: "radial-gradient(ellipse at 50% 50%, transparent 42%, rgba(0,0,0,0.6) 100%)",
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
};

export default Komponente;
