import React from "react";
import { Composition } from "remotion";
import { KineticText } from "./KineticText.jsx";
import { WortPop } from "./WortPop.jsx";
import { SzenenSequenz } from "./SzenenSequenz.jsx";
import { ZahlHighlight } from "./ZahlHighlight.jsx";
import { FormenText } from "./FormenText.jsx";
import { StorySequenz } from "./StorySequenz.jsx";
import { storyGesamtFrames, FPS } from "./story_helper.js";

export const FORMATE = {
  tiktok:   { width: 1080, height: 1920 },
  linkedin: { width: 1920, height: 1080 },
  quadrat:  { width: 1080, height: 1080 },
};

const defsKinetic = { zeilen: ["MAHNUNG","in 30 Sekunden","statt 30 Minuten"], palette: "dunkel", akzentZeile: 1, logo: true };
const defsWort    = { worte: ["SCHLUSS","MIT","PAPIERKRAM"], palette: "dunkel", akzentWort: -1, logo: true };
const defsSzenen  = { szenen: ["Kennst du das?","Mahnungen kosten Zeit","Büroflow: in Sekunden erledigt"], palette: "dunkel", logo: true };
const defsZahl    = { zielZahl: 30, suffix: " Sek", vortext: "Mahnung in", nachtext: "statt 30 Minuten", palette: "dunkel", logo: true };
const defsFormen  = { zeilen: ["Weniger Aufwand","mehr fürs Wesentliche"], palette: "dunkel", logo: true };

const defsStory = {
  sfx: [],
  palette: "dunkel", logo: true,
  segmente: [
    { stil: "wortpop", props: { worte: ["SCHLUSS","MIT","PAPIERKRAM"], akzentWort: -1 }, dauer: 1.7, surface: "glas", uebergang: "cut" },
    { stil: "szenen",  props: { szenen: ["Mahnungen kosten dich Zeit"] }, dauer: 1.7, surface: "glas", uebergang: "cut" },
    { stil: "zahl",    props: { zielZahl: 30, suffix: " Sek", vortext: "Erledigt in", nachtext: "statt 30 Minuten" }, dauer: 2.0, surface: "glas", uebergang: "flash" },
    { stil: "szenen",  props: { szenen: ["Büroflow erledigt das automatisch"], akzent: true }, dauer: 2.0, surface: "glas", uebergang: "cut" },
    { stil: "kinetic", props: { zeilen: ["Jetzt testen — buroflow.de"] }, dauer: 1.7, surface: "card", uebergang: "dissolve" },
  ],
};

function dreiFormate(basisId, Comp, defs, dauer = 300) {
  return Object.entries(FORMATE).map(([fmt, size]) => (
    <Composition key={`${basisId}-${fmt}`} id={`${basisId}-${fmt}`}
      component={Comp} durationInFrames={dauer} fps={FPS}
      width={size.width} height={size.height} defaultProps={defs} />
  ));
}

function storyFormate() {
  return Object.entries(FORMATE).map(([fmt, size]) => (
    <Composition key={`story-${fmt}`} id={`story-${fmt}`}
      component={StorySequenz} fps={FPS}
      width={size.width} height={size.height}
      durationInFrames={storyGesamtFrames(defsStory.segmente)}
      defaultProps={defsStory}
      calculateMetadata={({ props }) => ({ durationInFrames: storyGesamtFrames(props.segmente) })} />
  ));
}

// ═══ SELBST-GEBAUTE KOMPONENTEN (Komponenten-Schmiede) ═══
// Der Regie-Bot schreibt neue Komponenten nach src/custom/. Remotion buendelt
// bei jedem Render neu -> neue Dateien werden automatisch erfasst, ohne Rebuild.
// Jede Datei exportiert: `meta` ({dauerSek, defaultProps}) und `Komponente`.
function customFormate() {
  let ctx;
  try {
    ctx = require.context("./custom", false, /\.jsx$/);
  } catch (e) {
    return [];
  }
  const out = [];
  ctx.keys().forEach((key) => {
    try {
      const mod = ctx(key);
      const Comp = mod.Komponente || mod.default;
      const meta = mod.meta || {};
      if (!Comp) return;
      const name = key.replace("./", "").replace(".jsx", "");
      const dauer = Math.round((meta.dauerSek || 5) * FPS);
      Object.entries(FORMATE).forEach(([fmt, size]) => {
        out.push(
          <Composition key={`custom-${name}-${fmt}`} id={`custom-${name}-${fmt}`}
            component={Comp} durationInFrames={dauer} fps={FPS}
            width={size.width} height={size.height}
            defaultProps={meta.defaultProps || {}} />
        );
      });
    } catch (e) { /* fehlerhafte custom-Datei ignorieren, Rest laeuft weiter */ }
  });
  return out;
}

export const RemotionRoot = () => {
  return (
    <>
      {dreiFormate("kinetic", KineticText, defsKinetic)}
      {dreiFormate("wortpop", WortPop, defsWort)}
      {dreiFormate("szenen", SzenenSequenz, defsSzenen)}
      {dreiFormate("zahl", ZahlHighlight, defsZahl)}
      {dreiFormate("formen", FormenText, defsFormen)}
      {storyFormate()}
      {customFormate()}
    </>
  );
};
