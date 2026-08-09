import React from "react";
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate,
  staticFile, Img,
} from "remotion";
import { BRAND, logoFuer } from "./brand.js";

// ENERGETISCH: Wörter knallen einzeln rhythmisch rein (Scale-Punch).
// props: worte:["SCHLUSS","MIT","PAPIERKRAM"], palette, akzentWort (Index), logo
export const WortPop = ({
  worte = ["WORT"], palette = "dunkel", akzentWort = -1, logo = true,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const istHoch = height > width;
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const takt = 14; // Frames pro Wort — rhythmischer Beat

  const basis = istHoch ? width * 0.14 : height * 0.17;
  const logoOp = interpolate(frame - (worte.length * takt + 10), [0, 20], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{
      background: p.verlauf, justifyContent: "center", alignItems: "center",
      fontFamily: BRAND.fonts.display,
    }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: basis * 0.2,
                    justifyContent: "center", maxWidth: "85%", zIndex: 2 }}>
        {worte.map((w, i) => {
          const start = i * takt;
          const s = spring({ frame: frame - start, fps,
            config: { damping: 10, stiffness: 200, mass: 0.6 } });
          const scale = interpolate(s, [0, 1], [0.3, 1]);
          const opacity = interpolate(frame - start, [0, 5], [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const istAkzent = i === akzentWort || (akzentWort === -1 && i === worte.length - 1);
          return (
            <span key={i} style={{
              transform: `scale(${scale})`, opacity,
              fontSize: basis, fontWeight: 800,
              color: istAkzent ? p.akzent : p.text,
              textShadow: istAkzent ? `0 0 30px ${p.akzent}66` : "none",
              letterSpacing: "-0.02em", lineHeight: 1,
            }}>{w}</span>
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
