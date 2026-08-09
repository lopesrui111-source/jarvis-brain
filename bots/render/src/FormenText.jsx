import React from "react";
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate,
  staticFile, Img,
} from "remotion";
import { BRAND, logoFuer } from "./brand.js";

// PREMIUM: geometrische Elemente (Linien, Kreis in Akzent) bewegen sich mit dem Text.
// Motion-Design-Look mit bewegten Formen.
// props: zeilen:["Weniger Aufwand","mehr Zeit fürs Wesentliche"], palette, logo
export const FormenText = ({
  zeilen = ["Text"], palette = "dunkel", logo = true,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const istHoch = height > width;
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const basis = istHoch ? width * 0.09 : height * 0.12;

  // bewegte Linie, die von links reinfaehrt
  const linieProg = spring({ frame, fps, config: { damping: 20, stiffness: 70 } });
  const linieBreite = interpolate(linieProg, [0, 1], [0, istHoch ? width * 0.5 : width * 0.25]);

  // rotierender Kreis-Akzent
  const rot = interpolate(frame, [0, 300], [0, 180]);
  const kreisScale = spring({ frame: frame - 8, fps, config: { damping: 12, stiffness: 100 } });

  const logoOp = interpolate(frame - 60, [0, 20], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{
      background: p.verlauf, justifyContent: "center", alignItems: "center",
      fontFamily: BRAND.fonts.display,
    }}>
      {/* rotierender Ring-Akzent hinter dem Text */}
      <div style={{
        position: "absolute",
        width: istHoch ? width * 0.7 : height * 0.7,
        height: istHoch ? width * 0.7 : height * 0.7,
        border: `3px solid ${p.akzent}`, borderRadius: "50%",
        opacity: 0.15 * kreisScale,
        transform: `rotate(${rot}deg) scale(${kreisScale})`,
        borderTopColor: "transparent", borderRightColor: "transparent",
      }} />

      <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
                    gap: basis * 0.2, zIndex: 2 }}>
        {/* Akzent-Linie ueber dem Text */}
        <div style={{ width: linieBreite, height: 5, background: p.akzent,
                      borderRadius: 3, boxShadow: `0 0 20px ${p.akzent}88`,
                      marginBottom: basis * 0.15 }} />
        {zeilen.map((zeile, i) => {
          const start = i * 12 + 6;
          const s = spring({ frame: frame - start, fps,
            config: { damping: 16, stiffness: 110 } });
          const x = interpolate(s, [0, 1], [-30, 0]);
          const opacity = interpolate(frame - start, [0, 10], [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={i} style={{
              transform: `translateX(${x}px)`, opacity,
              fontSize: basis, fontWeight: 700, color: p.text,
              letterSpacing: "-0.02em", textAlign: "center", lineHeight: 1.1,
            }}>{zeile}</div>
          );
        })}
      </div>
      {logo && (
        <div style={{ position: "absolute", bottom: istHoch ? "12%" : "8%", opacity: logoOp, zIndex: 3 }}>
          <Img src={staticFile(logoFuer(palette))} style={{ height: istHoch ? width * 0.06 : height * 0.06 }} />
        </div>
      )}
    </AbsoluteFill>
  );
};
