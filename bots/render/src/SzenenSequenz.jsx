import React from "react";
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate,
  staticFile, Img, Sequence,
} from "remotion";
import { BRAND, logoFuer } from "./brand.js";

// PREMIUM GLAS-LOOK v2: schneller, mehr Ebenen, knackigere Uebergaenge.
export const SzenenSequenz = ({
  szenen = ["Szene"], palette = "dunkel", logo = true,
}) => {
  const { fps, width, height } = useVideoConfig();
  const istHoch = height > width;
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const proSzene = Math.floor(300 / szenen.length);
  const frame = useCurrentFrame();

  // schneller wandernder Glow (Faktor kleiner = schneller)
  const gx = interpolate(Math.sin(frame / 28), [-1, 1], [25, 75]);
  const gy = interpolate(Math.cos(frame / 34), [-1, 1], [25, 65]);
  // zweite, gegenlaeufige Glow-Ebene
  const gx2 = interpolate(Math.cos(frame / 40), [-1, 1], [20, 80]);

  return (
    <AbsoluteFill style={{
      background: p.hintergrund, fontFamily: BRAND.fonts.display, overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(circle at ${gx}% ${gy}%, ${p.akzent}26 0%, transparent 42%),
                     radial-gradient(circle at ${gx2}% ${100-gy}%, ${p.akzent}14 0%, transparent 48%),
                     ${p.hintergrund}`,
      }} />
      {/* durchziehende Lichtlinie (diagonal), gibt Bewegung + Raffinesse */}
      <LichtStreif frame={frame} p={p} width={width} height={height} />
      {/* Grain */}
      <div style={{
        position: "absolute", inset: 0, opacity: 0.05,
        backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='100' height='100' filter='url(%23n)'/%3E%3C/svg%3E\")",
      }} />

      {szenen.map((txt, i) => (
        <Sequence key={i} from={i * proSzene} durationInFrames={proSzene + 8}>
          <GlasPanel txt={txt} p={p} fps={fps} dauer={proSzene}
            istAkzent={i === szenen.length - 1} istHoch={istHoch}
            width={width} height={height} nummer={i + 1} gesamt={szenen.length} />
        </Sequence>
      ))}

      {logo && (
        <div style={{ position: "absolute", bottom: istHoch ? "9%" : "7%",
                      width: "100%", textAlign: "center", zIndex: 10 }}>
          <Img src={staticFile(logoFuer(palette))}
               style={{ height: istHoch ? width * 0.045 : height * 0.045, opacity: 0.85 }} />
        </div>
      )}
    </AbsoluteFill>
  );
};

// durchziehender diagonaler Lichtstreif — wiederholt sich, sorgt fuer staendige Bewegung
const LichtStreif = ({ frame, p, width, height }) => {
  const zyklus = 90;
  const t = (frame % zyklus) / zyklus;
  const x = interpolate(t, [0, 1], [-30, 130]);
  return (
    <div style={{
      position: "absolute", top: "-20%", left: `${x}%`,
      width: "18%", height: "140%",
      background: `linear-gradient(105deg, transparent, ${p.akzent}12, transparent)`,
      transform: "rotate(12deg)", filter: "blur(8px)", pointerEvents: "none",
    }} />
  );
};

const GlasPanel = ({ txt, p, fps, dauer, istAkzent, istHoch, width, height, nummer, gesamt }) => {
  const frame = useCurrentFrame();

  // schnellerer, knackiger Overshoot
  const ein = spring({ frame, fps, config: { damping: 11, stiffness: 240, mass: 0.6 } });
  const aus = interpolate(frame, [dauer - 9, dauer], [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const opacity = Math.min(interpolate(frame, [0, 5], [0, 1], { extrapolateRight: "clamp" }), aus);

  // Panel kommt schneller rein, mit seitlichem Micro-Kippen
  const y = interpolate(ein, [0, 1], [istHoch ? 70 : 45, 0]);
  const panelScale = interpolate(ein, [0, 1], [0.9, 1]);
  const kippen = interpolate(ein, [0, 1], [3, 0]); // Grad, richtet sich auf

  const schweben = Math.sin(frame / 18) * 3;

  // Text schneller nach dem Panel, mit Blur-Aufloesung (raffinierter)
  const textOp = interpolate(frame, [4, 11], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const textBlur = interpolate(frame, [4, 12], [8, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const textY = interpolate(spring({ frame: frame - 4, fps, config: { damping: 16, stiffness: 160 } }), [0, 1], [12, 0]);

  const textGroesse = istHoch ? width * 0.062 : height * 0.078;
  const panelBreite = istHoch ? "82%" : "64%";
  const hell = p.text !== "#FFFFFF";

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <div style={{
        transform: `translateY(${y + schweben}px) scale(${panelScale}) rotate(${kippen}deg)`,
        opacity,
        width: panelBreite,
        padding: istHoch ? "8% 6%" : "5% 5%",
        borderRadius: 28,
        background: hell ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.06)",
        border: `1px solid ${hell ? "rgba(255,255,255,0.7)" : "rgba(255,255,255,0.14)"}`,
        backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)",
        boxShadow: `0 20px 60px rgba(0,0,0,0.35),
                    inset 0 1px 1px ${hell ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.15)"},
                    0 0 50px ${p.akzent}22`,
        position: "relative",
      }}>
        <div style={{
          position: "absolute", top: 0, left: "12%", right: "12%", height: 1,
          background: `linear-gradient(90deg, transparent, ${p.akzent}, transparent)`,
          opacity: 0.7,
        }} />
        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginBottom: istHoch ? 22 : 16 }}>
          {Array.from({ length: gesamt }).map((_, k) => (
            <div key={k} style={{
              width: k === nummer - 1 ? 22 : 6, height: 6, borderRadius: 3,
              background: k === nummer - 1 ? p.akzent : `${p.text}33`,
            }} />
          ))}
        </div>
        <div style={{
          transform: `translateY(${textY}px)`, opacity: textOp,
          filter: `blur(${textBlur}px)`,
          fontSize: textGroesse, fontWeight: istAkzent ? 800 : 600,
          color: istAkzent ? p.akzent : p.text,
          textShadow: istAkzent ? `0 0 30px ${p.akzent}44` : "none",
          textAlign: "center", lineHeight: 1.15, letterSpacing: "-0.02em",
        }}>{txt}</div>
      </div>
    </AbsoluteFill>
  );
};
