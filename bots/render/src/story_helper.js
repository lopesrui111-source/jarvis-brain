// Story-Dauer-Logik. Genutzt von Root (calculateMetadata) und Komposition.
// Mit echten Uebergaengen (TransitionSeries): Uebergaenge ueberlappen -> abziehen.

export const FPS = 60;
export const STANDARD_SEG_SEK = 2.5;
export const UEBERGANG_FRAMES = 16;  // Dauer eines fliessenden Uebergangs

// Uebergangstyp -> ob er ueberlappt (cut = kein Overlap)
export function istFliessend(uebergang) {
  return uebergang && uebergang !== "cut";
}

export function segmenteAufbereiten(segmente) {
  const arr = Array.isArray(segmente) && segmente.length ? segmente : [
    { stil: "szenen", props: { szenen: ["Kein Segment"] }, dauer: 2.5 },
  ];
  return arr.map((seg) => ({
    stil: seg.stil || "szenen",
    props: seg.props || {},
    frames: Math.max(24, Math.round((seg.dauer || STANDARD_SEG_SEK) * FPS)),
    surface: seg.surface || "glas",
    uebergang: seg.uebergang || "cut",   // cut | fade | slide-links/rechts/hoch/runter | wipe | clockwipe | flip
  }));
}

// Gesamtdauer: Summe minus ueberlappende Uebergaenge.
// Der Uebergang VOR Segment i (i>=1) gehoert zu segs[i].uebergang.
export function storyGesamtFrames(segmente) {
  const segs = segmenteAufbereiten(segmente);
  let total = segs.reduce((a, s) => a + s.frames, 0);
  for (let i = 1; i < segs.length; i++) {
    if (istFliessend(segs[i].uebergang)) total -= UEBERGANG_FRAMES;
  }
  return Math.max(30, total);
}
