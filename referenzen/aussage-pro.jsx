// aussage-pro.jsx — REFERENZ: HOOK & CTA
//
// NACHGEBAUT AUS simo.mp4 (Frame-fuer-Frame-Analyse 0,9s-1,8s).
//
// DER MECHANISMUS — und warum frueheres Ein-/Ausblenden falsch war:
//
//   1. Die Zeile faehrt KONTINUIERLICH nach links. Gleichmaessig, ohne
//      Halt. Kein Wort "fliegt ein".
//
//   2. Alle Woerter stehen an ihrer festen Position in der Zeile. Sie
//      bewegen sich nicht relativ zueinander.
//
//   3. Jedes Wort durchlaeuft eine MATERIALISIERUNG, die an seine
//      POSITION IM BILD gekoppelt ist:
//        - weit rechts  -> transparent + stark unscharf
//        - Bildmitte    -> halb sichtbar, weich
//        - links        -> voll deckend + scharf
//      Weil die Zeile faehrt, wandert jedes Wort durch diese Zone und
//      wird dabei scharf. Es "erscheint" also nacheinander — aber als
//      kontinuierlicher Prozess, nicht als abrupter Einblendvorgang.
//
//   4. Das letzte Wort (die Pointe) kommt nach einer kurzen Pause und
//      bleibt heller/zurueckhaltender als der Rest.
//
// Der Text steht LINKS im Bild, nicht mittig.
//
// props: modus = "hook" | "cta"

import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { BRAND } from "../brand.js";

export const meta = {
  dauerSek: 3,
  defaultProps: {
    modus: "hook",
    satz: "Bürokram, der sich selbst",
    pointe: "erledigt.",
    ctaSatz: "Alles automatisch —",
    ctaPointe: "buroflow.de",
  },
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

// Textbreite schaetzen (im Server-Render gibt es keine DOM-Messung)
const breite = (text, groesse, serif = false) =>
  text.length * groesse * (serif ? 0.46 : 0.52);

export const Komponente = ({
  palette = "dunkel",
  modus = "hook",
  satz = "Bürokram, der sich selbst",
  pointe = "erledigt.",
  ctaSatz = "Alles automatisch —",
  ctaPointe = "buroflow.de",
}) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const F_D = BRAND.fonts.display, F_A = BRAND.fonts.akzent;
  const istHook = modus === "hook";

  const gross = H * 0.125;   // gross genug, dass die Zeile breiter als das Bild wird
  const luecke = gross * 0.26;

  /* ═══ Woerter mit fester Position in der Zeile ═══ */
  const roh = [
    ...(istHook ? satz : ctaSatz).split(" ").map((w) => ({ w, serif: false })),
    { w: istHook ? pointe : ctaPointe, serif: true },
  ];
  const woerter = [];
  let lauf = 0;
  roh.forEach((wo) => {
    const g = wo.serif ? gross * 1.05 : gross;
    const bw = breite(wo.w, g, wo.serif);
    woerter.push({ ...wo, links: lauf, bw, g });
    lauf += bw + luecke;
  });
  const zeilenBreite = lauf;

  /* ═══ DIE FAHRT — kontinuierlich, mit einer Atempause vor der Pointe ═══
     Im Vorbild: gleichmaessige Fahrt, kurze Verlangsamung bei ~1,6s,
     dann kommt die Pointe. */
  // Startposition so gewaehlt, dass anfangs NUR das erste Wort sichtbar ist.
  // Der Rest der Zeile liegt rechts ausserhalb und faehrt nach und nach
  // in die Schaerfezone hinein.
  const startX = W * 0.12;
  const fahrt = (f) => {
    // DURCHGEHENDE Fahrt ohne Pause. Frueher gab es einen Halt zwischen
    // Frame 96 und 122 — genau dort hing die Pointe in der Halbschatten-
    // Zone und wurde danach abrupt scharf. Eine gleichmaessige Fahrt
    // laesst jedes Wort fluessig durch die Schaerfezone gleiten.
    const a = interpolate(f, [8, 170], [0, 1],
      { easing: Easing.inOut(Easing.cubic), ...clamp });
    return startX - a * zeilenBreite * 0.72;
  };
  const zeileX = fahrt(frame);
  const zeileXDavor = fahrt(frame - 1);
  const fahrTempo = Math.abs(zeileX - zeileXDavor);

  /* ═══ Fokus-Effekt zu Beginn ═══ */
  const fokus = interpolate(frame, [0, 30], [13, 0],
    { easing: Easing.out(Easing.cubic), ...clamp });

  /* ═══ Sanfter Push-In ═══ */
  const push = interpolate(frame, [0, 180], [1.0, 1.035],
    { easing: Easing.inOut(Easing.ease), ...clamp });

  /* ═══ Organischer Hintergrund ═══ */
  const tt = frame / 60;
  const blob = (i) => {
    const ph = i * 2.1;
    return {
      x: 50 + Math.sin(tt * 0.42 + ph) * 34 + Math.cos(tt * 0.27 + ph * 1.6) * 14,
      y: 48 + Math.cos(tt * 0.36 + ph) * 30 + Math.sin(tt * 0.31 + ph * 1.3) * 12,
      r: 44 + Math.sin(tt * 0.24 + ph) * 12,
    };
  };
  const B = [blob(0), blob(1), blob(2), blob(3)];
  const hx = (n) => Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, "0");
  const kraft = interpolate(frame, [0, 26], [0.6, 1], clamp);

  return (
    <AbsoluteFill style={{ background: "#0a1a12", overflow: "hidden" }}>
      <AbsoluteFill style={{
        transform: `scale(${push})`,
        background: `
          radial-gradient(ellipse ${B[0].r}% ${B[0].r * 0.82}% at ${B[0].x}% ${B[0].y}%,
            ${p.akzent}${hx(kraft * 74)} 0%, ${p.akzent}${hx(kraft * 26)} 44%, transparent 78%),
          radial-gradient(ellipse ${B[1].r * 0.9}% ${B[1].r}% at ${B[1].x}% ${B[1].y}%,
            #5DCAA5${hx(kraft * 62)} 0%, #5DCAA5${hx(kraft * 20)} 46%, transparent 80%),
          radial-gradient(ellipse ${B[2].r * 1.1}% ${B[2].r * 0.7}% at ${B[2].x}% ${B[2].y}%,
            #06120c${hx(kraft * 150)} 0%, transparent 62%),
          radial-gradient(ellipse ${B[3].r * 0.8}% ${B[3].r * 0.95}% at ${B[3].x}% ${B[3].y}%,
            #0d2418${hx(kraft * 130)} 0%, transparent 58%),
          linear-gradient(150deg, #17301f 0%, #0b1a12 52%, #061009 100%)`,
        filter: "blur(2px)",
      }} />
      <AbsoluteFill style={{
        opacity: 0.055, mixBlendMode: "overlay",
        backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='150' height='150'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4'/%3E%3C/filter%3E%3Crect width='150' height='150' filter='url(%23n)'/%3E%3C/svg%3E\")",
      }} />

      <AbsoluteFill style={{
        filter: fokus > 0.4 ? `blur(${fokus.toFixed(1)}px)` : "none",
        transform: `scale(${push})`,
      }}>
        <div style={{
          position: "absolute", top: "50%", left: 0,
          transform: `translateY(-50%) translateX(${zeileX}px)`,
          whiteSpace: "nowrap", willChange: "transform",
        }}>
          {woerter.map((wo, i) => {
            /* ═══ MATERIALISIERUNG nach Position im Bild ═══
               Das ist der Kern: Nicht die Zeit bestimmt, wie sichtbar ein
               Wort ist, sondern WO es gerade im Bild steht. */
            const mitteImBild = zeileX + wo.links + wo.bw / 2;
            const anteil = mitteImBild / W;   // 0 = linker Rand, 1 = rechter

            // rechts vom Bild -> unsichtbar; ab ~0,72 beginnt es zu erscheinen;
            // bei ~0,34 ist es voll scharf und deckend
            // WICHTIG: Remotions interpolate braucht einen AUFSTEIGENDEN
            // Eingabebereich. Da die Sichtbarkeit zunimmt, je weiter LINKS
            // ein Wort steht, muessen die Ausgabewerte getauscht werden:
            //   anteil klein (links)  -> voll sichtbar, scharf
            //   anteil gross (rechts) -> transparent, unscharf
            // Weiche, breite Uebergangszone — je grosszuegiger der Bereich,
            // desto fluessiger das Materialisieren. Enge Zonen wirken wie
            // ein Schalter, der umspringt.
            const sicht = interpolate(anteil, [0.22, 0.92], [1, 0], clamp);
            const deckung = interpolate(anteil, [0.26, 0.86], [1, 0],
              { easing: Easing.inOut(Easing.ease), ...clamp });
            const unschaerfe = interpolate(anteil, [0.26, 0.86], [0, 19],
              { easing: Easing.inOut(Easing.ease), ...clamp });

            // Pointe bleibt bewusst zurueckhaltender (wie "Apple." im Vorbild)
            const maxDeckung = wo.serif ? 0.78 : 1;
            // Bewegungsunschaerfe aus der Fahrgeschwindigkeit
            const fahrBlur = Math.min(9, fahrTempo * 0.38);

            if (sicht <= 0.01) return null;
            return (
              <span key={i} style={{
                position: "absolute", left: wo.links, top: 0,
                fontFamily: wo.serif ? F_A : F_D,
                fontStyle: wo.serif ? "italic" : "normal",
                fontSize: wo.g,
                fontWeight: wo.serif ? 400 : 700,
                color: `rgba(255,255,255,${(deckung * maxDeckung).toFixed(3)})`,
                letterSpacing: wo.serif ? "-0.015em" : "-0.035em",
                filter: (unschaerfe + fahrBlur) > 0.4
                  ? `blur(${(unschaerfe + fahrBlur).toFixed(1)}px)` : "none",
                textShadow: "0 6px 44px rgba(0,0,0,0.4)",
                willChange: "filter",
              }}>{wo.w}</span>
            );
          })}
        </div>
      </AbsoluteFill>

      <AbsoluteFill style={{
        background: "radial-gradient(ellipse at 50% 50%, transparent 64%, rgba(0,0,0,0.28) 100%)",
        pointerEvents: "none",
      }} />
    </AbsoluteFill>
  );
};

export default Komponente;
