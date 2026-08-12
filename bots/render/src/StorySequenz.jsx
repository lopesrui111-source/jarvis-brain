import React from "react";
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, staticFile, Img, Audio, Sequence, OffthreadVideo, spring,
} from "remotion";
import { TransitionSeries, springTiming, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { BRAND, logoFuer } from "./brand.js";
import { segmenteAufbereiten, istFliessend, UEBERGANG_FRAMES } from "./story_helper.js";
import { EXPO, TextBlock, Surface, useKameraPush, FlashOverlay, StoryHintergrund } from "./motion_helpers.jsx";

// custom-Komponenten dynamisch laden
let CUSTOM_MAP = {};
try {
  const ctx = require.context("./custom", false, /\.jsx$/);
  ctx.keys().forEach((k) => {
    try {
      const mod = ctx(k);
      const name = k.replace("./", "").replace(".jsx", "");
      CUSTOM_MAP[name] = mod.Komponente || mod.default;
    } catch (e) {}
  });
} catch (e) {}

// Uebergang-String -> Remotion-Presentation
function presentation(uebergang, width, height) {
  if (uebergang === "fade") return fade();
  if (uebergang === "slide-links")  return slide({ direction: "from-right" });
  if (uebergang === "slide-rechts") return slide({ direction: "from-left" });
  if (uebergang === "slide-hoch")   return slide({ direction: "from-bottom" });
  if (uebergang === "slide-runter") return slide({ direction: "from-top" });
  if (uebergang === "wipe")     return wipe({ direction: "from-right" });
  return fade(); // Fallback fuer fliessende
}

export const StorySequenz = ({ segmente = [], palette = "dunkel", logo = true, sfx = [], musik = "", musik_lautstaerke = 0.25 }) => {
  const { width, height } = useVideoConfig();
  const istHoch = height > width;
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const segs = segmenteAufbereiten(segmente);

  return (
    <AbsoluteFill style={{ background: p.hintergrund, fontFamily: BRAND.fonts.display, overflow: "hidden" }}>
      {/* Hintergrund-Musik, durchgehend, leise */}
      {musik ? <Audio src={staticFile(musik)} volume={musik_lautstaerke} /> : null}

      {/* GLOBALER Hintergrund-Blob — laeuft EINMAL fuer das gesamte Video,
          nicht pro Segment. Dadurch wandert er kontinuierlich statt bei
          jedem Cut an eine neue Zufallsposition zu springen. Einfache
          Segmente lassen ihn durchscheinen (transparenter BG), custom-
          Komponenten uebermalen ihn mit ihrem eigenen Look. */}
      <StoryHintergrund p={p} />

      <TransitionSeries>
        {segs.map((seg, i) => {
          const el = [];
          const weich = i > 0 && istFliessend(seg.uebergang);
          // Uebergang VOR diesem Segment (ausser dem ersten)
          if (weich) {
            el.push(
              <TransitionSeries.Transition key={`t${i}`}
                timing={springTiming({ config: { damping: 200, stiffness: 200 }, durationInFrames: UEBERGANG_FRAMES })}
                presentation={presentation(seg.uebergang, width, height)} />
            );
          }
          el.push(
            <TransitionSeries.Sequence key={`s${i}`} durationInFrames={seg.frames}>
              <SegmentRenderer seg={seg} p={p} istHoch={istHoch} width={width} height={height} palette={palette} weich={weich} />
            </TransitionSeries.Sequence>
          );
          return el;
        })}
      </TransitionSeries>

      {/* SFX-Spuren: jeder Effekt startet bei seinem Frame */}
      {(sfx || []).map((s, i) => (
        <Sequence key={`sfx${i}`} from={Math.max(0, s.frame || 0)}>
          <Audio src={staticFile(s.datei)} volume={s.lautstaerke ?? 0.7} />
        </Sequence>
      ))}

      {logo && (
        <div style={{ position: "absolute", bottom: istHoch ? "8%" : "6%", width: "100%",
          textAlign: "center", zIndex: 30 }}>
          <Img src={staticFile(logoFuer(palette))}
            style={{ height: istHoch ? width * 0.045 : height * 0.045, opacity: 0.85 }} />
        </div>
      )}
    </AbsoluteFill>
  );
};

const SegmentRenderer = ({ seg, p, istHoch, width, height, palette, weich }) => {
  const istCustom = typeof seg.stil === "string" && seg.stil.startsWith("custom-");

  if (istCustom) {
    const name = seg.stil.replace("custom-", "");
    const Comp = CUSTOM_MAP[name];
    return (
      <AbsoluteFill>
        {Comp ? <Comp palette={palette} {...(seg.props || {})} /> : <FehlendHinweis name={seg.stil} p={p} />}
        {seg.uebergang === "flash" && <FlashOverlay farbe={p.akzent} />}
      </AbsoluteFill>
    );
  }

  // einfache Stile: TRANSPARENTER Hintergrund (der globale Blob scheint
  // durch) + zentriert + Kamera-Push. Bei weichem Einstieg startet der
  // Push NICHT bei 1.0 neu (das riss den Puls bei jedem Cut ab), sondern
  // knapp ueber 1.0 — wirkt wie eine fortlaufende Kamera statt Reset.
  const push = useKameraPush(seg.frames, weich);
  const hell = p.text !== "#FFFFFF";
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div style={{ transform: `scale(${push})`, width: "100%", height: "100%",
          display: "flex", justifyContent: "center", alignItems: "center" }}>
          <SegmentInhalt seg={seg} p={p} istHoch={istHoch} width={width} height={height} hell={hell} weich={weich} />
        </div>
      </AbsoluteFill>
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

const SegmentInhalt = ({ seg, p, istHoch, width, height, hell, weich }) => {
  const { stil, props } = seg;
  if (stil === "ui-clip") return <UiClipSeg props={{ ...props, __frames: seg.frames }} p={p} istHoch={istHoch} width={width} height={height} hell={hell} />;
  if (stil === "zahl")    return <ZahlSeg props={props} p={p} istHoch={istHoch} width={width} height={height} hell={hell} surface={seg.surface} weich={weich} />;
  if (stil === "wortpop") return <WortPopSeg props={props} p={p} istHoch={istHoch} width={width} height={height} hell={hell} weich={weich} />;
  if (stil === "formen")  return <FormenSeg props={props} p={p} istHoch={istHoch} width={width} height={height} weich={weich} />;
  if (stil === "kinetic") return <KineticSeg props={props} p={p} istHoch={istHoch} width={width} height={height} weich={weich} />;
  return <AussageSeg props={props} p={p} istHoch={istHoch} width={width} height={height} hell={hell} surface={seg.surface} weich={weich} />;
};

// ── UI-CLIP: echtes Buroflow-Material (Screenshot/Recording) schoen gerahmt + Ken-Burns ──
// props: datei ("ui/dashboard.png" oder .mp4), rahmen ("browser"|"phone"|"plain"), label, bewegung ("zoom-in"|"pan-up"|"none")
const UiClipSeg = ({ props, p, istHoch, width, height, hell }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const datei = props.datei || "";
  const rahmen = props.rahmen || "browser";
  const label = props.label || "";
  const bewegung = props.bewegung || "zoom-in";
  const istVideo = datei.toLowerCase().endsWith(".mp4") || datei.toLowerCase().endsWith(".webm") || datei.toLowerCase().endsWith(".mov");

  // Einblendung
  const op = interpolate(frame, [0, 10], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const einY = interpolate(frame, [0, 16], [24, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // Ken-Burns (damit ein statischer Screenshot lebt)
  const dur = Math.max(60, props.__frames || 150);
  let kbScale = 1, kbX = 0, kbY = 0;
  if (bewegung === "zoom-in") kbScale = interpolate(frame, [0, dur], [1.0, 1.03], { extrapolateRight: "clamp" });
  else if (bewegung === "pan-up") kbY = interpolate(frame, [0, dur], [0, -6], { extrapolateRight: "clamp" });

  // Rahmen: bei Hochformat schmaler, bei Querformat breit (Dashboard soll gross/scharf sein)
  const rahmenBreite = istHoch ? width * 0.9 : width * 0.72;

  // Frame-Styles
  const browserBar = (
    <div style={{ height: istHoch ? 34 : 30, background: "#1c1f26", display: "flex", alignItems: "center",
      paddingLeft: 16, gap: 8, borderTopLeftRadius: 14, borderTopRightRadius: 14 }}>
      {["#ff5f57", "#febc2e", "#28c840"].map((c, i) => (
        <div key={i} style={{ width: 11, height: 11, borderRadius: "50%", background: c }} />
      ))}
      <div style={{ flex: 1, textAlign: "center", color: "rgba(255,255,255,0.4)", fontSize: 13,
        marginRight: 40, fontFamily: BRAND.fonts.display }}>buroflow.de</div>
    </div>
  );

  const medien = istVideo
    ? <OffthreadVideo src={staticFile(datei)} style={{ width: "100%", display: "block" }} muted />
    : <Img src={staticFile(datei)} style={{ width: "100%", display: "block" }} />;

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <div style={{ opacity: op, transform: `translateY(${einY}px)`, width: rahmenBreite,
        display: "flex", flexDirection: "column", alignItems: "center", gap: istHoch ? 24 : 18 }}>
        {label ? (
          <div style={{ fontSize: istHoch ? width * 0.05 : height * 0.06, fontWeight: 700,
            color: p.text, letterSpacing: "-0.02em", textAlign: "center", fontFamily: BRAND.fonts.display }}>
            {label}
          </div>
        ) : null}
        <div style={{ width: "100%", borderRadius: 16, overflow: "hidden",
          boxShadow: `0 30px 80px rgba(0,0,0,0.45), 0 0 60px ${p.akzent}18`,
          border: rahmen === "plain" ? `1px solid ${hell ? "rgba(0,0,0,0.1)" : "rgba(255,255,255,0.12)"}` : "none",
          transform: `scale(${kbScale}) translate(${kbX}px, ${kbY}px)` }}>
          {rahmen === "browser" ? browserBar : null}
          <div style={{ overflow: "hidden", background: "#000" }}>{medien}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const AussageSeg = ({ props, p, istHoch, width, height, hell, surface, weich }) => {
  const txt = (props.szenen && props.szenen[0]) || (props.zeilen && props.zeilen.join(" ")) || props.text || "Aussage";
  const istAkzent = !!props.akzent;
  const groesse = istHoch ? width * 0.06 : height * 0.075;
  const breite = istHoch ? "82%" : "62%";
  const padding = istHoch ? "9% 7%" : "6% 6%";
  return (
    <Surface art={surface} akzent={p.akzent} hell={hell} breite={breite} padding={padding} sofort={weich}>
      <TextBlock text={txt} groesse={groesse} delay={weich ? 0 : 4} sofort={weich}
        farbe={istAkzent ? p.akzent : p.text}
        gewicht={istAkzent ? 800 : 600}
        glow={istAkzent ? `${p.akzent}44` : null} />
    </Surface>
  );
};

const ZahlSeg = ({ props, p, istHoch, width, height, hell, surface, weich }) => {
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
    <Surface art={surface} akzent={p.akzent} hell={hell} breite={breite} padding={padding} sofort={weich}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        {vor ? <TextBlock text={vor} groesse={tg} farbe={p.text} delay={weich ? 0 : 4} blur={false} sofort={weich} /> : null}
        <div style={{ fontSize: zg, fontWeight: 800, color: p.akzent, lineHeight: 1,
          letterSpacing: "-0.03em", textShadow: `0 0 50px ${p.akzent}55`, fontFamily: BRAND.fonts.display }}>
          {zahl}{suffix}
        </div>
        {nach ? <TextBlock text={nach} groesse={tg} farbe={p.text} delay={40} blur={false} /> : null}
      </div>
    </Surface>
  );
};

const WortPopSeg = ({ props, p, istHoch, width, height, hell, weich }) => {
  const frame = useCurrentFrame();
  const worte = props.worte || ["WORT"];
  const akzent = props.akzentWort ?? -1;
  const basis = istHoch ? width * 0.1 : height * 0.13;
  // Durchgehendes Leben NACH der Eintritts-Animation: sanftes Glow-Puls +
  // Mikro-Atmen auf dem Akzent-Wort, damit das Segment nicht einfriert,
  // solange es haelt. Startet erst nach dem Einblenden (Frame 24+), sonst
  // wuerde es sich mit der Eintritts-Animation ueberlagern.
  const lebenStart = 24;
  const lebenPhase = Math.max(0, frame - lebenStart);
  const atemPuls = 1 + Math.sin(lebenPhase / 22) * 0.045;
  const bobY = Math.sin(lebenPhase / 22) * 4;
  const glowPuls = 0.55 + Math.sin(lebenPhase / 22) * 0.4;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: basis * 0.28 }}>
      {worte.map((w, i) => {
        const f = frame - i * (weich ? 5 : 8);
        const opDauer = weich ? 5 : 10;
        const op = interpolate(f, [0, opDauer], [0, 1], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const y = weich ? 0 : interpolate(f, [0, 14], [12, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const b = weich ? 0 : interpolate(f, [0, 12], [8, 0], { easing: EXPO, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const ak = i === akzent || (akzent === -1 && i === worte.length - 1);
        const scale = ak ? atemPuls : 1;
        const lebenY = ak ? bobY : 0;
        const glowStaerke = ak ? glowPuls : 0.55;
        return (
          <div key={i} style={{
            opacity: op, transform: `translateY(${y + lebenY}px) scale(${scale})`, filter: `blur(${b}px)`,
            fontSize: basis, fontWeight: 800, letterSpacing: "-0.02em", lineHeight: 1,
            color: ak ? p.akzent : p.text,
            textShadow: ak ? `0 0 ${30 * glowStaerke}px ${p.akzent}` : "none",
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

// ── FORMEN (jetzt ECHT angeschlossen, statt AussageSeg-Attrappe) ──
// Nachgebaut aus FormenText.jsx: rotierender Ring + einfahrende Akzent-Linie +
// zeilenweise von-links-einschwebender Text. AbsoluteFill/Hintergrund/Logo
// werden von SegmentRenderer/StorySequenz gestellt, hier nur der Inhalt.
// props: zeilen: ["Weniger Aufwand","mehr fuers Wesentliche"]
const FormenSeg = ({ props, p, istHoch, width, height, weich }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const zeilen = props.zeilen && props.zeilen.length ? props.zeilen : ["Text"];
  const basis = istHoch ? width * 0.075 : height * 0.095;

  const linieProg = spring({ frame, fps, config: { damping: 20, stiffness: 70 } });
  const linieBreite = interpolate(linieProg, [0, 1], [0, istHoch ? width * 0.45 : width * 0.22]);
  // Durchgehendes Leben: Linien-Glow UND ein spuerbarer Skalierungs-Puls auf
  // der Hauptzeile — Glow allein war im komprimierten Video kaum sichtbar.
  const lebenPhase2 = Math.max(0, frame - 20);
  const linienGlow = 0.5 + Math.sin(lebenPhase2 / 22) * 0.4;
  const zeilenPuls = 1 + Math.sin(lebenPhase2 / 22) * 0.035;

  const rot = interpolate(frame, [0, 300], [0, 180]);
  const kreisScale = spring({ frame: frame - 8, fps, config: { damping: 12, stiffness: 100 } });

  return (
    <>
      {/* rotierender Ring-Akzent hinter dem Text */}
      <div style={{
        position: "absolute",
        width: istHoch ? width * 0.6 : height * 0.6,
        height: istHoch ? width * 0.6 : height * 0.6,
        border: `3px solid ${p.akzent}`, borderRadius: "50%",
        opacity: 0.15 * kreisScale,
        transform: `rotate(${rot}deg) scale(${kreisScale})`,
        borderTopColor: "transparent", borderRightColor: "transparent",
        pointerEvents: "none",
      }} />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
                    gap: basis * 0.2, zIndex: 2, width: istHoch ? "86%" : "70%" }}>
        <div style={{ width: linieBreite, height: 5, background: p.akzent,
                      borderRadius: 3, boxShadow: `0 0 ${20 * linienGlow}px ${p.akzent}`,
                      marginBottom: basis * 0.15 }} />
        {zeilen.map((zeile, i) => {
          const start = i * (weich ? 8 : 12) + (weich ? 2 : 6);
          const opDauer = weich ? 5 : 10;
          const opacity = interpolate(frame - start, [0, opDauer], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          let x = 0;
          if (!weich) {
            const s = spring({ frame: frame - start, fps, config: { damping: 16, stiffness: 110 } });
            x = interpolate(s, [0, 1], [-30, 0]);
          }
          const istLetzte = i === zeilen.length - 1;
          const scale = istLetzte ? zeilenPuls : 1;
          return (
            <div key={i} style={{
              transform: `translateX(${x}px) scale(${scale})`, opacity,
              fontSize: basis, fontWeight: 700, color: p.text,
              letterSpacing: "-0.02em", textAlign: "center", lineHeight: 1.1,
            }}>{zeile}</div>
          );
        })}
      </div>
    </>
  );
};

// ── KINETIC (jetzt ECHT angeschlossen, statt AussageSeg-Attrappe) ──
// Nachgebaut aus KineticText.jsx: pulsierender Glow-Blob + zeilenweise
// hochfedernder Text mit Akzent-Zeile. Hintergrund/Logo kommen vom Rahmen.
// props: zeilen: ["MAHNUNG","in 30 Sekunden"], akzentZeile: 1
const KineticSeg = ({ props, p, istHoch, width, height, weich }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const zeilen = props.zeilen && props.zeilen.length ? props.zeilen : ["Text"];
  const akzentZeile = props.akzentZeile ?? 1;
  const basisGroesse = istHoch ? width * 0.085 : height * 0.105;

  const drift = interpolate(frame, [0, 300], [0, 40]);
  const glowPuls = interpolate(Math.sin(frame / 30), [-1, 1], [0.2, 0.4]);
  // Durchgehendes Leben auf der Akzent-Zeile: Glow UND spuerbare Skalierung.
  const lebenPhase3 = Math.max(0, frame - 20);
  const textGlowPuls = 0.4 + Math.sin(lebenPhase3 / 22) * 0.4;
  const textSkalPuls = 1 + Math.sin(lebenPhase3 / 22) * 0.03;

  return (
    <>
      <div style={{
        position: "absolute",
        width: width * 0.7, height: width * 0.7,
        top: `calc(40% - ${width * 0.35}px + ${drift}px)`,
        left: "15%",
        background: `radial-gradient(circle, ${p.akzentDim || p.akzent + "33"} 0%, transparent 70%)`,
        opacity: glowPuls, filter: "blur(40px)", pointerEvents: "none",
      }} />
      <div style={{ display: "flex", flexDirection: "column", gap: basisGroesse * 0.25, zIndex: 2 }}>
        {zeilen.map((zeile, i) => {
          const start = i * (weich ? 8 : 12);
          const opDauer = weich ? 5 : 10;
          const opacity = interpolate(frame - start, [0, opDauer], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          let y = 0, scale = 1;
          if (!weich) {
            const s = spring({ frame: frame - start, fps, config: { damping: 14, stiffness: 120, mass: 0.8 } });
            y = interpolate(s, [0, 1], [40, 0]);
            scale = interpolate(s, [0, 1], [0.85, 1]);
          }
          const istAkzent = i === akzentZeile;
          const finalScale = istAkzent ? scale * textSkalPuls : scale;
          return (
            <div key={i} style={{
              transform: `translateY(${y}px) scale(${finalScale})`, opacity,
              fontSize: istAkzent ? basisGroesse * 1.15 : basisGroesse,
              fontWeight: istAkzent ? 800 : 700,
              color: istAkzent ? p.akzent : p.text,
              textShadow: istAkzent ? `0 0 ${30 * textGlowPuls}px ${p.akzent}` : "none",
              letterSpacing: "-0.02em", textAlign: "center", lineHeight: 1,
            }}>{zeile}</div>
          );
        })}
      </div>
    </>
  );
};
