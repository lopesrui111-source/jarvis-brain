import React from "react";
import { useCurrentFrame, interpolate } from "remotion";
import { EXPO } from "./motion_helpers.jsx";

// ═══ GRAFIK-BAUSTEINE fuer reichere Videos ═══
// Icons, Pillen, Mini-Karten, animierte Details — im Buroflow-Kontext.
// Alle halten die Motion-DNA (easeOutExpo, clean, dezent).

// ── Line-Icons (stroke, currentColor, viewBox 24) ──
const ICON_PATHS = {
  rechnung:  "M6 2h9l3 3v17H6zM9 8h6M9 12h6M9 16h4",
  dokument:  "M6 2h9l3 3v17H6zM9 8h6M9 12h6M9 16h4",
  mail:      "M3 6h18v12H3zM3 7l9 6 9-6",
  uhr:       "M12 7v5l3 2M12 3a9 9 0 100 18 9 9 0 000-18z",
  sanduhr:   "M6 3h12M6 21h12M8 3c0 4 8 5 8 9s-8 5-8 9M16 3c0 4-8 5-8 9s8 5 8 9",
  check:     "M4 12l5 5L20 6",
  euro:      "M15 6a6 6 0 100 12M5 10h8M5 14h8",
  warnung:   "M12 3l10 17H2zM12 9v5M12 17v.5",
  blitz:     "M13 2L4 14h6l-1 8 9-12h-6z",
  karte:     "M2 6h20v12H2zM2 10h20M6 15h4",
  glocke:    "M6 9a6 6 0 1112 0c0 5 2 7 2 7H4s2-2 2-7M10 21h4",
  kalender:  "M4 5h16v16H4zM4 9h16M8 3v4M16 3v4M8 13h3M8 17h3",
  prozent:   "M6 6h.01M18 18h.01M6 18L18 6M8 6a2 2 0 11-4 0 2 2 0 014 0zM20 18a2 2 0 11-4 0 2 2 0 014 0z",
  pfeil:     "M5 12h14M13 6l6 6-6 6",
  x:         "M6 6l12 12M18 6L6 18",
  robot:     "M7 8h10v9H7zM9 12h.01M15 12h.01M12 4v4M9 21h6M4 12h1M19 12h1",
  stapel:    "M4 8l8-4 8 4-8 4zM4 12l8 4 8-4M4 16l8 4 8-4",
};

export function Icon({ name = "check", groesse = 48, farbe = "currentColor", strich = 2, delay = 0 }) {
  const frame = useCurrentFrame();
  const op = interpolate(frame - delay, [0, 8], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const sc = interpolate(frame - delay, [0, 12], [0.7, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const d = ICON_PATHS[name] || ICON_PATHS.check;
  return (
    <svg width={groesse} height={groesse} viewBox="0 0 24 24" fill="none"
      style={{ opacity: op, transform: `scale(${sc})` }}>
      <path d={d} stroke={farbe} strokeWidth={strich} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Pille: kleines Badge mit optionalem Icon + Text (Glas-Look) ──
export function Pille({ text, icon, akzent, hell, farbe, delay = 0, groesse = 22 }) {
  const frame = useCurrentFrame();
  const op = interpolate(frame - delay, [0, 10], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(frame - delay, [0, 14], [10, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{
      opacity: op, transform: `translateY(${y}px)`,
      display: "inline-flex", alignItems: "center", gap: groesse * 0.4,
      padding: `${groesse * 0.5}px ${groesse * 0.9}px`, borderRadius: 999,
      background: hell ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.07)",
      border: `1px solid ${akzent}55`,
      backdropFilter: "blur(18px)", WebkitBackdropFilter: "blur(18px)",
      color: farbe, fontSize: groesse, fontWeight: 600, letterSpacing: "-0.01em",
    }}>
      {icon ? <Icon name={icon} groesse={groesse * 1.1} farbe={akzent} strich={2.2} delay={delay} /> : null}
      {text}
    </div>
  );
}

// ── Mini-Karte: kleines App-UI-Snippet (Titel + Zeile + Status-Icon) ──
export function MiniKarte({ titel, zeile, statusIcon = "check", statusFarbe, hell, akzent, breite = 360, delay = 0 }) {
  const frame = useCurrentFrame();
  const op = interpolate(frame - delay, [0, 10], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(frame - delay, [0, 16], [16, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const textFarbe = hell ? "#1A1D24" : "#FFFFFF";
  const subFarbe = hell ? "rgba(26,29,36,0.6)" : "rgba(255,255,255,0.6)";
  return (
    <div style={{
      opacity: op, transform: `translateY(${y}px)`,
      width: breite, padding: "18px 20px", borderRadius: 18,
      display: "flex", alignItems: "center", gap: 16,
      background: hell ? "#FFFFFF" : "rgba(255,255,255,0.06)",
      border: hell ? "none" : "1px solid rgba(255,255,255,0.12)",
      backdropFilter: hell ? "none" : "blur(20px)", WebkitBackdropFilter: hell ? "none" : "blur(20px)",
      boxShadow: hell ? "0 12px 32px rgba(0,0,0,0.12)" : "0 12px 40px rgba(0,0,0,0.3)",
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 12, flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: `${statusFarbe || akzent}22`,
      }}>
        <Icon name={statusIcon} groesse={24} farbe={statusFarbe || akzent} strich={2.4} delay={delay + 4} />
      </div>
      <div style={{ flex: 1, textAlign: "left" }}>
        <div style={{ fontSize: 22, fontWeight: 600, color: textFarbe, lineHeight: 1.2 }}>{titel}</div>
        {zeile ? <div style={{ fontSize: 17, color: subFarbe, marginTop: 3 }}>{zeile}</div> : null}
      </div>
    </div>
  );
}

// ── Haekchen, das sich zeichnet (stroke-dashoffset) ──
export function CheckZeichnen({ groesse = 90, farbe, delay = 0 }) {
  const frame = useCurrentFrame();
  const prog = interpolate(frame - delay, [0, 18], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const laenge = 40;
  return (
    <svg width={groesse} height={groesse} viewBox="0 0 48 48" fill="none">
      <circle cx="24" cy="24" r="22" stroke={farbe} strokeWidth="2" opacity="0.25" />
      <path d="M14 24l7 7 14-14" stroke={farbe} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"
        strokeDasharray={laenge} strokeDashoffset={laenge * (1 - prog)} />
    </svg>
  );
}

// ── Progress-Ring, der sich fuellt ──
export function Ring({ groesse = 120, farbe, hintergrund = "rgba(255,255,255,0.15)", prozent = 100, delay = 0, dicke = 8 }) {
  const frame = useCurrentFrame();
  const r = (groesse - dicke) / 2;
  const umfang = 2 * Math.PI * r;
  const p = interpolate(frame - delay, [0, 30], [0, prozent / 100], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <svg width={groesse} height={groesse} viewBox={`0 0 ${groesse} ${groesse}`}>
      <circle cx={groesse / 2} cy={groesse / 2} r={r} fill="none" stroke={hintergrund} strokeWidth={dicke} />
      <circle cx={groesse / 2} cy={groesse / 2} r={r} fill="none" stroke={farbe} strokeWidth={dicke}
        strokeLinecap="round" strokeDasharray={umfang} strokeDashoffset={umfang * (1 - p)}
        transform={`rotate(-90 ${groesse / 2} ${groesse / 2})`} />
    </svg>
  );
}
