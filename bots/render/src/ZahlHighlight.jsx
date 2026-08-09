import React from "react";
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate,
  staticFile, Img,
} from "remotion";
import { BRAND, logoFuer } from "./brand.js";

// ENERGETISCH/PREMIUM-Mix: grosse Zahl zaehlt hoch, Label darunter.
// props: zielZahl:30, suffix:" Sek", vortext:"Mahnung in", nachtext:"statt 30 Minuten", palette, logo
export const ZahlHighlight = ({
  zielZahl = 30, suffix = "", vortext = "", nachtext = "",
  palette = "dunkel", logo = true,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const istHoch = height > width;
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;

  // Zahl zaehlt in den ersten 45 Frames hoch
  const zahlProg = spring({ frame, fps, config: { damping: 20, stiffness: 80 } });
  const aktuelleZahl = Math.round(interpolate(zahlProg, [0, 1], [0, zielZahl]));

  const vorOp = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  const nachOp = interpolate(frame - 50, [0, 15], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const logoOp = interpolate(frame - 75, [0, 20], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const zahlGroesse = istHoch ? width * 0.32 : height * 0.34;
  const textGroesse = istHoch ? width * 0.06 : height * 0.07;

  return (
    <AbsoluteFill style={{
      background: p.verlauf, justifyContent: "center", alignItems: "center",
      fontFamily: BRAND.fonts.display, flexDirection: "column", gap: 20,
    }}>
      {vortext ? (
        <div style={{ fontSize: textGroesse, color: p.text, opacity: vorOp,
                      fontWeight: 600, letterSpacing: "-0.01em" }}>{vortext}</div>
      ) : null}
      <div style={{ fontSize: zahlGroesse, fontWeight: 800, color: p.akzent,
                    textShadow: `0 0 50px ${p.akzent}55`, lineHeight: 1,
                    letterSpacing: "-0.03em" }}>
        {aktuelleZahl}{suffix}
      </div>
      {nachtext ? (
        <div style={{ fontSize: textGroesse, color: p.text, opacity: nachOp,
                      fontWeight: 600, letterSpacing: "-0.01em" }}>{nachtext}</div>
      ) : null}
      {logo && (
        <div style={{ position: "absolute", bottom: istHoch ? "12%" : "8%", opacity: logoOp }}>
          <Img src={staticFile(logoFuer(palette))} style={{ height: istHoch ? width * 0.06 : height * 0.06 }} />
        </div>
      )}
    </AbsoluteFill>
  );
};
