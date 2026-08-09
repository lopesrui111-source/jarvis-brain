import React from "react";
import { Composition } from "remotion";
import { KineticText } from "./KineticText.jsx";
import { WortPop } from "./WortPop.jsx";
import { SzenenSequenz } from "./SzenenSequenz.jsx";
import { ZahlHighlight } from "./ZahlHighlight.jsx";
import { FormenText } from "./FormenText.jsx";

export const FORMATE = {
  tiktok:   { width: 1080, height: 1920 },
  linkedin: { width: 1920, height: 1080 },
  quadrat:  { width: 1080, height: 1080 },
};

// Standard-Props je Stil (dunkel+limette als Vibe)
const defsKinetic = { zeilen: ["MAHNUNG","in 30 Sekunden","statt 30 Minuten"], palette: "dunkel", akzentZeile: 1, logo: true };
const defsWort    = { worte: ["SCHLUSS","MIT","PAPIERKRAM"], palette: "dunkel", akzentWort: -1, logo: true };
const defsSzenen  = { szenen: ["Kennst du das?","Mahnungen kosten Zeit","Büroflow: in Sekunden erledigt"], palette: "dunkel", logo: true };
const defsZahl    = { zielZahl: 30, suffix: " Sek", vortext: "Mahnung in", nachtext: "statt 30 Minuten", palette: "dunkel", logo: true };
const defsFormen  = { zeilen: ["Weniger Aufwand","mehr fürs Wesentliche"], palette: "dunkel", logo: true };

// Hilfsfunktion: eine Komposition in allen drei Formaten registrieren
function dreiFormate(basisId, Comp, defs, dauer = 300) {
  return Object.entries(FORMATE).map(([fmt, size]) => (
    <Composition key={`${basisId}-${fmt}`} id={`${basisId}-${fmt}`}
      component={Comp} durationInFrames={dauer} fps={60}
      width={size.width} height={size.height} defaultProps={defs} />
  ));
}

export const RemotionRoot = () => {
  return (
    <>
      {dreiFormate("kinetic", KineticText, defsKinetic)}
      {dreiFormate("wortpop", WortPop, defsWort)}
      {dreiFormate("szenen", SzenenSequenz, defsSzenen)}
      {dreiFormate("zahl", ZahlHighlight, defsZahl)}
      {dreiFormate("formen", FormenText, defsFormen)}
    </>
  );
};
