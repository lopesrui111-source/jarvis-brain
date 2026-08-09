import React from "react";
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, staticFile, Img, Sequence,
} from "remotion";
import { BRAND, logoFuer } from "./brand.js";
import { segmenteAufbereiten, segmentStarts } from "./story_helper.js";
import { EXPO, TextBlock, Surface, useKameraPush, FlashOverlay, StoryHintergrund } from "./motion_helpers.jsx";

// custom-Komponenten dynamisch laden (wie in Root) — Map name -> Komponente.
// Remotion buendelt bei jedem Render neu, daher sind neue custom-Dateien sofort da.
let CUSTOM_MAP = {};
try {
  const ctx = require.context("./custom", false, /\.jsx$/);
  ctx.keys().forEach((k) => {
    try {
      const mod = ctx(k);
      const name = k.replace("./", "").replace(".jsx", "");
      CUSTOM_MAP[name] = mod.Komponente || mod.default;
    } catch (e) { /* fehlerhafte custom-Datei ueberspringen */ }
  });
} catch (e) { /* kein custom-Ordner */ }

// ═══ STORY nach Referenz-DNA ═══
// harte Cuts, metronomisch, easeOutExpo, 1 Pivot moeglich.
// Segmente koennen einfache Stile ODER reiche custom-Komponenten sein.
export const StorySequenz = ({ segmente = [], palette = "dunkel", logo = true }) => {
  const { width, height } = useVideoConfig();
  const istHoch = height > width;
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const segs = segmenteAufbereiten(segmente);
  const starts = segmentStarts(segs);

  return (
    <AbsoluteFill style={{ background: p.hintergrund, fontFamily: BRAND.fonts.display, overflow: "hidden" }}>
      <StoryHintergrund p={p} />

      {segs.map((seg, i) => (
        <Sequence key={i} from={starts[i]} durationInFrames={seg.frames}>
          <SegmentRenderer seg={seg} p={p} istHoch={istHoch} width={width} height={height} palette={palette} />
        </Sequence>
      ))}

      {logo && (
        <div style={{ position: "absolute", bottom: istHoch ? "8%" : "6%", width: "100%",
          textAlign: "center", zIndex: 20 }}>
          <Img src={staticFile(logoFuer(palette))}
            style={{ height: istHoch ? width * 0.045 : height * 0.045, opacity: 0.85 }} />
        </div>
      )}
    </AbsoluteFill>
  );
};

const SegmentRenderer = ({ seg, p, istHoch, width, height, palette }) => {
  const frame = useCurrentFrame();
  const istCustom = typeof seg.stil === "string" && seg.stil.startsWith("custom-");

  const dissolveOp = seg.uebergang === "dissolve"
    ? interpolate(frame, [0, 12], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : 1;

  // custom-Komponente fuellt den Frame selbst (eigener BG/Layout), kein zentrierter Wrapper, kein Push
  if (istCustom) {
    const name = seg.stil.replace("custom-", "");
    const Comp = CUSTOM_MAP[name];
    return (
      <AbsoluteFill style={{ opacity: dissolveOp }}>
        {Comp
          ? <Comp palette={palette} {...(seg.props || {})} />
          : <FehlendHinweis name={seg.stil} p={p} />}
        {seg.uebergang === "flash" && <FlashOverlay farbe={p.akzent} />}
      </AbsoluteFill>
    );
  }

  // einfache Stile: zentriert + Kamera-Push
  const push = useKameraPush(seg.frames);
  const hell = p.text !== "#FFFFFF";
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: dissolveOp }}>
      <div style={{ transform: `scale(${push})`, width: "100%", height: "100%",
        display: "flex", justifyContent: "center", alignItems: "center" }}>
        <SegmentInhalt seg={seg} p={p} istHoch={istHoch} width={width} height={height} hell={hell} />
      </div>
      {seg.uebergang === "flash" && <FlashOverlay farbe={p.akzent} />}
    </AbsoluteFill>
  );
};

const FehlendHinweis = ({ name, p }) => (
  <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", background: p.hintergrund }}>
    <div style={{ color: p.akzent, fontSize: 32, fontFamily: BRAND.fonts.display }}>
      Komponente „{name}" nicht gefunden
    </div>
  </AbsoluteFill>
);

const SegmentInhalt = ({ seg, p, istHoch, width, height, hell }) => {
  const { stil, props } = seg;
  if (stil === "zahl")    return <ZahlSeg props={props} p={p} istHoch={istHoch} width={width} height={height} hell={hell} surface={seg.surface} />;
  if (stil === "wortpop") return <WortPopSeg props={props} p={p} istHoch={istHoch} width={width} height={height} hell={hell} surface={seg.surface} />;
  return <AussageSeg props={props} p={p} istHoch={istHoch} width={width} height={height} hell={hell} surface={seg.surface} />;
};

const AussageSeg = ({ props, p, istHoch, width, height, hell, surface }) => {
  const txt = (props.szenen && props.szenen[0]) || (props.zeilen && props.zeilen.join(" ")) || props.text || "Aussage";
  const istAkzent = !!props.akzent;
  const groesse = istHoch ? width * 0.06 : height * 0.075;
  const breite = istHoch ? "82%" : "62%";
  const padding = istHoch ? "9% 7%" : "6% 6%";
  return (
    <Surface art={surface} akzent={p.akzent} hell={hell} breite={breite} padding={padding}>
      <TextBlock text={txt} groesse={groesse} delay={4}
        farbe={istAkzent ? p.akzent : p.text}
        gewicht={istAkzent ? 800 : 600}
        glow={istAkzent ? `${p.akzent}44` : null} />
    </Surface>
  );
};

const ZahlSeg = ({ props, p, istHoch, width, height, hell, surface }) => {
  const frame = useCurrentFrame();
  const ziel = props.zielZahl ?? 30;
  const suffix = props.suffix || "";
  const vor = props.vortext || "";
  const nach = props.nachtext || "";
  const prog = interpolate(frame, [4, 40], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const zahl = Math.round(prog * ziel);
  const zg = istHoch ? width * 0.26 : height * 0.30;
  const tg = istHoch ? width * 0.05 : height * 0.06;
  const breite = istHoch ? "80%" : "58%";
  const padding = istHoch ? "10% 6%" : "7% 6%";
  return (
    <Surface art={surface} akzent={p.akzent} hell={hell} breite={breite} padding={padding}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        {vor ? <TextBlock text={vor} groesse={tg} farbe={p.text} delay={4} blur={false} /> : null}
        <div style={{ fontSize: zg, fontWeight: 800, color: p.akzent, lineHeight: 1,
          letterSpacing: "-0.03em", textShadow: `0 0 50px ${p.akzent}55`, fontFamily: BRAND.fonts.display }}>
          {zahl}{suffix}
        </div>
        {nach ? <TextBlock text={nach} groesse={tg} farbe={p.text} delay={40} blur={false} /> : null}
      </div>
    </Surface>
  );
};

const WortPopSeg = ({ props, p, istHoch, width, height, hell }) => {
  const frame = useCurrentFrame();
  const worte = props.worte || ["WORT"];
  const akzent = props.akzentWort ?? -1;
  const basis = istHoch ? width * 0.1 : height * 0.13;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: basis * 0.28 }}>
      {worte.map((w, i) => {
        const f = frame - i * 8;
        const op = interpolate(f, [0, 10], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const y = interpolate(f, [0, 14], [12, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const b = interpolate(f, [0, 12], [8, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const ak = i === akzent || (akzent === -1 && i === worte.length - 1);
        return (
          <div key={i} style={{
            opacity: op, transform: `translateY(${y}px)`, filter: `blur(${b}px)`,
            fontSize: basis, fontWeight: 800, letterSpacing: "-0.02em", lineHeight: 1,
            color: ak ? p.akzent : p.text,
            textShadow: ak ? `0 0 30px ${p.akzent}55` : "none",
            padding: ak ? `${basis * 0.12}px ${basis * 0.3}px` : 0,
            borderRadius: 999,
            background: ak ? (hell ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.06)") : "transparent",
            border: ak ? `1px solid ${p.akzent}44` : "none",
            backdropFilter: ak ? "blur(18px)" : "none",
            WebkitBackdropFilter: ak ? "blur(18px)" : "none",
          }}>{w}</div>
        );
      })}
    </div>
  );
};
