// mahnflow-motion.jsx — ECHTES MAHNFLOW-UI, FLEX-LAYOUT
//
// WICHTIGE LEHRE aus den Fehlversuchen: Absolute Pixelpositionen fuer jedes
// Element fuehren zu Ueberlappungen, sobald Text umbricht oder mehr Chips
// dazukommen. Diese Fassung nutzt echtes Flex-Layout — die Abstaende ergeben
// sich aus dem Fluss, nichts kann mehr uebereinanderliegen.
//
// Fuer den Cursor werden nur die WENIGEN Klickziele als Anteil der jeweiligen
// Spalte berechnet (siehe ziel()). Das ist robust, weil es sich an denselben
// Werten orientiert, die auch das Layout bestimmen.
//
// Alle Inhalte 1:1 aus components/dashboard/flow-view.tsx.

import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { BRAND } from "../brand.js";

export const meta = {
  dauerSek: 13,
  defaultProps: { titel: "Mahnung schreiben?", titelAkzent: "In 20 Sekunden." },
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };
const smooth = (t) => t * t * (3 - 2 * t);
const ease = (f, von, bis, a, b) => {
  const t = interpolate(f, [von, bis], [0, 1], clamp);
  return a + (b - a) * smooth(t);
};

const ACCENT = "#ef4444";
const MARKE = "#5DCAA5";

export const Komponente = ({
  palette = "dunkel",
  titel = "Mahnung schreiben?",
  titelAkzent = "In 20 Sekunden.",
}) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const F_D = BRAND.fonts.display, F_S = BRAND.fonts.sans;

  /* ═══ Fenster ═══ */
  const fw = W * 0.88, fh = H * 0.76;
  const fx = (W - fw) / 2, fy = H * 0.115;
  const kopfH = fh * 0.055;
  const S = fh / 820;                      // Skalierung
  const px = (n) => n * S * 1.5;           // Schriftgroessen
  const sp = (n) => n * S;                 // Abstaende

  // Spaltenbreiten
  const cListe = fw * 0.21, cForm = fw * 0.35, cVor = fw - cListe - cForm;
  const inhaltY = fy + kopfH;
  const inhaltH = fh - kopfH;

  /* ═══ KLICKZIELE — als Anteil der Spalten berechnet ═══
     Nur diese wenigen Werte sind "haendisch". Weil sie sich an denselben
     Spaltenmassen orientieren wie das Layout, bleiben sie korrekt. */
  const formX = fx + cListe, formPad = sp(20);
  const formInnenB = cForm - formPad * 2;
  // vertikale Positionen im Formular (Reihenfolge = Flex-Fluss)
  const yKopf = inhaltY + sp(20);
  const yVorlLabel = yKopf + sp(62);   // Kopfblock ist hoeher als geschaetzt
  const yVorlTabs = yVorlLabel + sp(20);
  const hVorlTabs = sp(32);
  const yFeld1 = yVorlTabs + hVorlTabs + sp(30);
  const hFeldBlock = sp(62);   // Label + Feld + gap sp(16)              // Label + Feld + Abstand
  const hFeld = sp(34);
  const yKnopf = yFeld1 + hFeldBlock * 4 + sp(14);
  const hKnopf = sp(42);

  const ziel = (nr) => ({
    x: formX + formPad + formInnenB * (nr === 0 ? 0.85 : nr === 5 ? 0.5 : 0.9),
    y: nr === 0 ? yVorlTabs + hVorlTabs / 2
      : nr === 5 ? yKnopf + hKnopf / 2
      : yFeld1 + hFeldBlock * (nr - 1) + sp(20) + hFeld / 2,
  });
  const zielVorl3 = { x: formX + formPad + formInnenB * 0.85, y: yVorlTabs + hVorlTabs / 2 };
  const zielEmpf = { x: formX + formPad + formInnenB * 0.9, y: yFeld1 + sp(20) + hFeld / 2 };
  const zielDrop = { x: formX + formPad + formInnenB * 0.35, y: yFeld1 + sp(20) + hFeld + sp(30) };
  const zielRech = { x: formX + formPad + formInnenB * 0.5, y: yFeld1 + hFeldBlock + sp(20) + hFeld / 2 };
  const zielBetr = { x: formX + formPad + formInnenB * 0.5, y: yFeld1 + hFeldBlock * 2 + sp(20) + hFeld / 2 };
  const zielKnopf = { x: formX + formPad + formInnenB * 0.5, y: yKnopf + hKnopf / 2 };

  const pfad = [
    { frame: 46, ...zielVorl3 },
    { frame: 72, ...zielVorl3, klick: true },
    { frame: 116, ...zielEmpf },
    { frame: 136, ...zielEmpf, klick: true },
    { frame: 182, ...zielDrop },
    { frame: 202, ...zielDrop, klick: true },
    { frame: 240, ...zielRech },
    { frame: 258, ...zielRech, klick: true },
    { frame: 360, ...zielBetr },
    { frame: 378, ...zielBetr, klick: true },
    { frame: 470, ...zielKnopf },
    { frame: 500, ...zielKnopf, klick: true },
  ];
  let cx = pfad[0].x, cy = pfad[0].y;
  for (let i = 0; i < pfad.length - 1; i++) {
    const a = pfad[i], b = pfad[i + 1];
    if (frame >= a.frame && frame <= b.frame) {
      const t = smooth(interpolate(frame, [a.frame, b.frame], [0, 1], clamp));
      cx = a.x + (b.x - a.x) * t; cy = a.y + (b.y - a.y) * t;
    } else if (frame > b.frame) { cx = b.x; cy = b.y; }
  }
  const klicks = pfad.filter((k) => k.klick);
  const akt = klicks.find((k) => Math.abs(frame - k.frame) < 26);
  const dip = akt ? interpolate(frame, [akt.frame - 2, akt.frame + 3, akt.frame + 11], [1, 0.8, 1], clamp) : 1;

  /* ═══ Zustaende ═══ */
  const fensterOp = interpolate(frame, [0, 26], [0, 1], clamp);
  const fensterY = ease(frame, 0, 50, 28, 0);
  const titelOp = interpolate(frame, [8, 36], [0, 1], clamp);
  const camPush = ease(frame, 0, 780, 0.988, 1.015);
  // Cursor blendet direkt nach dem Generieren-Klick aus (statt nach rechts
  // unten zu wandern) — das Auge soll dann beim Dokument sein, nicht beim Zeiger.
  const cursorOp = interpolate(frame, [36, 50], [0, 1], clamp)
                 * interpolate(frame, [512, 534], [1, 0], clamp);

  const vorlAktiv = frame > 72 ? 2 : 0;
  const dropOffen = interpolate(frame, [138, 154], [0, 1], clamp) * interpolate(frame, [204, 218], [1, 0], clamp);
  const empfGewaehlt = frame > 204;
  const rzZ = Math.round(interpolate(frame, [264, 336], [0, 11], clamp));
  const rzFokus = frame > 258 && frame < 352;
  const btZ = Math.round(interpolate(frame, [384, 436], [0, 8], clamp));
  const btFokus = frame > 378 && frame < 462;
  const datumDa = frame > 452;
  const kHover = interpolate(frame, [478, 494], [0, 1], clamp);
  const kKlick = interpolate(frame, [498, 504, 514], [0, 1, 0], clamp);
  const kLaden = interpolate(frame, [506, 516], [0, 1], clamp) * interpolate(frame, [592, 602], [1, 0], clamp);
  const kFertig = interpolate(frame, [598, 612], [0, 1], clamp);
  const a4Op = interpolate(frame, [48, 84], [0, 1], clamp);
  const a4Text = interpolate(frame, [606, 730], [0, 1], clamp);
  const neuDoc = interpolate(frame, [608, 668], [0, 1],
    { easing: Easing.out(Easing.cubic), ...clamp });   // laenger: die
  // Verdraengung der anderen Karten soll sichtbar sein, nicht huschen
  const fazitOp = interpolate(frame, [706, 742], [0, 1], clamp);

  const labelStil = {
    fontFamily: F_D, fontSize: px(10.5), fontWeight: 600,
    color: "rgba(255,255,255,0.38)", textTransform: "uppercase",
    letterSpacing: "0.1em", marginBottom: sp(6), whiteSpace: "nowrap",
  };
  const feldStil = (fokus) => ({
    height: hFeld, borderRadius: 9, boxSizing: "border-box",
    background: "rgba(255,255,255,0.05)",
    border: `1px solid ${fokus ? ACCENT + "60" : "rgba(255,255,255,0.09)"}`,
    boxShadow: fokus ? `0 0 0 3px ${ACCENT}15` : "none",
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: `0 ${sp(14)}px`, fontFamily: F_S, fontSize: px(12.5), color: "#fff",
  });

  return (
    <AbsoluteFill style={{ background: "#05070a", overflow: "hidden" }}>
      <AbsoluteFill style={{
        background: `radial-gradient(ellipse 55% 50% at 20% 28%, ${MARKE}0d 0%, transparent 58%),
                     radial-gradient(ellipse 50% 45% at 80% 70%, ${ACCENT}08 0%, transparent 60%),
                     linear-gradient(165deg, #0a1014 0%, #05070a 100%)`,
      }} />

      <AbsoluteFill style={{ transform: `scale(${camPush})` }}>
        {/* Titel */}
        <div style={{
          position: "absolute", left: fx, top: H * 0.042, opacity: titelOp,
          display: "flex", alignItems: "baseline", gap: sp(10),
        }}>
          <span style={{ fontFamily: F_D, fontSize: H * 0.04, fontWeight: 700,
            color: "#FFF", letterSpacing: "-0.03em" }}>{titel}</span>
          <span style={{ fontFamily: BRAND.fonts.akzent, fontStyle: "italic",
            fontSize: H * 0.044, fontWeight: 400, color: p.akzent,
            textShadow: `0 0 26px ${p.akzent}44` }}>{titelAkzent}</span>
        </div>

        {/* ═══ FENSTER — komplett als Flex ═══ */}
        <div style={{
          position: "absolute", left: fx, top: fy, width: fw, height: fh,
          opacity: fensterOp, transform: `translateY(${fensterY}px)`,
          borderRadius: 14, overflow: "hidden",
          background: "linear-gradient(160deg, rgba(255,255,255,0.035), rgba(8,13,19,0.96))",
          border: "1px solid rgba(255,255,255,0.08)",
          boxShadow: "0 40px 100px rgba(0,0,0,0.75)",
          display: "flex", flexDirection: "column",
        }}>
          {/* Topbar */}
          <div style={{
            height: kopfH, flexShrink: 0, borderBottom: "1px solid rgba(255,255,255,0.06)",
            display: "flex", alignItems: "center", padding: `0 ${sp(20)}px`, gap: sp(8),
          }}>
            <span style={{ fontFamily: F_S, fontSize: px(11), color: "rgba(255,255,255,0.35)" }}>Büroflow</span>
            <span style={{ color: "rgba(255,255,255,0.2)" }}>/</span>
            <span style={{ fontFamily: F_S, fontSize: px(11), color: "rgba(255,255,255,0.7)" }}>Mahnungflow</span>
          </div>

          {/* Drei Spalten */}
          <div style={{ flex: 1, minHeight: 0, display: "flex" }}>

            {/* ── SPALTE 1: Dokumentliste ── */}
            <div style={{
              width: cListe, flexShrink: 0, borderRight: "1px solid rgba(255,255,255,0.06)",
              display: "flex", flexDirection: "column", padding: sp(14), boxSizing: "border-box",
              gap: sp(9), minWidth: 0,   // enger: vorher klaffte oben eine Luecke
            }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                alignItems: "flex-start", gap: sp(8) }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: F_D, fontSize: px(14), fontWeight: 700,
                    color: "rgba(255,255,255,0.9)", letterSpacing: "-0.01em" }}>Mahnflow</div>
                  <div style={{ fontFamily: F_S, fontSize: px(9), color: "rgba(255,255,255,0.35)",
                    marginTop: sp(3), lineHeight: 1.4 }}>Mahnungen erstellen</div>
                </div>
                <div style={{
                  flexShrink: 0, padding: `${sp(6)}px ${sp(11)}px`, borderRadius: 8,
                  background: `${ACCENT}18`, border: `1px solid ${ACCENT}38`, color: ACCENT,
                  fontFamily: F_S, fontSize: px(10), fontWeight: 600, whiteSpace: "nowrap",
                }}>+ Neu</div>
              </div>

              <div style={{ display: "flex", gap: sp(4), flexWrap: "wrap" }}>
                {["Alle", "Offen", "Gesendet", "Bezahlt"].map((f, i) => (
                  <div key={f} style={{
                    padding: `${sp(4)}px ${sp(8)}px`, borderRadius: 6,
                    fontFamily: F_S, fontSize: px(9), fontWeight: 500, whiteSpace: "nowrap",
                    background: i === 0 ? `${ACCENT}18` : "rgba(255,255,255,0.04)",
                    border: `1px solid ${i === 0 ? ACCENT + "38" : "rgba(255,255,255,0.08)"}`,
                    color: i === 0 ? ACCENT : "rgba(255,255,255,0.4)",
                  }}>{f}</div>
                ))}
              </div>

              {/* ECHTE LISTEN-BEWEGUNG: Das neue Dokument klappt oben auf
                  (Hoehe waechst von 0 auf volle Kartenhoehe) und schiebt dabei
                  die bestehenden Karten SICHTBAR nach unten. Kein blosses
                  Einblenden — die anderen Karten bewegen sich mit. */}
              <div style={{ display: "flex", flexDirection: "column", gap: sp(4), minHeight: 0 }}>
                {[
                  { t: "Letzte Mahnung", c: "Weber GmbH", d: "17.08.2026", a: "1.840", s: "Gesendet", sc: "#818cf8", neu: true },
                  { t: "Erste Mahnung", c: "Bauer & Partner", d: "09.08.2026", a: "620", s: "Bezahlt", sc: "#22c55e" },
                  { t: "Zahlungserinnerung", c: "Lenz Logistik", d: "04.08.2026", a: "3.200", s: "Bezahlt", sc: "#22c55e" },
                ].map((d, i) => (
                  <div key={i} style={{
                    padding: d.neu ? `${sp(11) * neuDoc}px ${sp(11)}px` : sp(11),
                    borderRadius: 10, boxSizing: "border-box", minWidth: 0, overflow: "hidden",
                    // Die neue Karte waechst in der HOEHE -> Flex schiebt die
                    // darunterliegenden Karten automatisch nach unten.
                    maxHeight: d.neu ? `${neuDoc * sp(88)}px` : "none",
                    opacity: d.neu ? interpolate(neuDoc, [0.15, 0.6], [0, 1], clamp) : 1,
                    transform: d.neu ? `translateX(${(1 - neuDoc) * -22}px)` : "none",
                    background: d.neu && neuDoc > 0.5 ? `${ACCENT}10` : "transparent",
                    border: `1px solid ${d.neu && neuDoc > 0.5 ? ACCENT + "28" : "transparent"}`,
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between",
                      alignItems: "center", gap: sp(6), marginBottom: sp(5) }}>
                      <span style={{ fontFamily: F_D, fontSize: px(11), fontWeight: 700,
                        color: "rgba(255,255,255,0.88)", letterSpacing: "-0.01em", minWidth: 0,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.t}</span>
                      <span style={{ flexShrink: 0, padding: `${sp(3)}px ${sp(6)}px`, borderRadius: 5,
                        fontFamily: F_S, fontSize: px(8), fontWeight: 600,
                        background: `${d.sc}1f`, color: d.sc, whiteSpace: "nowrap" }}>{d.s}</span>
                    </div>
                    <div style={{ fontFamily: F_S, fontSize: px(10),
                      color: "rgba(255,255,255,0.55)", marginBottom: sp(4),
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.c}</div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontFamily: F_S, fontSize: px(9),
                        color: "rgba(255,255,255,0.28)" }}>{d.d}</span>
                      <span style={{ fontFamily: F_D, fontSize: px(10), fontWeight: 700,
                        color: "rgba(255,255,255,0.65)" }}>{d.a} €</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ── SPALTE 2: Formular ── */}
            <div style={{
              width: cForm, flexShrink: 0, borderRight: "1px solid rgba(255,255,255,0.06)",
              display: "flex", flexDirection: "column", padding: sp(20), boxSizing: "border-box",
              gap: sp(18), minWidth: 0,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                alignItems: "flex-start", gap: sp(10) }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: F_D, fontSize: px(14), fontWeight: 700,
                    color: "rgba(255,255,255,0.9)", letterSpacing: "-0.01em" }}>Neues Dokument</div>
                  <div style={{ fontFamily: F_S, fontSize: px(9),
                    color: "rgba(255,255,255,0.35)", marginTop: sp(3) }}>MAH-2026-001</div>
                </div>
                <div style={{
                  flexShrink: 0, display: "flex", alignItems: "center", gap: sp(5),
                  padding: `${sp(6)}px ${sp(11)}px`, borderRadius: 8,
                  background: `${ACCENT}18`, border: `1px solid ${ACCENT}38`, color: ACCENT,
                  fontFamily: F_S, fontSize: px(10), fontWeight: 600, whiteSpace: "nowrap",
                }}>
                  <svg width={px(9)} height={px(9)} viewBox="0 0 24 24" fill="none"
                    stroke={ACCENT} strokeWidth="2.2">
                    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" />
                  </svg>Vorschau
                </div>
              </div>

              <div>
                <div style={labelStil}>Vorlage</div>
                <div style={{ display: "flex", gap: sp(6), height: hVorlTabs }}>
                  {["Zahlungserinnerung", "Erste Mahnung", "Letzte Mahnung"].map((v, i) => {
                    const aktiv = i === vorlAktiv;
                    return (
                      <div key={v} style={{
                        flex: 1, borderRadius: 8, display: "flex", alignItems: "center",
                        justifyContent: "center", textAlign: "center", minWidth: 0,
                        fontFamily: F_S, fontSize: px(8.5), fontWeight: 500,
                        background: aktiv ? `${ACCENT}18` : "rgba(255,255,255,0.04)",
                        border: `1px solid ${aktiv ? ACCENT + "45" : "rgba(255,255,255,0.08)"}`,
                        color: aktiv ? ACCENT : "rgba(255,255,255,0.45)",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        padding: `0 ${sp(4)}px`,
                      }}>{v}</div>
                    );
                  })}
                </div>
              </div>

              {/* Felder */}
              <div style={{ display: "flex", flexDirection: "column", gap: sp(16), position: "relative" }}>
                <div>
                  <div style={labelStil}>Empfänger / Kunde</div>
                  <div style={feldStil(dropOffen > 0.3)}>
                    <span style={{ color: empfGewaehlt ? "#fff" : "rgba(255,255,255,0.22)" }}>
                      {empfGewaehlt ? "Weber GmbH" : "Kontakt auswählen…"}</span>
                    <svg width={px(10)} height={px(10)} viewBox="0 0 24 24"
                      style={{ transform: `rotate(${dropOffen * 180}deg)`, flexShrink: 0 }}>
                      <polyline points="6 9 12 15 18 9" fill="none" stroke="rgba(255,255,255,0.4)"
                        strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                  {dropOffen > 0.02 && (
                    <div style={{
                      position: "absolute", left: 0, right: 0, top: hFeld + sp(28),
                      opacity: dropOffen, transform: `translateY(${(1 - dropOffen) * -8}px)`,
                      borderRadius: 9, overflow: "hidden", zIndex: 12,
                      background: "#14121e", border: `1px solid ${ACCENT}33`,
                      boxShadow: "0 18px 44px rgba(0,0,0,0.7)",
                    }}>
                      {["Weber GmbH", "Bauer & Partner", "Lenz Logistik"].map((n, i) => (
                        <div key={n} style={{
                          padding: `${sp(8)}px ${sp(14)}px`, fontFamily: F_S, fontSize: px(10.5),
                          color: i === 0 && frame > 194 ? ACCENT : "rgba(255,255,255,0.8)",
                          background: i === 0 && frame > 194 ? `${ACCENT}14` : "transparent",
                          borderBottom: i < 2 ? "1px solid rgba(255,255,255,0.05)" : "none",
                        }}>{n}</div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <div style={labelStil}>Bezug: Rechnungsnummer</div>
                  <div style={feldStil(rzFokus)}>
                    <span style={{ display: "flex", alignItems: "center",
                      color: rzZ ? "#fff" : "rgba(255,255,255,0.22)" }}>
                      {rzZ ? "R-2026-0847".slice(0, rzZ) : "z.B. R-2025-042"}
                      {rzFokus && rzZ > 0 && rzZ < 11 && (
                        <span style={{ display: "inline-block", width: 2, height: px(13),
                          background: ACCENT, marginLeft: 2,
                          opacity: Math.floor(frame / 16) % 2 === 0 ? 1 : 0.15 }} />)}
                    </span>
                  </div>
                </div>

                <div>
                  <div style={labelStil}>Offener Betrag (€)</div>
                  <div style={feldStil(btFokus)}>
                    <span style={{ display: "flex", alignItems: "center",
                      color: btZ ? "#fff" : "rgba(255,255,255,0.22)" }}>
                      {btZ ? "1.840,00".slice(0, btZ) : "0,00"}
                      {btFokus && btZ > 0 && btZ < 8 && (
                        <span style={{ display: "inline-block", width: 2, height: px(13),
                          background: ACCENT, marginLeft: 2,
                          opacity: Math.floor(frame / 16) % 2 === 0 ? 1 : 0.15 }} />)}
                    </span>
                  </div>
                </div>

                <div>
                  <div style={labelStil}>Urspr. Fälligkeitsdatum</div>
                  <div style={feldStil(false)}>
                    <span style={{ color: datumDa ? "#fff" : "rgba(255,255,255,0.22)" }}>
                      {datumDa ? "31.07.2026" : "tt.mm.jjjj"}</span>
                    <svg width={px(10)} height={px(10)} viewBox="0 0 24 24" fill="none"
                      stroke="rgba(255,255,255,0.35)" strokeWidth="2" style={{ flexShrink: 0 }}>
                      <rect x="3" y="4" width="18" height="18" rx="2" />
                      <line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" />
                      <line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                  </div>
                </div>
              </div>

              <div>
                <div style={{
                  height: hKnopf, borderRadius: 10,
                  transform: `translateY(${-kHover * 2 + kKlick * 3}px) scale(${1 + kHover * 0.012 - kKlick * 0.02})`,
                  background: kLaden > 0.5 ? `${ACCENT}88` : ACCENT,
                  boxShadow: `0 0 ${28 + kHover * 18}px ${ACCENT}40`,
                  display: "flex", alignItems: "center", justifyContent: "center", gap: sp(8),
                  fontFamily: F_D, fontSize: px(13), fontWeight: 700, color: "#fff",
                  letterSpacing: "-0.01em",
                }}>
                  {kLaden > 0.5 ? (<>
                    <svg width={px(13)} height={px(13)} viewBox="0 0 24 24"
                      style={{ transform: `rotate(${(frame - 506) * 8}deg)` }}>
                      <circle cx="12" cy="12" r="9" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="3" />
                      <path d="M12 3 a9 9 0 0 1 9 9" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
                    </svg>Wird generiert...</>
                  ) : kFertig > 0.5 ? (<>
                    <svg width={px(13)} height={px(13)} viewBox="0 0 24 24">
                      <path d="M5 13 L10 18 L19 6" fill="none" stroke="#fff" strokeWidth="3"
                        strokeLinecap="round" strokeLinejoin="round" strokeDasharray="30"
                        strokeDashoffset={30 * (1 - interpolate(frame, [600, 622], [0, 1], clamp))} />
                    </svg>Fertig</>
                  ) : (<>
                    <svg width={px(13)} height={px(13)} viewBox="0 0 24 24" fill="none"
                      stroke="#fff" strokeWidth="2.5">
                      <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
                    </svg>Mit KI generieren</>
                  )}
                </div>
                <div style={{ textAlign: "center", marginTop: sp(7),
                  fontFamily: F_S, fontSize: px(9), color: "rgba(255,255,255,0.15)",
                }}>⌘ + ↵ zum Generieren</div>
              </div>
            </div>

            {/* ── SPALTE 3: Design-Auswahl + A4 ── */}
            <div style={{
              flex: 1, minWidth: 0, background: "rgba(0,0,0,0.15)",
              display: "flex", flexDirection: "column", padding: sp(18),
              boxSizing: "border-box", gap: sp(12), opacity: a4Op,
            }}>
              {/* Design-Karten */}
              <div style={{ display: "flex", gap: sp(8), flexShrink: 0 }}>
                {[["Standard", "Klassisch"], ["Modern", "Zweispaltig"], ["Minimal", "Whitespace"]].map((t, i) => {
                  const aktiv = i === 0;
                  return (
                    <div key={t[0]} style={{
                      flex: 1, minWidth: 0, display: "flex", flexDirection: "column",
                      alignItems: "center", gap: sp(6), padding: `${sp(9)}px ${sp(6)}px`,
                      borderRadius: 10, boxSizing: "border-box",
                      background: aktiv ? `${ACCENT}12` : "rgba(255,255,255,0.03)",
                      border: `1.5px solid ${aktiv ? ACCENT : "rgba(255,255,255,0.09)"}`,
                    }}>
                      <div style={{
                        width: sp(44), height: sp(58), background: "#faf9f7", borderRadius: 4,
                        padding: `${sp(6)}px ${sp(5)}px`, boxSizing: "border-box",
                        display: "flex", flexDirection: "column", gap: sp(3), flexShrink: 0,
                        boxShadow: aktiv ? `0 0 0 2px ${ACCENT}` : "0 1px 6px rgba(0,0,0,0.35)",
                      }}>
                        {i === 1 && <div style={{ height: sp(3), background: ACCENT, borderRadius: 1, opacity: 0.8 }} />}
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <div style={{ width: sp(14), height: sp(3.5), background: "#1a1a1a", borderRadius: 1 }} />
                          <div style={{ width: sp(9), height: sp(3.5), background: "#ccc", borderRadius: 1 }} />
                        </div>
                        {[100, 80, 90, 70].map((w, j) => (
                          <div key={j} style={{ width: `${w}%`, height: sp(2),
                            background: j === 0 ? "#ddd" : "#e8e8e8", borderRadius: 1 }} />
                        ))}
                      </div>
                      <div style={{ textAlign: "center", minWidth: 0 }}>
                        <div style={{ fontFamily: F_S, fontSize: px(9), fontWeight: 600,
                          color: aktiv ? "#fff" : "rgba(255,255,255,0.6)" }}>{t[0]}</div>
                        <div style={{ fontFamily: F_S, fontSize: px(7.5),
                          color: "rgba(255,255,255,0.3)" }}>{t[1]}</div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Logo-Schalter */}
              <div style={{
                flexShrink: 0, height: sp(28), borderRadius: 8, boxSizing: "border-box",
                background: `${ACCENT}0f`, border: `1px solid ${ACCENT}28`,
                display: "flex", alignItems: "center", gap: sp(8), padding: `0 ${sp(10)}px`,
              }}>
                <div style={{ width: sp(26), height: sp(14), borderRadius: 999, background: ACCENT,
                  display: "flex", alignItems: "center", justifyContent: "flex-end",
                  padding: sp(2), boxSizing: "border-box", flexShrink: 0 }}>
                  <div style={{ width: sp(10), height: sp(10), borderRadius: "50%", background: "#fff" }} />
                </div>
                <span style={{ fontFamily: F_S, fontSize: px(10),
                  color: "rgba(255,255,255,0.75)" }}>Logo anzeigen</span>
              </div>

              {/* A4 */}
              <div style={{
                flex: 1, minHeight: 0, background: "#faf9f7", borderRadius: 10,
                boxShadow: "0 14px 36px rgba(0,0,0,0.45)",
                padding: `${sp(22)}px ${sp(24)}px ${sp(16)}px`, boxSizing: "border-box",
                display: "flex", flexDirection: "column", fontFamily: F_S, color: "#1a1a1a",
              }}>
                <div style={{ flexShrink: 0, display: "flex", justifyContent: "space-between",
                  alignItems: "flex-start", gap: sp(12), marginBottom: sp(12) }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontFamily: F_D, fontSize: px(12), fontWeight: 700,
                      marginBottom: sp(4) }}>Beispielfirma GmbH</div>
                    <div style={{ fontSize: px(8), color: "#888", lineHeight: 1.7 }}>
                      Hauptstraße 28, 74586 Berlin<br />jonas@personalberatung.de
                    </div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ fontFamily: F_D, fontSize: px(13), fontWeight: 800,
                      letterSpacing: "-0.02em", marginBottom: sp(3), whiteSpace: "nowrap" }}>
                      {vorlAktiv === 2 ? "LETZTE MAHNUNG" : "ZAHLUNGSERINNERUNG"}</div>
                    <div style={{ fontSize: px(8.5), color: "#999" }}>MAH-2026-001</div>
                    <div style={{ fontSize: px(8.5), color: "#999", marginTop: sp(2) }}>17.08.2026</div>
                  </div>
                </div>
                <div style={{ flexShrink: 0, width: sp(38), height: 2, background: MARKE,
                  marginBottom: sp(12), borderRadius: 1 }} />
                <div style={{ flexShrink: 0, paddingBottom: sp(10), marginBottom: sp(10),
                  borderBottom: "1px solid #e8e3dc" }}>
                  <div style={{ fontSize: px(7.5), color: "#bbb", textTransform: "uppercase",
                    letterSpacing: "0.1em", marginBottom: sp(4) }}>An</div>
                  {empfGewaehlt ? (<>
                    <div style={{ fontSize: px(10.5), fontWeight: 700 }}>Weber GmbH</div>
                    <div style={{ fontSize: px(8.5), color: "#999", marginTop: sp(2) }}>
                      Industriestraße 12, 70565 Stuttgart</div>
                  </>) : (
                    <div style={{ fontSize: px(10.5), fontWeight: 700, color: "#ccc" }}>— Empfänger auswählen —</div>
                  )}
                </div>
                <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
                  {a4Text > 0.01 ? (<>
                    <div style={{ fontFamily: F_D, fontSize: px(10), fontWeight: 700,
                      marginBottom: sp(9),
                      opacity: interpolate(a4Text, [0, 0.12], [0, 1], clamp) }}>
                      Letzte Mahnung zu Rechnung R-2026-0847</div>
                    {["Sehr geehrte Damen und Herren,",
                      "trotz unserer bisherigen Erinnerungen konnten wir",
                      "keinen Zahlungseingang feststellen. Der offene",
                      "Betrag von 1.840,00 € ist seit dem 31.07.2026 fällig.",
                      "",
                      "Wir fordern Sie letztmalig auf, den Betrag bis zum",
                      "31.08.2026 zu überweisen.",
                      "",
                      "Mit freundlichen Grüßen",
                      "Beispielfirma GmbH"].map((z, i) => {
                        const zi = interpolate(a4Text, [0.1 + i * 0.075, 0.1 + i * 0.075 + 0.12], [0, 1], clamp);
                        if (!z) return <div key={i} style={{ height: sp(7) }} />;
                        return <div key={i} style={{ fontSize: px(9), color: "#333",
                          lineHeight: 1.7, opacity: zi,
                          transform: `translateY(${(1 - zi) * 4}px)` }}>{z}</div>;
                      })}
                  </>) : (
                    <div style={{ fontSize: px(9), color: "#999", fontStyle: "italic", lineHeight: 1.7 }}>
                      Sobald Sie einen Empfänger ausgewählt und die Rechnungsdaten eingegeben haben,
                      wird hier Ihre vollständige Mahnung angezeigt.
                    </div>
                  )}
                </div>
                <div style={{ flexShrink: 0, paddingTop: sp(9), borderTop: "1px solid #e8e3dc",
                  display: "flex", justifyContent: "space-between", gap: sp(12),
                  fontSize: px(7), color: "#888", lineHeight: 1.7 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, color: "#555", fontSize: px(6.5),
                      textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: sp(3) }}>Bankverbindung</div>
                    <div>IBAN: DE89370400440532013000</div>
                  </div>
                  <div style={{ textAlign: "right", minWidth: 0 }}>
                    <div style={{ fontWeight: 700, color: "#555", fontSize: px(6.5),
                      textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: sp(3) }}>Kontakt</div>
                    <div>jonas@personalberatung.de</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Ripples + Cursor */}
        {/* Klick-Ripple: nur EINER, exakt an der aktuellen Cursorposition.
            Vorher wurden alle Klickpunkte gleichzeitig gezeichnet — dadurch
            schwebten rote Ringe im Bild, wo der Cursor gar nicht war. */}
        {(() => {
          const k = klicks.find((kk) => frame >= kk.frame && frame < kk.frame + 30);
          if (!k) return null;
          const r = interpolate(frame, [k.frame, k.frame + 28], [5, 34], clamp);
          const rop = interpolate(frame, [k.frame, k.frame + 28], [0.6, 0], clamp);
          if (rop <= 0.02) return null;
          return <div style={{
            position: "absolute", left: cx - r, top: cy - r, width: r * 2, height: r * 2,
            borderRadius: "50%", border: `2px solid ${ACCENT}`, opacity: rop,
            zIndex: 18, pointerEvents: "none",
          }} />;
        })()}
        <div style={{
          position: "absolute", left: cx, top: cy, opacity: cursorOp,
          transform: `scale(${dip})`, transformOrigin: "top left", zIndex: 20,
          filter: "drop-shadow(0 3px 8px rgba(0,0,0,0.7))",
        }}>
          <svg width="22" height="26" viewBox="0 0 26 30">
            <path d="M2 2 L2 22 L7.5 17 L11 26 L15 24 L11.5 15.5 L19 15 Z"
              fill="#FFF" stroke="#0b1016" strokeWidth="1.6" strokeLinejoin="round" />
          </svg>
        </div>

        {/* Fazit */}
        <div style={{
          position: "absolute", left: fx, top: fy + fh + H * 0.022, opacity: fazitOp,
          display: "flex", alignItems: "baseline", gap: sp(8),
        }}>
          <span style={{ fontFamily: F_D, fontSize: H * 0.03, fontWeight: 700,
            color: "#FFF", letterSpacing: "-0.02em" }}>Vier Klicks —</span>
          <span style={{ fontFamily: BRAND.fonts.akzent, fontStyle: "italic",
            fontSize: H * 0.034, fontWeight: 400, color: p.akzent }}>Mahnung raus.</span>
        </div>
      </AbsoluteFill>

      <AbsoluteFill style={{
        background: "radial-gradient(ellipse at 50% 46%, transparent 62%, rgba(0,0,0,0.48) 100%)",
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
};

export default Komponente;
