// reveal.jsx — DASHBOARD-REVEAL mit Kamerafahrt
//
// WICHTIGE LEHRE aus den Fehlversuchen: DashboardVideo skaliert sich INTERN
// selbst auf die Kompositionsgroesse. Sobald man die Komponente in einen
// transformierten Wrapper steckt, kommt diese Transformation ZUSAETZLICH
// obendrauf — das Dashboard lief dadurch aus dem Bild (abgeschnittenes
// "Büroflow", fehlende vierte KPI-Karte).
//
// LOESUNG HIER: Die Kamerafahrt wirkt auf einen AEUSSEREN Wrapper, der die
// volle Bildflaeche hat, mit overflow:hidden auf der obersten Ebene. Die
// Dashboard-Komponente selbst bleibt unangetastet und behaelt ihre eigene
// Einpassung.
//
// ABLAUF:
//   0,0-1,0s: Dashboard kommt herein (leicht geneigt, unscharf -> scharf)
//   1,1-1,9s: Die vier KPI-Karten erscheinen EINZELN (Timing steckt in
//             dashboard-video.jsx: Frame 67/83/98/114)
//   2,8s:     Chart zeichnet sich, Donut fuellt sich
//   ab 4,5s:  Kamera richtet sich vollends auf, Text erscheint
//
// props: titel, untertitel

import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { BRAND } from "../brand.js";
import DashboardVideo from "./dashboard-video.jsx";

export const meta = {
  dauerSek: 8,
  defaultProps: { titel: "Dein Büroalltag", untertitel: "auf einen Blick" },
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };
const smooth = (t) => t * t * (3 - 2 * t);
const ease = (frame, von, bis, a, b) => {
  const t = interpolate(frame, [von, bis], [0, 1], clamp);
  return a + (b - a) * smooth(t);
};

export const Komponente = ({
  palette = "dunkel",
  titel = "Dein Büroalltag",
  untertitel = "auf einen Blick",
}) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;

  /* ── ANKUNFT: Dashboard kommt herein ── */
  const ankOp = interpolate(frame, [0, 26], [0, 1], clamp);
  const ankY = ease(frame, 0, 56, 46, 0);
  const ankBlur = interpolate(frame, [0, 34], [13, 0], clamp);
  const ankScale = ease(frame, 0, 60, 0.965, 1);

  /* ── KAMERAFAHRT: sehr zurueckhaltend ──
     Nur leichte Neigung, die sich aufrichtet. Der Zoom bleibt UNTER 1,
     damit das Dashboard garantiert nie ueber den Bildrand laeuft. */
  const rotY = ease(frame, 0, 400, -9, -1.2);
  const rotX = ease(frame, 0, 400, 4.5, 0.6);
  const zoomK = ease(frame, 0, 400, 0.93, 0.985) + frame * 0.00002;

  /* ── TEXT: erst wenn das Dashboard steht ── */
  const tOp = interpolate(frame, [270, 310], [0, 1], clamp);
  const tY = ease(frame, 270, 330, 26, 0);
  const sOp = interpolate(frame, [292, 332], [0, 1], clamp);
  const sY = ease(frame, 292, 352, 20, 0);
  // Textzone abdunkeln, damit die Schrift lesbar bleibt
  const zoneOp = interpolate(frame, [262, 300], [0, 1], clamp);

  /* ── Licht-Sweep beim Kartenauftritt ── */
  const sweep = interpolate(frame, [60, 130], [-25, 125],
    { easing: Easing.inOut(Easing.cubic), ...clamp });

  return (
    <AbsoluteFill style={{ background: "#04060a", overflow: "hidden" }}>

      {/* Hintergrund-Glow */}
      <AbsoluteFill style={{
        background: `radial-gradient(ellipse 70% 60% at ${46 + Math.sin(frame / 150) * 6}% 40%,
                     ${p.akzent}10 0%, transparent 60%)`,
      }} />

      {/* ── DASHBOARD mit Kamerafahrt ──
          Die Transformation sitzt auf einem Wrapper mit voller Bildflaeche.
          DashboardVideo darin behaelt seine eigene Einpassung. */}
      <AbsoluteFill style={{ perspective: `${W * 2.2}px`, perspectiveOrigin: "50% 45%" }}>
        <div style={{
          position: "absolute", inset: 0,
          opacity: ankOp,
          transform: `translateY(${ankY}px) scale(${ankScale * zoomK}) ` +
                     `rotateY(${rotY}deg) rotateX(${rotX}deg)`,
          filter: ankBlur > 0.4 ? `blur(${ankBlur.toFixed(1)}px)` : "none",
          transformStyle: "preserve-3d",
        }}>
          <DashboardVideo palette={palette} />
        </div>
      </AbsoluteFill>

      {/* Licht-Sweep, laeuft waehrend die Karten kommen */}
      <div style={{
        position: "absolute", top: "-20%", left: `${sweep}%`,
        width: "16%", height: "140%",
        background: `linear-gradient(100deg, transparent, ${p.akzent}18, #ffffff10, transparent)`,
        transform: "skewX(-14deg)", filter: "blur(14px)", pointerEvents: "none",
      }} />

      {/* Vignette */}
      <AbsoluteFill style={{
        background: "radial-gradient(ellipse at 50% 46%, transparent 52%, rgba(0,0,0,0.6) 100%)",
        pointerEvents: "none",
      }} />

      {/* ── TEXT unten, mit abgedunkelter Zone fuer Lesbarkeit ── */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0, height: "34%",
        background: "linear-gradient(180deg, transparent, rgba(2,4,7,0.82) 46%, rgba(2,4,7,0.94))",
        opacity: zoneOp, pointerEvents: "none",
      }} />
      <AbsoluteFill style={{
        justifyContent: "flex-end", alignItems: "flex-start",
        padding: `0 0 ${H * 0.07}px ${W * 0.07}px`, pointerEvents: "none",
      }}>
        <div style={{
          opacity: tOp, transform: `translateY(${tY}px)`,
          fontFamily: BRAND.fonts.display, fontSize: H * 0.058, fontWeight: 700,
          color: "#FFFFFF", letterSpacing: "-0.028em", lineHeight: 1.06,
        }}>{titel}</div>
        <div style={{
          opacity: sOp, transform: `translateY(${sY}px)`,
          fontFamily: BRAND.fonts.display, fontSize: H * 0.058, fontWeight: 700,
          color: p.akzent, letterSpacing: "-0.028em", lineHeight: 1.06,
          textShadow: `0 0 ${34 * sOp}px ${p.akzent}44`,
        }}>{untertitel}</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export default Komponente;
