// Zentrales Büroflow-Brandkit für alle Motion-Design-Kompositionen.
// Quelle: app/globals.css + public/brand/README.md des Büroflow-Repos.
// Einmal definiert — jede Komposition zieht Farben/Fonts/Logos von hier.

import { loadFont as loadBricolage } from "@remotion/google-fonts/BricolageGrotesque";
import { loadFont as loadInstrument } from "@remotion/google-fonts/InstrumentSerif";
import { loadFont as loadDMSans } from "@remotion/google-fonts/DMSans";

// Fonts werden beim Modul-Start geladen, damit sie im Render sicher da sind.
const bricolage = loadBricolage("normal", { weights: ["400", "500", "600", "700", "800"] });
const instrument = loadInstrument("italic", { weights: ["400"] });
const dmSans = loadDMSans("normal", { weights: ["400", "500", "600", "700"] });

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

  // ═══ TYPOGRAFIE ═══
  // Das Prinzip: KRAEFTIGE SANS fuer die Hauptaussage, ELEGANTE KURSIVE SERIF
  // fuer das betonte Wort. Diese Mischung erzeugt Spannung und wirkt sofort
  // hochwertiger als eine durchgehende Sans.
  // Beispiel: "Schluss mit dem" (Sans, weiss) + "Papierkram." (Serif kursiv, Akzentfarbe)
  //
  // Bricolage Grotesque ist zusaetzlich die Schrift des echten Bueroflow-
  // Dashboards — dadurch passen Video und Produkt visuell zusammen.
  fonts: {
    display: `'${bricolage.fontFamily}', 'Geist', system-ui, sans-serif`,
    akzent:  `'${instrument.fontFamily}', Georgia, serif`,   // IMMER kursiv setzen
    sans:    `'${dmSans.fontFamily}', 'Geist', system-ui, sans-serif`,
    mono:    "'Geist Mono', 'JetBrains Mono', 'Courier New', monospace",
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

// Fertiger Baustein fuer die Sans/Serif-Mischung.
// text: "Schluss mit dem", akzentText: "Papierkram."
// Der Akzentteil wird automatisch kursiv in der Akzentfarbe gesetzt.
export function mischSatz({ text, akzentText, groesse, p, weiss = "#FFFFFF", zentriert = false }) {
  return {
    container: {
      display: "flex", flexDirection: "column",
      alignItems: zentriert ? "center" : "flex-start",
      lineHeight: 1.02,
    },
    sans: {
      fontFamily: BRAND.fonts.display,
      fontSize: groesse, fontWeight: 700,
      color: weiss, letterSpacing: "-0.03em",
    },
    serif: {
      fontFamily: BRAND.fonts.akzent,
      fontStyle: "italic",
      fontSize: groesse * 1.06,     // Serif wirkt optisch kleiner -> leicht groesser setzen
      fontWeight: 400,
      color: p.akzent, letterSpacing: "-0.01em",
    },
  };
}
