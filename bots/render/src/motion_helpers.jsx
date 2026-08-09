import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { BRAND } from "./brand.js";

// ═══ MOTION-DNA aus den Referenzen (simo, thednyx, ref3) ═══
// - easeOutExpo als EINZIGE Kurve (kein Bounce/Elastic)
// - Text: Fade + 8-12px Y-Drift + Blur-Dissolve, als Block
// - Text sitzt IMMER auf Surface (Glas oder Card), nie nackt
// - metronomischer Takt, harte Cuts, 1 Pivot-Moment pro Video
// - max. 2 Dekor-Elemente, subtiler Scale-Push als "Kamera"

export const EXPO = Easing.out(Easing.exp);

// Text-Block: erscheint mit Fade + Y-Drift + Blur-Aufloesung (easeOutExpo)
export function TextBlock({ text, groesse, farbe, gewicht = 600, glow, delay = 0, blur = true }) {
  const frame = useCurrentFrame();
  const f = frame - delay;
  const op = interpolate(f, [0, 12], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(f, [0, 16], [10, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const b = blur ? interpolate(f, [0, 14], [8, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  return (
    <div style={{
      opacity: op, transform: `translateY(${y}px)`, filter: b ? `blur(${b}px)` : "none",
      fontSize: groesse, fontWeight: gewicht, color: farbe,
      textShadow: glow ? `0 0 30px ${glow}` : "none",
      textAlign: "center", lineHeight: 1.15, letterSpacing: "-0.02em",
      fontFamily: BRAND.fonts.display,
    }}>{text}</div>
  );
}

// Surface: Glas ODER Material-Card (waehlbar) — Text sitzt immer darauf
export function Surface({ children, art = "glas", akzent, hell, breite, padding }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Surface fadet leicht VOR dem Text ein (zweistufiges Staging)
  const op = interpolate(frame, [0, 8], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(frame, [0, 12], [14, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const glas = {
    background: hell ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.06)",
    border: `1px solid ${hell ? "rgba(255,255,255,0.7)" : "rgba(255,255,255,0.14)"}`,
    backdropFilter: "blur(22px)", WebkitBackdropFilter: "blur(22px)",
    boxShadow: `0 20px 60px rgba(0,0,0,0.35), inset 0 1px 1px ${hell ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.15)"}, 0 0 50px ${akzent}22`,
  };
  const card = {
    background: hell ? "#FFFFFF" : "#15171b",
    border: "none",
    boxShadow: `0 24px 60px rgba(0,0,0,${hell ? 0.14 : 0.5}), 0 4px 12px rgba(0,0,0,0.2)`,
  };
  const stil = art === "card" ? card : glas;

  return (
    <div style={{
      opacity: op, transform: `translateY(${y}px)`,
      width: breite, padding: padding, borderRadius: 24, position: "relative",
      ...stil,
    }}>
      {art === "glas" && (
        <div style={{ position: "absolute", top: 0, left: "12%", right: "12%", height: 1,
          background: `linear-gradient(90deg, transparent, ${akzent}, transparent)`, opacity: 0.7 }} />
      )}
      {children}
    </div>
  );
}

// subtiler Scale-Push als "Kamera" (1.0 -> 1.03 ueber die Segmentdauer)
export function useKameraPush(dauerFrames) {
  const frame = useCurrentFrame();
  return interpolate(frame, [0, dauerFrames], [1.0, 1.03], { easing: Easing.out(Easing.ease), extrapolateRight: "clamp" });
}

// Pivot-Flash-Overlay (Luminance-Flash) — nur an dramatischen Momenten
export function FlashOverlay({ farbe = "#FFFFFF" }) {
  const frame = useCurrentFrame();
  const op = interpolate(frame, [0, 3, 9], [0, 0.85, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  if (op <= 0.001) return null;
  return <div style={{ position: "absolute", inset: 0, background: farbe, opacity: op, zIndex: 30, pointerEvents: "none" }} />;
}

// globaler Hintergrund: 1 wandernder Blob + dezenter Radial (max 2 Dekor, clean)
export function StoryHintergrund({ p }) {
  const frame = useCurrentFrame();
  const bx = interpolate(Math.sin(frame / 55), [-1, 1], [25, 70]);
  const by = interpolate(Math.cos(frame / 68), [-1, 1], [28, 62]);
  return (
    <>
      <div style={{ position: "absolute", inset: 0, background: p.hintergrund }} />
      <div style={{
        position: "absolute", width: "90%", height: "60%",
        top: `${by - 25}%`, left: `${bx - 45}%`,
        background: `radial-gradient(circle, ${p.akzent}22 0%, transparent 60%)`,
        filter: "blur(40px)", pointerEvents: "none",
      }} />
    </>
  );
}
