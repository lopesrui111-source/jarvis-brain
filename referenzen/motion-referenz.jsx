// motion-referenz.jsx — DIE 2D-MOTION-REFERENZ
//
// Eine DURCHGEHENDE Sequenz (~10s) ohne einen einzigen harten Schnitt.
// Alles ist EINE Kamerafahrt ueber eine grosse virtuelle Flaeche, auf der
// die Szenen nebeneinander liegen. Die Uebergaenge entstehen durch die
// Bewegung selbst — man sieht nie eine Naht.
//
// DREI PRINZIPIEN, die hier vorgefuehrt werden:
//
// 1) KAMERAFAHRT: Die "Kamera" (ein grosser Wrapper) faehrt ueber eine
//    Flaeche von mehreren Bildschirmbreiten. Sie beschleunigt weich, haelt
//    an den Szenen kurz, faehrt weiter — nie ein harter Stopp.
//
// 2) PARALLAX: Vier Ebenen bewegen sich mit UNTERSCHIEDLICHER Geschwindigkeit
//    (Hintergrund 0.25x, Mittelgrund 0.6x, Inhalt 1.0x, Vordergrund 1.5x).
//    Das erzeugt Raumtiefe, obwohl alles flach ist.
//
// 3) MORPHING: Elemente sterben nicht am Szenenwechsel — sie VERWANDELN sich.
//    Ein Rechteck wird zum Kreis wird zum Balken. Ein Wort bleibt stehen,
//    waehrend das andere tauscht. Eine Karte wird zum Dashboard-Rahmen.

import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { BRAND } from "../brand.js";

export const meta = { dauerSek: 10, defaultProps: {} };

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };
const smooth = (t) => t * t * (3 - 2 * t);
// weiche Fahrt zwischen zwei Werten
const fahrt = (frame, von, bis, a, b) => {
  const t = interpolate(frame, [von, bis], [0, 1], clamp);
  return a + (b - a) * smooth(t);
};
// Mehrpunkt-Fahrt: die Kamera haelt an Stationen, faehrt dann weiter
function station(frame, punkte) {
  // punkte: [[frame, wert], [frame, wert], ...]
  for (let i = 0; i < punkte.length - 1; i++) {
    const [f1, v1] = punkte[i];
    const [f2, v2] = punkte[i + 1];
    if (frame <= f2) return fahrt(frame, f1, f2, v1, v2);
  }
  return punkte[punkte.length - 1][1];
}

/* ══════════════════════════════════════════════════════
   MORPH-BAUSTEIN: eine Form, die sich verwandelt
   Rechteck -> abgerundet -> Kreis, mit Groessen- und Farbwechsel
   ══════════════════════════════════════════════════════ */
const MorphForm = ({ frame, von, bis, startForm, zielForm, p }) => {
  const t = interpolate(frame, [von, bis], [0, 1], { easing: Easing.inOut(Easing.cubic), ...clamp });
  const b = (k) => startForm[k] + (zielForm[k] - startForm[k]) * t;
  return (
    <div style={{
      position: "absolute",
      left: b("x"), top: b("y"),
      width: b("w"), height: b("h"),
      borderRadius: b("r"),
      background: t < 0.5 ? startForm.farbe : zielForm.farbe,
      opacity: b("o"),
      transform: `rotate(${b("rot")}deg)`,
      boxShadow: `0 0 ${40 * b("glow")}px ${p.akzent}`,
      transition: "none",
    }} />
  );
};

/* ══════════════════════════════════════════════════════
   TEXT-MORPH: gemeinsames Wort bleibt, das andere tauscht
   ══════════════════════════════════════════════════════ */
const TextMorph = ({ frame, wechselAb, bleibt, wortA, wortB, groesse, p }) => {
  // Wort A verschwindet nach oben+blur, Wort B kommt von unten
  const aOp = interpolate(frame, [wechselAb, wechselAb + 14], [1, 0], clamp);
  const aY = interpolate(frame, [wechselAb, wechselAb + 14], [0, -22], { easing: Easing.in(Easing.cubic), ...clamp });
  const aBlur = interpolate(frame, [wechselAb, wechselAb + 14], [0, 9], clamp);
  const bOp = interpolate(frame, [wechselAb + 8, wechselAb + 24], [0, 1], clamp);
  const bY = interpolate(frame, [wechselAb + 8, wechselAb + 24], [26, 0], { easing: Easing.out(Easing.cubic), ...clamp });
  const bBlur = interpolate(frame, [wechselAb + 8, wechselAb + 24], [9, 0], clamp);
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: groesse * 0.28,
      fontFamily: BRAND.fonts.display, fontSize: groesse, fontWeight: 700,
      letterSpacing: "-0.03em", whiteSpace: "nowrap" }}>
      {/* Dieses Wort BLEIBT — das ist der Morph-Effekt */}
      <span style={{ color: "#FFFFFF" }}>{bleibt}</span>
      <span style={{ position: "relative", display: "inline-block", minWidth: groesse * 4.4 }}>
        <span style={{ position: "absolute", left: 0, top: 0, color: p.akzent,
          opacity: aOp, transform: `translateY(${aY}px)`, filter: `blur(${aBlur}px)`,
          textShadow: `0 0 34px ${p.akzent}66` }}>{wortA}</span>
        <span style={{ position: "absolute", left: 0, top: 0, color: p.akzent,
          opacity: bOp, transform: `translateY(${bY}px)`, filter: `blur(${bBlur}px)`,
          textShadow: `0 0 34px ${p.akzent}66` }}>{wortB}</span>
      </span>
    </div>
  );
};

/* ══════════════════════════════════════════════════════
   PARALLAX-EBENE
   ══════════════════════════════════════════════════════ */
const Ebene = ({ tiefe, camX, camY, camScale, children, style }) => (
  <div style={{
    position: "absolute", inset: 0,
    transform: `translate(${-camX * tiefe}px, ${-camY * tiefe}px) scale(${1 + (camScale - 1) * tiefe})`,
    transformOrigin: "50% 50%",
    willChange: "transform",
    ...style,
  }}>{children}</div>
);

/* ══════════════════════════════════════════════════════
   HAUPTKOMPONENTE
   ══════════════════════════════════════════════════════ */
export const Komponente = ({ palette = "dunkel" }) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;

  /* ── DIE KAMERAFAHRT ──
     Vier Stationen ueber ~10s. Zwischen den Stationen faehrt sie,
     an den Stationen verweilt sie kurz (gleicher Wert = Stillstand,
     aber der Parallax-Hintergrund laeuft weiter). */
  const camX = station(frame, [
    [0, 0],            // Station 1: Hook
    [95, W * 1.0],     // faehrt nach rechts
    [150, W * 1.0],    // Station 2: haelt
    [250, W * 2.0],    // faehrt weiter
    [305, W * 2.0],    // Station 3: haelt
    [430, W * 3.0],    // Station 4: Finale
  ]);
  const camY = station(frame, [
    [0, 0], [95, -H * 0.12], [150, -H * 0.12],
    [250, H * 0.08], [305, H * 0.08], [430, 0],
  ]);
  // Zoom atmet mit: naeher ran an den Stationen, weiter weg beim Fahren
  const camScale = station(frame, [
    [0, 1.14], [60, 1.02], [95, 1.0], [150, 1.12],
    [200, 1.0], [250, 1.0], [305, 1.16], [370, 1.02], [430, 1.06],
  ]);
  // leichte Rotation beim Fahren — macht die Bewegung koerperlich
  const camRot = station(frame, [
    [0, -1.4], [95, 0.6], [150, 0], [250, -0.8], [305, 0], [430, 0.4],
  ]);

  /* ── MORPH 1 (Station 1 -> 2): Karte wird zum Dashboard-Rahmen ── */
  const morph1 = interpolate(frame, [96, 148], [0, 1], { easing: Easing.inOut(Easing.cubic), ...clamp });

  /* ── MORPH 2 (Station 2 -> 3): Rechteck wird zum Kreis (Donut) ── */
  const morph2 = interpolate(frame, [252, 300], [0, 1], { easing: Easing.inOut(Easing.cubic), ...clamp });

  /* ── Vordergrund-Streifen, die durchs Bild wischen (Uebergangs-Kaschierung) ── */
  const wisch1 = interpolate(frame, [92, 130], [-30, 130], { easing: Easing.inOut(Easing.cubic), ...clamp });
  const wisch2 = interpolate(frame, [248, 288], [-30, 130], { easing: Easing.inOut(Easing.cubic), ...clamp });

  const gross = H * 0.115;

  return (
    <AbsoluteFill style={{
      background: "#05070a", overflow: "hidden",
      transform: `rotate(${camRot}deg)`, transformOrigin: "50% 50%",
    }}>

      {/* ═══ EBENE 1 (Tiefe 0.25): Hintergrund — bewegt sich kaum ═══ */}
      <Ebene tiefe={0.25} camX={camX} camY={camY} camScale={camScale}>
        <div style={{ position: "absolute", inset: "-50%",
          background: `radial-gradient(circle at 22% 34%, ${p.akzent}14 0%, transparent 42%),
                       radial-gradient(circle at 72% 62%, #5DCAA512 0%, transparent 46%),
                       radial-gradient(circle at 140% 30%, ${p.akzent}0e 0%, transparent 40%)` }} />
        {/* Raster als Tiefenreferenz */}
        <div style={{ position: "absolute", inset: "-50%", opacity: 0.05,
          backgroundImage: `linear-gradient(${p.akzent} 1px, transparent 1px),
                            linear-gradient(90deg, ${p.akzent} 1px, transparent 1px)`,
          backgroundSize: "90px 90px" }} />
      </Ebene>

      {/* ═══ EBENE 2 (Tiefe 0.6): Mittelgrund — Formen, die morphen ═══ */}
      <Ebene tiefe={0.6} camX={camX} camY={camY} camScale={camScale}>
        {/* MORPH 1: Dokument-Karte (Station 1) wird zum Dashboard-Rahmen (Station 2) */}
        <div style={{
          position: "absolute",
          left: W * 0.26 + morph1 * (W * 0.72),
          top: H * 0.3 + morph1 * (H * -0.06),
          width: W * 0.2 + morph1 * (W * 0.42),
          height: H * 0.3 + morph1 * (H * 0.12),
          borderRadius: 18 - morph1 * 8,
          border: `${1.5 + morph1 * 0.5}px solid ${p.akzent}${morph1 > 0.5 ? "55" : "33"}`,
          background: `linear-gradient(150deg, ${p.akzent}${morph1 > 0.5 ? "0a" : "12"}, rgba(8,14,20,0.75))`,
          boxShadow: `0 30px 90px rgba(0,0,0,0.6), 0 0 ${50 + morph1 * 40}px ${p.akzent}1a`,
          backdropFilter: "blur(14px)",
          transform: `rotate(${-4 + morph1 * 4}deg)`,
          padding: H * 0.028,
          display: "flex", flexDirection: "column", gap: H * 0.018,
          boxSizing: "border-box", overflow: "hidden",
        }}>
          {/* INHALT: angedeutete Zeilen — ohne die wirkt der Rahmen leer/nackt.
              Beim Morph werden aus den Dokumentzeilen Dashboard-Kacheln. */}
          <div style={{
            height: H * 0.016, width: `${52 - morph1 * 14}%`,
            background: p.akzent, opacity: 0.75, borderRadius: 3,
          }} />
          <div style={{ display: "flex", gap: H * 0.014, flex: 1 }}>
            {[0, 1, 2].map((i) => (
              <div key={i} style={{
                flex: 1,
                background: `rgba(255,255,255,${0.04 + morph1 * 0.02})`,
                border: `1px solid ${p.akzent}${morph1 > 0.5 ? "26" : "14"}`,
                borderRadius: 6,
                opacity: i < 2 || morph1 > 0.4 ? 1 : 0.35,
                display: "flex", flexDirection: "column",
                justifyContent: "flex-end", padding: H * 0.012, gap: H * 0.008,
              }}>
                <div style={{ height: H * 0.009, width: "70%",
                  background: "#5a6b7a", borderRadius: 2 }} />
                <div style={{ height: H * 0.014, width: "45%",
                  background: i === 1 ? p.akzent : "#8fa3b3", borderRadius: 2, opacity: 0.9 }} />
              </div>
            ))}
          </div>
          {/* Fusszeile — erscheint erst beim Morph zum Dashboard */}
          <div style={{
            height: H * 0.03, opacity: morph1,
            background: "rgba(255,255,255,0.03)",
            border: `1px solid ${p.akzent}1a`, borderRadius: 5,
          }} />
        </div>

        {/* MORPH 2: Balken (Station 2) wird zum runden Ring (Station 3).
            Breite und Hoehe laufen auf denselben Zielwert zu — sonst
            entsteht am Ende ein verzogenes Oval statt eines Kreises. */}
        {(() => {
          const zielD = H * 0.26;              // Ziel-Durchmesser (Kreis)
          const startB = W * 0.26, startH = H * 0.1;
          const b = startB + (zielD - startB) * morph2;
          const h = startH + (zielD - startH) * morph2;
          return (
            <div style={{
              position: "absolute",
              left: W * 1.6 + morph2 * (W * 0.6),
              top: H * 0.5 + morph2 * (H * -0.1),
              width: b, height: h,
              borderRadius: morph2 * (zielD / 2),
              border: `${8 + morph2 * 10}px solid ${p.akzent}`,
              opacity: 0.9,
              boxShadow: `0 0 ${30 + morph2 * 46}px ${p.akzent}55`,
              transform: `rotate(${morph2 * -120}deg)`,
              boxSizing: "border-box",
            }} />
          );
        })()}

        {/* Station 4: Ring, der sich aufbaut — bewusst RECHTS OBEN, damit er
            nicht durch den CTA-Text laeuft (Zonentrennung: Text links unten,
            Grafik rechts oben). */}
        <div style={{
          position: "absolute", left: W * 3.52, top: H * 0.12,
          width: H * 0.32, height: H * 0.32, borderRadius: "50%",
          border: `3px solid ${p.akzent}`,
          borderTopColor: "transparent", borderRightColor: "transparent",
          opacity: interpolate(frame, [330, 380], [0, 0.42], clamp),
          transform: `rotate(${interpolate(frame, [330, 470], [0, 200], clamp)}deg)`,
        }} />
      </Ebene>

      {/* ═══ EBENE 3 (Tiefe 1.0): Inhalt — Text und Kernaussagen ═══ */}
      <Ebene tiefe={1.0} camX={camX} camY={camY} camScale={camScale}>

        {/* ── STATION 1: Hook ── */}
        <div style={{ position: "absolute", left: W * 0.1, top: H * 0.42 }}>
          <div style={{
            opacity: interpolate(frame, [8, 34], [0, 1], clamp),
            transform: `translateY(${fahrt(frame, 8, 44, 34, 0)}px)`,
            fontFamily: BRAND.fonts.display, fontSize: H * 0.036, fontWeight: 500,
            letterSpacing: "0.3em", color: p.akzent, marginBottom: H * 0.03,
          }}>BÜROFLOW</div>
          <div style={{
            opacity: interpolate(frame, [18, 48], [0, 1], clamp),
            transform: `translateY(${fahrt(frame, 18, 60, 46, 0)}px)`,
            fontFamily: BRAND.fonts.display, fontSize: gross, fontWeight: 700,
            color: "#FFFFFF", letterSpacing: "-0.03em", lineHeight: 1.02,
          }}>Papierkram<br />frisst deine Zeit.</div>
        </div>

        {/* ── STATION 2: TEXT-MORPH ── */}
        <div style={{ position: "absolute", left: W * 1.1, top: H * 0.44 }}>
          <div style={{ opacity: interpolate(frame, [110, 140], [0, 1], clamp) }}>
            <TextMorph frame={frame} wechselAb={196} bleibt="Weniger"
              wortA="Chaos." wortB="Aufwand." groesse={gross} p={p} />
          </div>
        </div>

        {/* ── STATION 3: Zahl, die hochzaehlt ── */}
        <div style={{ position: "absolute", left: W * 2.08, top: H * 0.38 }}>
          <div style={{
            opacity: interpolate(frame, [268, 296], [0, 1], clamp),
            transform: `scale(${fahrt(frame, 268, 310, 0.82, 1)})`,
            fontFamily: BRAND.fonts.display, fontSize: H * 0.2, fontWeight: 800,
            color: p.akzent, lineHeight: 1, letterSpacing: "-0.04em",
            textShadow: `0 0 60px ${p.akzent}55`,
          }}>
            {Math.round(interpolate(frame, [272, 340], [0, 12], clamp))}h
          </div>
          <div style={{
            opacity: interpolate(frame, [300, 330], [0, 1], clamp),
            transform: `translateY(${fahrt(frame, 300, 344, 20, 0)}px)`,
            fontFamily: BRAND.fonts.display, fontSize: H * 0.042, fontWeight: 500,
            color: "#9fb4c4", marginTop: H * 0.012,
          }}>gespart. Jeden Monat.</div>
        </div>

        {/* ── STATION 4: CTA ── */}
        <div style={{ position: "absolute", left: W * 3.08, top: H * 0.44 }}>
          <div style={{
            opacity: interpolate(frame, [368, 398], [0, 1], clamp),
            transform: `translateY(${fahrt(frame, 368, 412, 32, 0)}px)`,
            fontFamily: BRAND.fonts.display, fontSize: gross, fontWeight: 700,
            color: "#FFFFFF", letterSpacing: "-0.03em", lineHeight: 1.04,
          }}>Alles automatisch.</div>
          <div style={{
            opacity: interpolate(frame, [388, 418], [0, 1], clamp),
            transform: `translateY(${fahrt(frame, 388, 432, 24, 0)}px)`,
            fontFamily: BRAND.fonts.display, fontSize: gross * 0.72, fontWeight: 700,
            color: p.akzent, letterSpacing: "-0.02em", marginTop: H * 0.02,
            textShadow: `0 0 40px ${p.akzent}55`,
          }}>buroflow.de</div>
        </div>
      </Ebene>

      {/* ═══ EBENE 4 (Tiefe 1.5): Vordergrund — zieht am schnellsten vorbei ═══
          Dezente, gleichmaessig verteilte Lichtstriche. Bewusst schwach: sie
          sollen Tiefe erzeugen, nicht als Fremdkoerper auffallen. */}
      <Ebene tiefe={1.5} camX={camX} camY={camY} camScale={camScale}>
        {[0.18, 0.66, 1.14, 1.62, 2.10, 2.58, 3.06].map((x, i) => (
          <div key={i} style={{
            position: "absolute", left: W * x, top: H * (0.06 + (i % 2) * 0.52),
            width: 2, height: H * 0.3,
            background: `linear-gradient(180deg, transparent, ${p.akzent}33, transparent)`,
            opacity: 0.32,
          }} />
        ))}
      </Ebene>

      {/* ═══ UEBERGANGS-WISCHER: kaschieren die Szenenwechsel ═══ */}
      <div style={{
        position: "absolute", top: "-20%", left: `${wisch1}%`,
        width: "14%", height: "140%",
        background: `linear-gradient(100deg, transparent, ${p.akzent}22, #ffffff14, transparent)`,
        transform: "skewX(-14deg)", filter: "blur(10px)", pointerEvents: "none",
      }} />
      <div style={{
        position: "absolute", top: "-20%", left: `${wisch2}%`,
        width: "12%", height: "140%",
        background: `linear-gradient(100deg, transparent, #5DCAA522, #ffffff10, transparent)`,
        transform: "skewX(-14deg)", filter: "blur(10px)", pointerEvents: "none",
      }} />

      {/* Vignette */}
      <AbsoluteFill style={{
        background: "radial-gradient(ellipse at 50% 50%, transparent 46%, rgba(0,0,0,0.68) 100%)",
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
};

export default Komponente;
