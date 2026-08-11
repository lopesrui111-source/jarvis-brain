import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(95);       // hoehere Frame-Qualitaet (Standard 80) fuer scharfes UI
Config.setOverwriteOutput(true);
Config.setCrf(18);               // schaerferes Video (niedriger = besser, Standard 18-23)
// Chromium-Flags fuer Server ohne GPU / wenig RAM
Config.setChromiumOpenGlRenderer("angle");
