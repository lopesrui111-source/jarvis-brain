// Story-Dauer-Logik. Genutzt von Root (calculateMetadata) und Komposition.
// DNA: harte Cuts (kein Overlap) -> Gesamtdauer = Summe der Segment-Frames.

export const FPS = 60;
export const STANDARD_SEG_SEK = 1.7;   // metronomischer Default (Referenz-Schnittmenge)

export function segmenteAufbereiten(segmente) {
  const arr = Array.isArray(segmente) && segmente.length ? segmente : [
    { stil: "szenen", props: { szenen: ["Kein Segment"] }, dauer: 1.7 },
  ];
  return arr.map((seg) => ({
    stil: seg.stil || "szenen",
    props: seg.props || {},
    frames: Math.max(24, Math.round((seg.dauer || STANDARD_SEG_SEK) * FPS)),
    surface: seg.surface || "glas",     // glas | card
    uebergang: seg.uebergang || "cut",  // cut | dissolve | flash
  }));
}

export function storyGesamtFrames(segmente) {
  const segs = segmenteAufbereiten(segmente);
  return segs.reduce((a, s) => a + s.frames, 0);
}

// Startframe jedes Segments (harte Cuts, kumuliert)
export function segmentStarts(segs) {
  const starts = [];
  let acc = 0;
  for (const s of segs) { starts.push(acc); acc += s.frames; }
  return starts;
}
