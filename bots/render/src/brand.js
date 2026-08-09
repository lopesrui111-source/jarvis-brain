// Zentrales Büroflow-Brandkit für alle Motion-Design-Kompositionen.
// Quelle: app/globals.css + public/brand/README.md des Büroflow-Repos.
// Einmal definiert — jede Komposition zieht Farben/Fonts/Logos von hier.

export const BRAND = {
  farben: {
    // Dunkle Welt
    anthrazit:   "#1A1D24",   // Primär dunkel
    schwarz:     "#090908",   // Tiefer dunkler Hintergrund
    limette:     "#C8FF47",   // Haupt-Akzent (dunkle Welt)
    // Helle Welt
    creme:       "#F6F3EC",   // Heller Hintergrund
    dunkelgruen: "#2D5E08",   // Akzent (helle Welt)
    // Marke allgemein
    weiss:       "#FFFFFF",
    gruen:       "#5DCAA5",   // Marken-Grün (Status/sekundär)
  },

  // Fertige Paletten je Stimmung — der Bot wählt eine davon
  paletten: {
    dunkel: {
      hintergrund: "#090908",
      text:        "#FFFFFF",
      akzent:      "#C8FF47",   // Limette
      akzentDim:   "rgba(200,255,71,0.14)",
      verlauf:     "radial-gradient(circle at 50% 40%, #1a1d24 0%, #090908 70%)",
    },
    hell: {
      hintergrund: "#F6F3EC",
      text:        "#1A1D24",
      akzent:      "#2D5E08",   // Dunkelgrün
      akzentDim:   "rgba(45,94,8,0.10)",
      verlauf:     "radial-gradient(circle at 50% 40%, #ffffff 0%, #F6F3EC 70%)",
    },
    gruen: {
      hintergrund: "#5DCAA5",
      text:        "#FFFFFF",
      akzent:      "#1A1D24",   // dunkler Kontrast
      akzentDim:   "rgba(26,29,36,0.12)",
      verlauf:     "radial-gradient(circle at 50% 40%, #6fd9b3 0%, #5DCAA5 70%)",
    },
    limette: {
      hintergrund: "#C8FF47",
      text:        "#1A1D24",
      akzent:      "#2D5E08",
      akzentDim:   "rgba(45,94,8,0.12)",
      verlauf:     "radial-gradient(circle at 50% 40%, #d8ff6e 0%, #C8FF47 70%)",
    },
  },

  fonts: {
    // Geist Sans — die Büroflow-Schrift. Wird im Container über CSS geladen.
    display: "'Geist', 'Geist Sans', system-ui, sans-serif",
    sans:    "'Geist', 'Geist Sans', system-ui, sans-serif",
    mono:    "'Geist Mono', 'Courier New', monospace",
  },

  // Logo-Pfade (liegen im Container unter /app/brand/, per staticFile geladen)
  logos: {
    weissTransparent: "brand/logo_white_transparent.png",
    dunkelTransparent: "brand/logo_dark_transparent.png",
    aufDunkel:        "brand/logo_on_dark_bg.png",
    aufHell:          "brand/logo_on_light_bg.png",
    solid:            "brand/logo_solid_transparent.png",
  },
};

// Hilfsfunktion: passendes Logo je nach Palette (hell/dunkel)
export function logoFuer(paletteName) {
  if (paletteName === "hell" || paletteName === "limette") {
    return BRAND.logos.dunkelTransparent;  // dunkles Logo auf hellem BG
  }
  return BRAND.logos.weissTransparent;     // weißes Logo auf dunklem BG
}
