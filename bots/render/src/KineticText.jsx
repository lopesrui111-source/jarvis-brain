import React from "react";
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig,
  spring, interpolate, staticFile, Img,
} from "remotion";
import { BRAND, logoFuer } from "./brand.js";

// Kinetic Typography mit Büroflow-Brandkit.
// props:
//   zeilen:  ["MAHNUNG", "in 30 Sekunden", ...]
//   palette: "dunkel" | "hell" | "gruen" | "limette"   (Standard: dunkel)
//   akzentZeile: Index der hervorgehobenen Zeile (Standard: 1)
//   logo:    true/false  (Logo unten einblenden)
export const KineticText = ({
  zeilen = ["TEXT"],
  palette = "dunkel",
  akzentZeile = 1,
  logo = true,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const istHoch = height > width;
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;

  const drift = interpolate(frame, [0, 300], [0, 40]);
  const glowPuls = interpolate(Math.sin(frame / 30), [-1, 1], [0.25, 0.5]);
  const basisGroesse = istHoch ? width * 0.11 : height * 0.14;

  const logoStart = 40;
  const logoOpacity = interpolate(frame - logoStart, [0, 20], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: p.verlauf,
        justifyContent: "center",
        alignItems: "center",
        fontFamily: BRAND.fonts.display,
      }}
    >
      <div
        style={{
          position: "absolute",
          width: width * 0.8, height: width * 0.8,
          top: `calc(40% - ${width * 0.4}px + ${drift}px)`,
          left: "10%",
          background: `radial-gradient(circle, ${p.akzentDim} 0%, transparent 70%)`,
          opacity: glowPuls,
          filter: "blur(40px)",
        }}
      />

      <div style={{ display: "flex", flexDirection: "column",
                    gap: basisGroesse * 0.25, zIndex: 2 }}>
        {zeilen.map((zeile, i) => {
          const start = i * 12;
          const s = spring({ frame: frame - start, fps,
            config: { damping: 14, stiffness: 120, mass: 0.8 } });
          const opacity = interpolate(frame - start, [0, 10], [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const y = interpolate(s, [0, 1], [40, 0]);
          const scale = interpolate(s, [0, 1], [0.85, 1]);
          const istAkzent = i === akzentZeile;

          return (
            <div key={i} style={{
              transform: `translateY(${y}px) scale(${scale})`,
              opacity,
              fontSize: istAkzent ? basisGroesse * 1.15 : basisGroesse,
              fontWeight: istAkzent ? 800 : 700,
              color: istAkzent ? p.akzent : p.text,
              textShadow: istAkzent ? `0 0 30px ${p.akzent}66` : "none",
              letterSpacing: "-0.02em",
              textAlign: "center",
              lineHeight: 1,
            }}>
              {zeile}
            </div>
          );
        })}
      </div>

      {logo && (
        <div style={{
          position: "absolute",
          bottom: istHoch ? "12%" : "8%",
          opacity: logoOpacity,
          zIndex: 3,
        }}>
          <Img
            src={staticFile(logoFuer(palette))}
            style={{ height: istHoch ? width * 0.06 : height * 0.06 }}
          />
        </div>
      )}
    </AbsoluteFill>
  );
};
