// logo-outro.jsx — MARKEN-OUTRO im simo-Stil
//
// Baut auf der Bewegung aus marken-intro auf (die Rui besser gefiel als der
// Lichtstrahl-Ansatz): Das Logo RAST ins Bild mit geschwindigkeitsgekoppeltem
// Motion Blur, bremst weich ab, und der Claim legt sich per Maske frei —
// waehrend das Logo dabei leicht nach hinten ruecht.
//
// Unterschied zum Intro: Es endet in RUHE statt weiterzulaufen. Nach dem
// Claim bleibt alles stehen und atmet nur noch minimal — passend fuers Ende.
//
//   0,0-0,7s  Logo rast von rechts herein, bremst ab (Motion Blur)
//   0,7-1,0s  minimales Nachschwingen
//   0,9-1,8s  Claim legt sich per Maske frei, Logo rueckt dabei nach hinten
//   ab 1,8s   ruhiger Ausklang: Atmen, Partikel, wandernder Glow
//
// props: claim, claimAkzent

import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing, Img, staticFile } from "remotion";
import { BRAND, logoFuer } from "../brand.js";

export const meta = {
  dauerSek: 4,
  defaultProps: { claim: "Bürokram?", claimAkzent: "Erledigt." },
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

// Geschwindigkeits-gekoppelter Motion Blur — das Praegende an dieser Bewegung:
// je schneller sich etwas bewegt, desto staerker die Unschaerfe.
function mitBlur(fn, frame, faktor = 0.34, max = 24) {
  const jetzt = fn(frame), davor = fn(frame - 1);
  return { wert: jetzt, blur: Math.min(max, Math.abs(jetzt - davor) * faktor) };
}

function partikel(anzahl, seed) {
  let a = seed >>> 0;
  const rnd = () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return Array.from({ length: anzahl }, () => ({
    x: rnd(), y: rnd(), r: 1 + rnd() * 2.2,
    tiefe: 0.3 + rnd() * 0.7, phase: rnd() * Math.PI * 2, speed: 0.4 + rnd() * 0.9,
  }));
}

export const Komponente = ({
  palette = "dunkel",
  claim = "Bürokram?",
  claimAkzent = "Erledigt.",
}) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const pts = React.useMemo(() => partikel(30, 44021), []);

  /* ── Logo rast herein (wie im Intro) ── */
  const logoX = (f) => interpolate(f, [6, 62], [W * 0.42, 0],
    { easing: Easing.out(Easing.cubic), ...clamp });
  const lx = mitBlur(logoX, frame);
  const logoScaleIn = interpolate(frame, [6, 70], [1.5, 1],
    { easing: Easing.out(Easing.cubic), ...clamp });
  const logoOp = interpolate(frame, [4, 26], [0, 1], clamp);
  // minimales Nachschwingen nach dem Abbremsen
  const nach = Math.sin(Math.max(0, frame - 70) / 26) * 1.5;

  /* ── Gruppen-Choreografie: Logo rueckt zurueck, wenn der Claim kommt ── */
  const oeffnen = interpolate(frame, [86, 176], [0, 1],
    { easing: Easing.inOut(Easing.cubic), ...clamp });

  /* ── Claim legt sich per Maske frei ── */
  const reveal = interpolate(frame, [86, 174], [0, 1],
    { easing: Easing.inOut(Easing.cubic), ...clamp });
  const claimOp = interpolate(frame, [84, 98], [0, 1], clamp);

  /* ── Ruhiger Ausklang ── */
  const leben = Math.max(0, frame - 178);
  const atem = 1 + Math.sin(leben / 54) * 0.007;
  const schweben = Math.sin(leben / 48) * 2.2;

  /* ── SCHLUSSPHASE: damit die letzten Sekunden nicht tot sind ──
     Eine sehr langsame Kamerafahrt laeuft ueber die GESAMTE Dauer weiter,
     ein zweiter Lichtsweep zieht spaet durchs Bild, HUD-Ecken bauen sich auf. */
  const camZoom = interpolate(frame, [0, 240], [1.0, 1.045],
    { easing: Easing.inOut(Easing.ease), ...clamp });
  const camDrift = interpolate(frame, [0, 240], [0, -H * 0.018], clamp);
  const sweepSpaet = interpolate(frame, [150, 226], [-25, 125],
    { easing: Easing.inOut(Easing.cubic), ...clamp });
  const hud = interpolate(frame, [162, 208], [0, 0.36], clamp);

  /* ── Hintergrund ── */
  const glowX = 48 + Math.sin(frame / 92) * 8;
  const glowY = 46 + Math.cos(frame / 108) * 6;
  const glowPeak = interpolate(frame, [6, 62, 180], [0.45, 1, 0.7], clamp);

  const logoH = H * 0.155;

  return (
    <AbsoluteFill style={{ background: "#05070a", overflow: "hidden" }}>

      {/* Hintergrund mit wanderndem Marken-Glow */}
      <AbsoluteFill style={{
        background: `radial-gradient(ellipse 64% 60% at ${glowX}% ${glowY}%,
                     ${p.akzent}${Math.round(glowPeak * 36).toString(16).padStart(2, "0")} 0%,
                     transparent 62%),
                     linear-gradient(165deg, #0d141b 0%, #05070a 100%)`,
      }} />

      {/* Partikel */}
      <svg width={W} height={H} style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
        {pts.map((pt, i) => {
          const drift = Math.sin(frame / (48 / pt.speed) + pt.phase) * 15 * pt.tiefe;
          const px = (pt.x * W + drift) % W;
          const py = (pt.y * H - frame * pt.speed * pt.tiefe * 0.2 + H) % H;
          const op = (0.1 + pt.tiefe * 0.28) * interpolate(frame, [10, 60], [0, 1], clamp);
          return <circle key={i} cx={px} cy={py} r={pt.r * pt.tiefe}
            fill={i % 4 === 0 ? p.akzent : "#9fd4e8"} opacity={op} />;
        })}
      </svg>

      {/* ── Logo + Claim als EINE Gruppe ── */}
      <AbsoluteFill style={{
        justifyContent: "center", alignItems: "center",
        perspective: `${W}px`,
      }}>
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: H * (0.028 + oeffnen * 0.038),
          transform: `translateY(${schweben + camDrift}px) scale(${camZoom})`,
          transformStyle: "preserve-3d",
        }}>
          {/* Logo — rast herein, rueckt beim Claim nach hinten */}
          <div style={{
            opacity: logoOp * (1 - oeffnen * 0.2),
            transform: `translateX(${lx.wert}px) translateY(${nach}px) ` +
                       `scale(${logoScaleIn * atem * (1 - oeffnen * 0.22)}) ` +
                       `translateZ(${-oeffnen * 110}px)`,
            filter: lx.blur > 0.5 ? `blur(${lx.blur.toFixed(1)}px)` : "none",
            willChange: "transform, filter",
          }}>
            <Img src={staticFile(logoFuer(palette))}
              style={{ height: logoH, display: "block",
                filter: `drop-shadow(0 0 ${28 + glowPeak * 18}px ${p.akzent}55)` }} />
          </div>

          {/* Claim in Sans/Serif-Mischung, per Maske freigelegt */}
          <div style={{ position: "relative", opacity: claimOp }}>
            <div style={{
              display: "flex", alignItems: "baseline", gap: H * 0.014, whiteSpace: "nowrap",
              WebkitMaskImage: `linear-gradient(90deg, #000 0%, #000 ${reveal * 100}%,
                                transparent ${Math.min(100, reveal * 100 + 5)}%, transparent 100%)`,
              maskImage: `linear-gradient(90deg, #000 0%, #000 ${reveal * 100}%,
                          transparent ${Math.min(100, reveal * 100 + 5)}%, transparent 100%)`,
            }}>
              <span style={{
                fontFamily: BRAND.fonts.display, fontSize: H * 0.052, fontWeight: 700,
                color: "#FFFFFF", letterSpacing: "-0.03em",
              }}>{claim}</span>
              <span style={{
                fontFamily: BRAND.fonts.akzent, fontStyle: "italic",
                fontSize: H * 0.056, fontWeight: 400,
                color: p.akzent, letterSpacing: "-0.01em",
                textShadow: `0 0 30px ${p.akzent}44`,
              }}>{claimAkzent}</span>
            </div>
            {reveal > 0.02 && reveal < 0.98 && (
              <div style={{
                position: "absolute", top: "-16%", bottom: "-16%",
                left: `${reveal * 100}%`, width: 2.5,
                background: `linear-gradient(180deg, transparent, ${p.akzent}, transparent)`,
                boxShadow: `0 0 20px ${p.akzent}, 0 0 44px ${p.akzent}88`,
              }} />
            )}
          </div>
        </div>
      </AbsoluteFill>

      {/* Spaeter Licht-Sweep — belebt die Schlussphase */}
      <div style={{
        position: "absolute", top: "-20%", left: `${sweepSpaet}%`,
        width: "18%", height: "140%",
        background: `linear-gradient(100deg, transparent, ${p.akzent}1c, #ffffff12, transparent)`,
        transform: "skewX(-16deg)", filter: "blur(16px)", pointerEvents: "none",
      }} />

      {/* HUD-Ecken, bauen sich zum Schluss auf */}
      {(() => {
        const m = H * 0.075, len = H * 0.05;
        const ecke = (top, left) => (
          <div key={`${top}${left}`} style={{
            position: "absolute",
            top: top ? m : undefined, bottom: top ? undefined : m,
            left: left ? m : undefined, right: left ? undefined : m,
            width: len, height: len, opacity: hud,
            borderTop: top ? `2px solid ${p.akzent}` : "none",
            borderBottom: top ? "none" : `2px solid ${p.akzent}`,
            borderLeft: left ? `2px solid ${p.akzent}` : "none",
            borderRight: left ? "none" : `2px solid ${p.akzent}`,
          }} />
        );
        return <>{ecke(true, true)}{ecke(true, false)}{ecke(false, true)}{ecke(false, false)}</>;
      })()}

      {/* Vignette */}
      <AbsoluteFill style={{
        background: "radial-gradient(ellipse at 50% 50%, transparent 46%, rgba(0,0,0,0.6) 100%)",
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
};

export default Komponente;
