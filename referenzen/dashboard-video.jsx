// dashboard-hero.jsx — Büroflow Dashboard 1:1 Vollbild-Nachbau (Remotion, 60fps)
// Sidebar (240px) + Topbar (58px) + Content + Gravity-Stars-Hintergrund.
// Quelle: dash-sidebar.tsx, dash-topbar.tsx, dashboard-client.tsx, gravity-stars.tsx
// Alles frame-basiert & deterministisch. Hover → statisch. fetch → Fake-Daten.

import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { loadFont as loadBricolage } from "@remotion/google-fonts/BricolageGrotesque";
import { loadFont as loadDMSans } from "@remotion/google-fonts/DMSans";

const bricolage = loadBricolage("normal", { weights: ["400", "500", "600", "700", "800"] });
const dmSans = loadDMSans("normal", { weights: ["400", "500", "600", "700"] });

/* ═══════════════ Konstanten ═══════════════ */
const ACCENT = "#5DCAA5";
const DESIGN_W = 1600;
const DESIGN_H = 1000;
const SIDEBAR_W = 240;
const TOPBAR_H = 58;
const FONT_DISPLAY = `'${bricolage.fontFamily}','Geist',sans-serif`;
const FONT_SANS = `'${dmSans.fontFamily}','Geist',sans-serif`;
const FONT_MONO = "'Geist Mono','JetBrains Mono',monospace";
const BF = "blur(26px) saturate(200%) brightness(1.12)";

const easeOutExpo = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
const clamp01 = (v) => Math.max(0, Math.min(1, v));
// Fortschritt 0→1 zwischen startFrame und startFrame+dur, easeOutExpo
const prog = (frame, start, dur) => easeOutExpo(clamp01((frame - start) / dur));

/* ═══════════════ Icons (aus dash-icons.tsx) ═══════════════ */
const SvgIcon = ({ size = 20, children, sw = 1.75 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"
    style={{ flexShrink: 0, display: "block" }}>{children}</svg>
);
const IcoDashboard = ({ size }) => <SvgIcon size={size}><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></SvgIcon>;
const IcoMahnung = ({ size }) => <SvgIcon size={size}><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></SvgIcon>;
const IcoBrief = ({ size }) => <SvgIcon size={size}><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></SvgIcon>;
const IcoAngebot = ({ size }) => <SvgIcon size={size}><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></SvgIcon>;
const IcoRechnung = ({ size }) => <SvgIcon size={size}><path d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 2.5 2 2.5-2 3.5 2z"/></SvgIcon>;
const IcoSettings = ({ size }) => <SvgIcon size={size}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></SvgIcon>;
const IcoUsers = ({ size }) => <SvgIcon size={size}><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></SvgIcon>;
const IcoBell = ({ size }) => <SvgIcon size={size}><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></SvgIcon>;
const IcoZap = ({ size }) => <SvgIcon size={size}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></SvgIcon>;
const IcoTrendingUp = ({ size }) => <SvgIcon size={size}><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></SvgIcon>;
const IcoHistory = ({ size }) => <SvgIcon size={size}><polyline points="12 8 12 12 14 14"/><path d="M3.05 11a9 9 0 1 0 .5-4H1"/><polyline points="1 3 1 7 5 7"/></SvgIcon>;
const IcoBilling = ({ size }) => <SvgIcon size={size}><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></SvgIcon>;
const IcoSearch = ({ size }) => <SvgIcon size={size} sw={2.5}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></SvgIcon>;
const IcoHome = ({ size }) => <SvgIcon size={size} sw={2.2}><path d="M3 9.5 12 3l9 6.5"/><path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9"/><path d="M9 20v-6h6v6"/></SvgIcon>;
const IcoPlus = ({ size = 13 }) => <SvgIcon size={size} sw={2.5}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></SvgIcon>;
const IcoChevDown = ({ size = 11 }) => <SvgIcon size={size} sw={2.5}><polyline points="6 9 12 15 18 9"/></SvgIcon>;
const IcoChevUp = ({ size = 14 }) => <SvgIcon size={size} sw={2}><polyline points="18 15 12 9 6 15"/></SvgIcon>;

/* ═══════════════ Hintergrund: Gradient + Gravity Stars ═══════════════ */
function Background({ frame }) {
  // Referenz-Look: fast schwarz, grüner Radial-Glow oben links, sanfte Vignette.
  return (
    <div style={{ position: "absolute", inset: 0, background: "#050608", overflow: "hidden" }}>
      {/* Haupt-Glow oben links */}
      <div style={{ position: "absolute", top: "-18%", left: "-12%", width: "58%", height: "75%",
        background: "radial-gradient(circle, rgba(93,202,165,0.12) 0%, rgba(93,202,165,0.05) 35%, transparent 70%)",
        filter: "blur(10px)" }} />
      {/* Sekundärer, sehr dezenter Glow Mitte */}
      <div style={{ position: "absolute", top: "20%", left: "15%", width: "45%", height: "55%",
        background: "radial-gradient(ellipse, rgba(93,202,165,0.03) 0%, transparent 70%)", filter: "blur(30px)" }} />
      {/* Vignette unten rechts */}
      <div style={{ position: "absolute", inset: 0,
        background: "radial-gradient(circle at 15% 5%, transparent 40%, rgba(0,0,0,0.45) 100%)" }} />
    </div>
  );
}

/* ═══════════════ Sidebar (dash-sidebar.tsx) ═══════════════ */
const NAV = {
  overview: [{ label: "Dashboard", Icon: IcoDashboard, active: true }],
  management: [
    { label: "Kontakte", Icon: IcoUsers },
    { label: "Verlauf", Icon: IcoHistory },
  ],
  flows: [
    { label: "Mahnungflow", Icon: IcoMahnung },
    { label: "Mailflow", Icon: IcoBrief },
    { label: "Angebotsflow", Icon: IcoAngebot },
    { label: "E-Rechnung", Icon: IcoRechnung },
  ],
  system: [
    { label: "Abrechnung", Icon: IcoBilling },
    { label: "Einstellungen", Icon: IcoSettings },
  ],
};

function SectionLabel({ children }) {
  return (
    <div style={{ padding: "14px 22px 6px", fontSize: 9.5, letterSpacing: "0.15em",
      textTransform: "uppercase", color: "rgba(255,255,255,0.45)",
      fontFamily: FONT_DISPLAY, fontWeight: 600 }}>{children}</div>
  );
}

function NavItem({ label, Icon, active, appear }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 11,
      padding: "9px 14px", margin: "1px 0", borderRadius: 10, position: "relative",
      background: active ? "rgba(93,202,165,0.12)" : "transparent",
      border: `1px solid ${active ? "rgba(93,202,165,0.2)" : "transparent"}`,
      color: active ? "#8ee7c9" : "rgba(255,255,255,0.72)",
      opacity: appear, transform: `translateX(${(1 - appear) * -14}px)`,
    }}>
      {active && (
        <div style={{ position: "absolute", left: 0, top: "20%", bottom: "20%", width: 3,
          borderRadius: "0 3px 3px 0",
          background: "linear-gradient(180deg,#8ee7c9,#5DCAA5)",
          boxShadow: "0 0 10px rgba(93,202,165,0.7)" }} />
      )}
      <span style={{ flexShrink: 0 }}><Icon size={16} /></span>
      <span style={{ flex: 1, fontSize: 13, fontFamily: FONT_SANS,
        fontWeight: active ? 500 : 400, letterSpacing: "-0.01em", whiteSpace: "nowrap" }}>{label}</span>
    </div>
  );
}

function Sidebar({ frame, userName, userInitial, totalCredits }) {
  const slide = prog(frame, 0, 40);
  // Nav-Items staffeln
  let navIdx = 0;
  const itemAppear = () => prog(frame, 14 + navIdx++ * 3, 24);

  return (
    <div style={{
      position: "absolute", left: 0, top: 0, width: SIDEBAR_W, height: DESIGN_H,
      background: "rgba(255,255,255,0.06)",
      borderRight: "1px solid rgba(255,255,255,0.14)",
      display: "flex", flexDirection: "column",
      backdropFilter: "blur(26px) saturate(200%) brightness(1.05)",
      WebkitBackdropFilter: "blur(26px) saturate(200%) brightness(1.05)",
      boxShadow: "inset -1px 0 0 rgba(255,255,255,0.08), 2px 0 40px rgba(0,0,0,0.35)",
      zIndex: 10,
      transform: `translateX(${(1 - slide) * -SIDEBAR_W}px)`,
    }}>
      {/* Logo */}
      <div style={{ padding: "24px 22px 20px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <Img src={staticFile("brand/logo_white_transparent.png")}
          style={{ height: 28, width: "auto", objectFit: "contain", objectPosition: "left", display: "block" }} />
      </div>

      {/* Nav */}
      <div style={{ flex: 1, paddingBottom: 8, overflow: "hidden" }}>
        <SectionLabel>Übersicht</SectionLabel>
        <nav style={{ padding: "0 10px" }}>
          {NAV.overview.map((it) => <NavItem key={it.label} {...it} appear={itemAppear()} />)}
        </nav>
        <SectionLabel>Verwaltung</SectionLabel>
        <nav style={{ padding: "0 10px" }}>
          {NAV.management.map((it) => <NavItem key={it.label} {...it} appear={itemAppear()} />)}
        </nav>
        <SectionLabel>Flows</SectionLabel>
        <nav style={{ padding: "0 10px" }}>
          {NAV.flows.map((it) => <NavItem key={it.label} {...it} appear={itemAppear()} />)}
        </nav>
        {/* Neues Dokument (soft-Variante) */}
        <div style={{ padding: "10px 10px 4px", opacity: prog(frame, 104, 24) }}>
          <div style={{
            width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
            padding: "9px 14px", borderRadius: 10,
            background: "rgba(93,202,165,0.1)", border: "1px solid rgba(93,202,165,0.25)",
            color: ACCENT, fontSize: 13, fontWeight: 600, fontFamily: FONT_SANS, boxSizing: "border-box",
          }}>
            <IcoPlus size={14} /> Neues Dokument <span style={{ marginLeft: 1, opacity: 0.8, display: "flex" }}><IcoChevDown /></span>
          </div>
        </div>
      </div>

      {/* System */}
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", padding: "8px 10px 6px" }}>
        {NAV.system.map((it) => <NavItem key={it.label} {...it} appear={prog(frame, 114, 24)} />)}
      </div>

      {/* User-Card */}
      <div style={{ padding: "6px 10px 18px", opacity: prog(frame, 124, 24) }}>
        <div style={{
          width: "100%", display: "flex", alignItems: "center", gap: 10,
          padding: "10px 12px", borderRadius: 10, boxSizing: "border-box",
          background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.07)",
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 9, flexShrink: 0,
            background: `linear-gradient(135deg,${ACCENT},#2da882)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, fontWeight: 700, color: "#0e1117", fontFamily: FONT_DISPLAY,
            boxShadow: "0 0 14px rgba(93,202,165,0.3)",
          }}>{userInitial}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5, fontWeight: 500, color: "rgba(255,255,255,0.78)",
              fontFamily: FONT_SANS, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{userName}</div>
            <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 1 }}>
              <div style={{ width: 5, height: 5, borderRadius: "50%", background: ACCENT,
                boxShadow: "0 0 4px rgba(93,202,165,0.7)" }} />
              <span style={{ fontSize: 10.5, color: "rgba(255,255,255,0.55)", fontFamily: FONT_SANS }}>
                Aktiv · {totalCredits} Credits
              </span>
            </div>
          </div>
          <span style={{ color: "rgba(255,255,255,0.4)", display: "flex" }}><IcoChevUp /></span>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════ Topbar (dash-topbar.tsx) ═══════════════ */
function Topbar({ frame, credits, maxCredits, purchasedCredits, userInitial, dateStr }) {
  const slide = prog(frame, 15, 40);
  const total = credits + purchasedCredits;
  const pct = maxCredits > 0 ? Math.min(100, Math.round((credits / maxCredits) * 100)) : 100;

  return (
    <div style={{
      position: "absolute", top: 0, left: SIDEBAR_W, right: 0, height: TOPBAR_H, zIndex: 20,
      borderBottom: "1px solid rgba(255,255,255,0.1)",
      display: "flex", alignItems: "center", gap: 16, padding: "0 28px", boxSizing: "border-box",
      background: "rgba(255,255,255,0.06)",
      backdropFilter: "blur(26px) saturate(200%) brightness(1.08)",
      WebkitBackdropFilter: "blur(26px) saturate(200%) brightness(1.08)",
      boxShadow: "0 1px 0 rgba(255,255,255,0.14), 0 4px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.18)",
      transform: `translateY(${(1 - slide) * -TOPBAR_H}px)`,
    }}>
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        <span style={{ fontSize: 12, color: "rgba(255,255,255,0.52)", fontFamily: FONT_SANS }}>Büroflow</span>
        <span style={{ color: "rgba(255,255,255,0.14)", fontSize: 14, lineHeight: 1 }}>/</span>
        <span style={{ fontSize: 12.5, fontWeight: 500, color: "rgba(255,255,255,0.88)",
          fontFamily: FONT_SANS, letterSpacing: "-0.01em" }}>Dashboard</span>
      </div>

      {/* Mitte: Home + Suche */}
      <div style={{ flex: 1, display: "flex", justifyContent: "center", alignItems: "center", gap: 10 }}>
        <div style={{
          width: 36, height: 36, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
          borderRadius: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)",
          color: "rgba(255,255,255,0.55)",
        }}><IcoHome size={15} /></div>
        <div style={{
          display: "flex", alignItems: "center", gap: 9,
          background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 10, padding: "8px 14px", width: 300, boxSizing: "border-box",
        }}>
          <span style={{ color: "rgba(255,255,255,0.22)", display: "flex" }}><IcoSearch size={13} /></span>
          <span style={{ flex: 1, fontSize: 12.5, color: "rgba(255,255,255,0.35)", fontFamily: FONT_SANS }}>
            Dokument, Kunde suchen…
          </span>
          <span style={{ fontSize: 10.5, color: "rgba(255,255,255,0.18)", fontFamily: FONT_SANS,
            background: "rgba(255,255,255,0.07)", padding: "2px 7px", borderRadius: 5, flexShrink: 0 }}>⌘K</span>
        </div>
      </div>

      {/* Rechts */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
        <span style={{ fontSize: 11.5, color: "rgba(255,255,255,0.55)", fontFamily: FONT_SANS }}>{dateStr}</span>

        {/* Credits-Badge */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8, padding: "5px 11px", borderRadius: 8,
          background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.09)",
        }}>
          <span style={{ color: ACCENT, display: "flex" }}><IcoZap size={11} /></span>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: "rgba(255,255,255,0.9)",
              fontFamily: FONT_DISPLAY, lineHeight: 1, whiteSpace: "nowrap" }}>{total} Credits</span>
            {purchasedCredits > 0 ? (
              <span style={{ fontSize: 9.5, fontWeight: 500, color: "rgba(255,255,255,0.4)",
                fontFamily: FONT_SANS, lineHeight: 1, whiteSpace: "nowrap" }}>
                {credits} mtl. · {purchasedCredits} gekauft
              </span>
            ) : (
              <div style={{ width: 70, height: 2, borderRadius: 2, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${pct * prog(frame, 78, 50)}%`, borderRadius: 2, background: ACCENT }} />
              </div>
            )}
          </div>
        </div>

        <div style={{ width: 1, height: 18, background: "rgba(255,255,255,0.08)" }} />

        {/* Bell */}
        <div style={{
          width: 34, height: 34, display: "flex", alignItems: "center", justifyContent: "center",
          borderRadius: 9, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)",
          position: "relative", color: "rgba(255,255,255,0.42)",
        }}>
          <IcoBell size={15} />
          <div style={{ position: "absolute", top: 8, right: 8, width: 6, height: 6, borderRadius: "50%",
            background: ACCENT, border: "1.5px solid #06060a", boxShadow: "0 0 6px rgba(93,202,165,0.8)" }} />
        </div>

        {/* Avatar */}
        <div style={{
          width: 34, height: 34, borderRadius: 9,
          background: `linear-gradient(135deg,${ACCENT},#6366f1)`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 700, color: "white", fontFamily: FONT_DISPLAY,
          boxShadow: "0 0 16px rgba(93,202,165,0.28)",
        }}>{userInitial}</div>
      </div>
    </div>
  );
}

/* ═══════════════ Glass-Card (dashboard-client.tsx) ═══════════════ */
function GlassCard({ children, accent = "rgba(255,255,255,0.4)", glow, style = {}, appear = 1 }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.08)",
      backdropFilter: BF, WebkitBackdropFilter: BF,
      border: "1px solid rgba(255,255,255,0.18)",
      borderRadius: 24,
      boxShadow: [
        "0 2px 6px rgba(0,0,0,0.28)",
        "0 8px 24px rgba(0,0,0,0.38)",
        "0 20px 48px rgba(0,0,0,0.22)",
        glow ? `0 10px 36px ${glow}14` : "",
        "inset 0 2.5px 0 rgba(255,255,255,0.6)",
        "inset 0 -2px 0 rgba(0,0,0,0.28)",
        "inset 1.5px 0 0 rgba(255,255,255,0.24)",
        "inset -1.5px 0 0 rgba(0,0,0,0.18)",
      ].filter(Boolean).join(", "),
      position: "relative", overflow: "hidden",
      opacity: appear, transform: `translateY(${(1 - appear) * 26}px)`,
      boxSizing: "border-box",
      ...style,
    }}>
      {/* Top-Highlight */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 4,
        background: `linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.25) 10%, ${accent} 28%, rgba(255,255,255,0.92) 50%, ${accent} 72%, rgba(255,255,255,0.25) 90%, transparent 100%)`,
        pointerEvents: "none", borderRadius: "24px 24px 0 0", filter: "blur(0.5px)" }} />
      <div style={{ position: "absolute", top: 0, left: "10%", right: "10%", height: 16,
        background: "linear-gradient(180deg, rgba(255,255,255,0.12) 0%, transparent 100%)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", bottom: 0, left: "5%", right: "5%", height: 2,
        background: "linear-gradient(90deg,transparent,rgba(0,0,0,0.4),transparent)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", top: "10%", bottom: "10%", left: 0, width: 2,
        background: "linear-gradient(180deg,transparent,rgba(255,255,255,0.2),transparent)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", top: "-40%", left: "-20%", width: "58%", height: "72%",
        background: "radial-gradient(ellipse,rgba(255,255,255,0.12) 0%,transparent 65%)", pointerEvents: "none" }} />
      {children}
    </div>
  );
}

function CH({ title, sub, right }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
      <div>
        <h3 style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.02em", fontFamily: FONT_DISPLAY,
          color: "rgba(255,255,255,0.9)", margin: 0, marginBottom: 2 }}>{title}</h3>
        {sub && <p style={{ fontSize: 11, color: "rgba(255,255,255,0.38)", fontFamily: FONT_SANS, margin: 0 }}>{sub}</p>}
      </div>
      {right}
    </div>
  );
}

/* ═══════════════ Sparkline (Draw-Animation) ═══════════════ */
function Sparkline({ data, color, w = 140, h = 44, draw = 1 }) {
  const min = Math.min(...data), max = Math.max(...data), range = max - min || 1;
  const allZero = data.every((v) => v === 0);
  const pts = allZero
    ? data.map((_, i) => ({ x: (i / (data.length - 1)) * w, y: h - 5 }))
    : data.map((v, i) => ({ x: (i / (data.length - 1)) * w, y: h - 4 - ((v - min) / range) * (h - 10) }));
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const area = `${line} L ${w} ${h} L 0 ${h} Z`;
  const uid = `sp${color.replace(/[^a-z0-9]/gi, "")}${w}`;
  const clipId = `${uid}clip`;
  return (
    <svg width={w} height={h} style={{ display: "block", overflow: "visible", flexShrink: 0 }}>
      <defs>
        <linearGradient id={uid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={allZero ? "0.06" : "0.3"} />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
        <clipPath id={clipId}><rect x="0" y="-8" width={w * draw} height={h + 16} /></clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        <path d={area} fill={`url(#${uid})`} />
        <path d={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
          opacity={allZero ? 0.3 : 1} strokeDasharray={allZero ? "3 3" : undefined} />
      </g>
      {!allZero && draw > 0.98 && (
        <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r="3" fill={color}
          style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
      )}
    </svg>
  );
}

/* ═══════════════ AreaChart (Draw-Animation) ═══════════════ */
function smoothLinePath(pts) {
  if (pts.length < 2) return pts.length ? `M ${pts[0][0]} ${pts[0][1]}` : "";
  const t = 0.16;
  const d = [`M ${pts[0][0]} ${pts[0][1]}`];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    d.push(`C ${p1[0] + (p2[0] - p0[0]) * t} ${p1[1] + (p2[1] - p0[1]) * t}, ${p2[0] - (p3[0] - p1[0]) * t} ${p2[1] - (p3[1] - p1[1]) * t}, ${p2[0]} ${p2[1]}`);
  }
  return d.join(" ");
}

function AreaChart({ values, months, frame, start }) {
  const draw = prog(frame, start, 70);
  const dataMax = Math.max(...values);
  const scaleMax = Math.max(dataMax * 1.35, 4);
  const n = values.length;
  const isEmpty = values.every((v) => v === 0);
  const chartH = 156;
  const pts = values.map((v, i) => ({
    x: n > 1 ? (i / (n - 1)) * 100 : 50,
    pct: (v / scaleMax) * 100,
    v,
  }));
  const linePath = smoothLinePath(pts.map((p) => [p.x, 100 - p.pct]));
  const areaPath = linePath ? `${linePath} L 100 100 L 0 100 Z` : "";

  return (
    <div style={{ position: "relative" }}>
      <div style={{ position: "relative", height: chartH }}>
        {[0.25, 0.5, 0.75].map((p, i) => (
          <div key={i} style={{ position: "absolute", left: 0, right: 0, bottom: `${p * 100}%`, height: 1, background: "rgba(255,255,255,0.05)" }} />
        ))}
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none"
          style={{ position: "absolute", inset: 0, overflow: "visible" }}>
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity="0.34" />
              <stop offset="100%" stopColor={ACCENT} stopOpacity="0" />
            </linearGradient>
            <clipPath id="areaClip"><rect x="0" y="-20" width={draw * 100} height="140" /></clipPath>
          </defs>
          {!isEmpty && areaPath && <g clipPath="url(#areaClip)"><path d={areaPath} fill="url(#areaGrad)" /></g>}
          {!isEmpty && linePath && (
            <g clipPath="url(#areaClip)">
              <path d={linePath} fill="none" stroke={ACCENT} strokeWidth="2"
                vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round"
                style={{ filter: `drop-shadow(0 1px 5px ${ACCENT}55)` }} />
            </g>
          )}
        </svg>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 1, background: "rgba(255,255,255,0.14)" }} />
        {/* Punkte + Labels erscheinen, sobald die Linie sie erreicht */}
        {!isEmpty && pts.map((p, i) => {
          const reached = clamp01((draw * 100 - p.x) / 6);
          return p.v > 0 && reached > 0 ? (
            <div key={i} style={{ position: "absolute", left: `${p.x}%`, bottom: `${p.pct}%`,
              transform: `translate(-50%, 50%) scale(${reached})`, opacity: reached }}>
              <div style={{ width: 9, height: 9, borderRadius: "50%", background: ACCENT,
                boxShadow: `0 0 9px ${ACCENT}`, border: "2px solid #0a1310" }} />
              <div style={{ position: "absolute", bottom: "calc(100% + 5px)", left: "50%", transform: "translateX(-50%)",
                fontSize: 10.5, fontWeight: 700, color: "rgba(255,255,255,0.9)", fontFamily: FONT_DISPLAY, whiteSpace: "nowrap" }}>{p.v}</div>
            </div>
          ) : null;
        })}
        {isEmpty && (
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 4 }}>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.32)", fontFamily: FONT_SANS, margin: 0 }}>Noch keine versendeten Dokumente</p>
          </div>
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10 }}>
        {months.map((m, i) => (
          <span key={i} style={{ fontSize: 8.5, color: "rgba(255,255,255,0.3)", fontFamily: FONT_MONO }}>{m}</span>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════ Donut (Füll-Animation) ═══════════════ */
function Donut({ segs, size = 104, fill = 1 }) {
  const total = segs.reduce((a, s) => a + s.v, 0);
  const r = size * 0.36, cx = size / 2, cy = size / 2, circ = 2 * Math.PI * r;
  let acc = 0;
  if (total === 0) return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={size * 0.12} strokeDasharray="4 3" />
    </svg>
  );
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={size * 0.12} />
      {segs.map((s, i) => {
        const dash = Math.max(0, (s.v / total) * circ * fill - 2);
        const offset = -(acc / total) * circ * fill - circ * 0.25;
        acc += s.v;
        return <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={s.color}
          strokeWidth={size * 0.12} strokeDasharray={`${dash} ${circ}`}
          strokeDashoffset={offset} strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 5px ${s.color}80)` }} />;
      })}
      <text x={cx} y={cy - 5} textAnchor="middle" fill="white"
        fontSize={size * 0.16} fontWeight="800" fontFamily={FONT_DISPLAY}>{Math.round(total * fill)}</text>
      <text x={cx} y={cy + 10} textAnchor="middle" fill="rgba(255,255,255,0.3)"
        fontSize={size * 0.085} fontFamily={FONT_MONO}>Docs</text>
    </svg>
  );
}

/* ═══════════════ StatCard ═══════════════ */
function StatCard({ label, value, sub, Icon, trend, trendPositive = true, accentColor, rgb, sparkData, danger = false, frame, start }) {
  const appear = prog(frame, start, 34);
  const countP = prog(frame, start + 8, 72);
  const shown = Math.round(value * countP);
  const draw = prog(frame, start + 16, 60);
  return (
    <GlassCard accent={`${accentColor}aa`} glow={accentColor} appear={appear}
      style={{ padding: "22px 20px 18px" }}>
      <div style={{ position: "absolute", bottom: 0, left: "10%", right: "10%", height: 56,
        background: `radial-gradient(ellipse,${accentColor}30 0%,transparent 70%)`, pointerEvents: "none" }} />
      <div style={{ position: "relative", zIndex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={{
            width: 38, height: 38, borderRadius: 11,
            background: `rgba(${rgb},0.15)`, border: `1px solid rgba(${rgb},0.32)`,
            boxShadow: `inset 0 1px 0 rgba(255,255,255,0.12), 0 0 14px rgba(${rgb},0.2)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: accentColor, flexShrink: 0,
          }}><Icon size={16} /></div>
          {trend !== undefined && (
            <span style={{
              fontSize: 10.5, fontWeight: 700, padding: "3px 8px", borderRadius: 6,
              background: trendPositive ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
              color: trendPositive ? "#22c55e" : "#ef4444",
              border: `1px solid ${trendPositive ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
              fontFamily: FONT_SANS,
            }}>{trendPositive ? "↑" : "↓"} {trend}</span>
          )}
        </div>
        <div style={{
          fontSize: 32, fontWeight: 800, letterSpacing: "-0.045em", lineHeight: 1,
          color: danger ? "#f87171" : "white", fontFamily: FONT_DISPLAY, marginBottom: 4,
          textShadow: danger ? "0 0 20px rgba(248,113,113,0.4)" : `0 0 20px rgba(${rgb},0.2)`,
        }}>{shown.toLocaleString("de-DE")}</div>
        <div style={{ fontSize: 11.5, fontWeight: 500, color: "rgba(255,255,255,0.6)", fontFamily: FONT_SANS, marginBottom: 2 }}>{label}</div>
        {sub && <div style={{ fontSize: 10.5, color: "rgba(255,255,255,0.32)", fontFamily: FONT_SANS, marginBottom: 14 }}>{sub}</div>}
        <div style={{ marginTop: 14 }}>
          <Sparkline data={sparkData} color={accentColor} w={140} h={44} draw={draw} />
        </div>
      </div>
    </GlassCard>
  );
}

/* ═══════════════ QuickAction + Kontakte ═══════════════ */
function QuickAction({ label, desc, Icon, accent, appear }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.025)",
      backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
      border: "1px solid rgba(255,255,255,0.09)",
      borderRadius: 16, padding: "15px 14px",
      boxShadow: "0 2px 16px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.12)",
      position: "relative", overflow: "hidden", boxSizing: "border-box",
      opacity: appear, transform: `translateY(${(1 - appear) * 14}px)`,
    }}>
      <div style={{ color: "rgba(255,255,255,0.55)", marginBottom: 10 }}><Icon size={17} /></div>
      <div style={{ fontSize: 12.5, fontWeight: 700, color: "rgba(255,255,255,0.88)", fontFamily: FONT_DISPLAY, marginBottom: 3, letterSpacing: "-0.01em" }}>{label}</div>
      <div style={{ fontSize: 10.5, color: "rgba(255,255,255,0.45)", fontFamily: FONT_SANS, lineHeight: 1.4 }}>{desc}</div>
    </div>
  );
}

function CustomerRow({ name, company, date, appear }) {
  const inits = name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 11, padding: "9px 8px", borderRadius: 11,
      opacity: appear, transform: `translateX(${(1 - appear) * 16}px)` }}>
      <div style={{
        width: 32, height: 32, borderRadius: 9, flexShrink: 0,
        background: "rgba(93,202,165,0.1)", border: "1px solid rgba(93,202,165,0.2)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 12, fontWeight: 700, color: ACCENT, fontFamily: FONT_DISPLAY,
      }}>{inits}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, color: "rgba(255,255,255,0.7)", fontFamily: FONT_SANS, fontWeight: 500, whiteSpace: "nowrap" }}>{name}</div>
        {company && <div style={{ fontSize: 10.5, color: "rgba(255,255,255,0.38)", fontFamily: FONT_SANS }}>{company}</div>}
      </div>
      <div style={{ fontSize: 10.5, color: "rgba(255,255,255,0.35)", fontFamily: FONT_SANS, flexShrink: 0 }}>{date}</div>
    </div>
  );
}

/* ═══════════════ Hauptkomponente ═══════════════ */
const FAKE_CUSTOMERS = [
  { name: "Max Berger", company: "Berger Elektrotechnik", date: "02.08.2026" },
  { name: "Lena Hoffmann", company: "Hoffmann Design Studio", date: "28.07.2026" },
  { name: "Jonas Weber", company: "Weber Sanitär GmbH", date: "21.07.2026" },
  { name: "Sarah Klein", company: "Klein Fotografie", date: "14.07.2026" },
  { name: "Tim Schuster", company: "Schuster IT-Service", date: "05.07.2026" },
];

const QUICK_ACTIONS = [
  { label: "Mahnungflow", desc: "Mahnung erstellen & versenden", Icon: IcoMahnung, accent: "#ef4444" },
  { label: "Mailflow", desc: "E-Mail-Antworten in Sekunden", Icon: IcoBrief, accent: "#3b82f6" },
  { label: "Angebotsflow", desc: "Angebote schnell & einfach", Icon: IcoAngebot, accent: "#22c55e" },
  { label: "E-Rechnung", desc: "Elektronische Rechnungen", Icon: IcoRechnung, accent: "#a855f7" },
];

export const DashboardVideo = ({
  firstName = "Max",
  greeting = "Guten Morgen",
  userName = "Max Berger",
  userInitial = "M",
  credits = 118,
  maxCredits = 150,
  purchasedCredits = 0,
  paidThisMonth = 12,
  sentCount = 8,
  customerCount = 47,
  overdueCount = 3,
  overdueAmount = 1240.5,
  monthlySent = [3, 5, 4, 8, 7, 12],
  months = ["Mär", "Apr", "Mai", "Jun", "Jul", "Aug"],
  dateStr = "Di., 11. Aug. 2026",
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const scale = Math.min(width / DESIGN_W, height / DESIGN_H);

  const mkSpark = (v) => (v === 0
    ? [0, 0, 0, 0, 0, 0, 0, 0]
    : [0, Math.round(v * 0.12), Math.round(v * 0.1), Math.round(v * 0.32), Math.round(v * 0.28), Math.round(v * 0.52), Math.round(v * 0.76), v]);

  const donutSegs = [
    { v: paidThisMonth, color: "#22c55e", label: "Bezahlt" },
    { v: sentCount, color: "#3b82f6", label: "Offen" },
    { v: overdueCount, color: "#ef4444", label: "Überfällig" },
  ].filter((s) => s.v > 0);

  // Pulsierender Live-Punkt (3s-Zyklus @60fps)
  const pulse = 0.6 + 0.4 * (0.5 + 0.5 * Math.sin((frame / 180) * Math.PI * 2));
  const pulseScale = 1 + 0.04 * (0.5 + 0.5 * Math.sin((frame / 180) * Math.PI * 2));

  const headerAppear = prog(frame, 46, 34);
  const donutFill = prog(frame, 161, 80);

  return (
    <AbsoluteFill style={{ background: "#06060a", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: DESIGN_W, height: DESIGN_H, position: "relative", transform: `scale(${scale})`, transformOrigin: "center", overflow: "hidden", flexShrink: 0 }}>

        <Background frame={frame} />

        <Sidebar frame={frame} userName={userName} userInitial={userInitial} totalCredits={credits + purchasedCredits} />
        <Topbar frame={frame} credits={credits} maxCredits={maxCredits} purchasedCredits={purchasedCredits} userInitial={userInitial} dateStr={dateStr} />

        {/* Content */}
        <div style={{
          position: "absolute", left: SIDEBAR_W, top: TOPBAR_H, right: 0, bottom: 0,
          padding: "28px 28px 32px", boxSizing: "border-box", overflow: "hidden",
        }}>

          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 26,
            opacity: headerAppear, transform: `translateY(${(1 - headerAppear) * 16}px)` }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5 }}>
                <span style={{ position: "relative", display: "inline-flex", width: 8, height: 8 }}>
                  <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: ACCENT,
                    opacity: pulse * 0.4, transform: `scale(${pulseScale})` }} />
                  <span style={{ borderRadius: "50%", width: 8, height: 8, background: ACCENT, display: "block",
                    boxShadow: `0 0 8px ${ACCENT}` }} />
                </span>
                <span style={{ fontSize: 10.5, fontWeight: 600, color: "rgba(93,202,165,0.7)",
                  letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: FONT_MONO }}>Live</span>
              </div>
              <h1 style={{ fontSize: 23, fontWeight: 800, fontFamily: FONT_DISPLAY, color: "white",
                letterSpacing: "-0.035em", margin: 0, marginBottom: 3 }}>
                {greeting}{firstName ? `, ${firstName}` : ""}
              </h1>
              <p style={{ fontSize: 12, color: "rgba(255,255,255,0.42)", fontFamily: FONT_SANS, margin: 0 }}>
                Hier ist deine Übersicht — alles auf einen Blick.
              </p>
            </div>
            {/* Neues Dokument (solid) */}
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "10px 20px",
              borderRadius: 11, background: `linear-gradient(135deg,${ACCENT},#2da882)`,
              color: "#0a1210", fontSize: 12.5, fontWeight: 700, fontFamily: FONT_SANS,
              boxShadow: "0 0 32px rgba(93,202,165,0.4), 0 4px 20px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.3)",
              letterSpacing: "-0.01em",
            }}>
              <IcoPlus size={13} /> Neues Dokument <span style={{ marginLeft: 1, opacity: 0.8, display: "flex" }}><IcoChevDown /></span>
            </div>
          </div>

          {/* Row 1: Stat-Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 12 }}>
            <StatCard frame={frame} start={67} label="Bezahlt diesen Monat" value={paidThisMonth}
              sub={`${paidThisMonth} Rechnung${paidThisMonth !== 1 ? "en" : ""}`}
              Icon={IcoTrendingUp} accentColor="#22c55e" rgb="34,197,94"
              trend={`+${paidThisMonth}`} trendPositive sparkData={mkSpark(paidThisMonth)} />
            <StatCard frame={frame} start={83} label="Versendet & offen" value={sentCount}
              sub={`${sentCount} ausstehend`}
              Icon={IcoAngebot} accentColor="#a855f7" rgb="168,85,247"
              trend={`${sentCount}`} trendPositive={sentCount === 0} sparkData={mkSpark(sentCount)} />
            <StatCard frame={frame} start={98} label="Aktive Kunden" value={customerCount}
              sub={`${customerCount} gespeichert`}
              Icon={IcoUsers} accentColor="#3b82f6" rgb="59,130,246"
              trend={`+${customerCount}`} trendPositive sparkData={mkSpark(customerCount)} />
            <StatCard frame={frame} start={114} label="Überfällige Posten" value={overdueCount}
              sub={overdueAmount > 0 ? `${overdueAmount.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} € offen` : `${overdueCount} Posten`}
              Icon={IcoZap} accentColor={overdueCount > 0 ? "#ef4444" : "#22c55e"} rgb={overdueCount > 0 ? "239,68,68" : "34,197,94"}
              danger={overdueCount > 0} trend={`${overdueCount}`} trendPositive={overdueCount === 0} sparkData={mkSpark(overdueCount)} />
          </div>

          {/* Row 2: AreaChart + Donut */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 12, marginBottom: 12 }}>
            <GlassCard accent={`${ACCENT}55`} appear={prog(frame, 135, 34)} style={{ padding: "22px 24px 18px" }}>
              <CH title="Versendete Rechnungen" sub="Letzte 6 Monate"
                right={
                  <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "4px 10px",
                    borderRadius: 7, background: "rgba(93,202,165,0.1)", border: "1px solid rgba(93,202,165,0.2)" }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: ACCENT, display: "inline-block", boxShadow: `0 0 6px ${ACCENT}` }} />
                    <span style={{ fontSize: 10, color: "rgba(255,255,255,0.55)", fontFamily: FONT_MONO }}>Bezahlt</span>
                  </div>
                } />
              <AreaChart values={monthlySent} months={months} frame={frame} start={166} />
            </GlassCard>

            <GlassCard appear={prog(frame, 150, 34)} style={{ padding: "22px 20px" }}>
              <CH title="Fälligkeitsstatus" sub="Alle Dokumente" />
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
                <div style={{ position: "relative" }}>
                  <div style={{ position: "absolute", inset: -8, borderRadius: "50%",
                    background: "radial-gradient(ellipse,rgba(93,202,165,0.1) 0%,transparent 70%)", pointerEvents: "none" }} />
                  <Donut segs={donutSegs} size={104} fill={donutFill} />
                </div>
                <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
                  {[
                    { color: "#22c55e", label: "Bezahlt", v: paidThisMonth, rgb: "34,197,94" },
                    { color: "#3b82f6", label: "Offen", v: sentCount, rgb: "59,130,246" },
                    { color: "#ef4444", label: "Überfällig", v: overdueCount, rgb: "239,68,68" },
                  ].map((s, i) => {
                    const rowAppear = prog(frame, 74 + i * 6, 26);
                    return (
                      <div key={s.label} style={{
                        display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 8,
                        background: s.v > 0 ? `rgba(${s.rgb},0.06)` : "transparent",
                        border: `1px solid ${s.v > 0 ? `rgba(${s.rgb},0.18)` : "transparent"}`,
                        opacity: rowAppear, transform: `translateX(${(1 - rowAppear) * 12}px)`,
                      }}>
                        <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color, flexShrink: 0,
                          boxShadow: s.v > 0 ? `0 0 6px ${s.color}70` : "none" }} />
                        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.55)", fontFamily: FONT_SANS, flex: 1 }}>{s.label}</span>
                        <span style={{ fontSize: 11, fontWeight: 600,
                          color: s.v > 0 ? "rgba(255,255,255,0.75)" : "rgba(255,255,255,0.28)",
                          fontFamily: FONT_MONO }}>{s.v}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </GlassCard>
          </div>

          {/* Row 3: Schnellaktionen + Kontakte */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <GlassCard appear={prog(frame, 176, 34)} style={{ padding: "22px 22px" }}>
              <CH title="Schnellaktionen" sub="Flow direkt starten" />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
                {QUICK_ACTIONS.map((q, i) => (
                  <QuickAction key={q.label} {...q} appear={prog(frame, 78 + i * 5, 26)} />
                ))}
              </div>
            </GlassCard>

            <GlassCard appear={prog(frame, 192, 34)} style={{ padding: "22px 22px" }}>
              <CH title="Letzte Kontakte" sub={`${customerCount} Kontakte gespeichert`}
                right={
                  <span style={{ fontSize: 11, color: ACCENT, fontFamily: FONT_SANS, opacity: 0.8,
                    borderBottom: "1px solid rgba(93,202,165,0.3)", paddingBottom: 1 }}>Alle anzeigen</span>
                } />
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {FAKE_CUSTOMERS.map((c, i) => (
                  <CustomerRow key={c.name} {...c} appear={prog(frame, 84 + i * 5, 26)} />
                ))}
              </div>
            </GlassCard>
          </div>

        </div>
      </div>
    </AbsoluteFill>
  );
};

export default DashboardVideo;
