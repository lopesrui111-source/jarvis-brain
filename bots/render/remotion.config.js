import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// Chromium-Flags fuer Server ohne GPU / wenig RAM
Config.setChromiumOpenGlRenderer("angle");
