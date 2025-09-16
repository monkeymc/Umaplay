import { useState, useEffect } from "react";
import type { Config } from "../types";
import defaultConfig from "../../../config.json";

const STORAGE_KEY = "uma-config";
const MAX_PRESET = 10;

type Preset = {
  name: string;
  config: Config;
};

type PresetStorage = {
  index: number;
  presets: Preset[];
};

export function useConfigPreset() {
  const [presetStorage, setPresetStorage] = useState<PresetStorage>({
    index: 0,
    presets: [],
  });

  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed: PresetStorage = JSON.parse(saved);
      setPresetStorage(parsed);
      setActiveIndex(parsed.index);
    } else {
      const defaultPresets = Array.from({ length: MAX_PRESET }, (_, i) => ({
        name: `Preset ${i + 1}`,
        config: defaultConfig,
      }));
      const init = { index: 0, presets: defaultPresets };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(init));
      setPresetStorage(init);
      setActiveIndex(0);
    }
  }, []);

  const setNamePreset = (i: number, newName: string) => {
    setPresetStorage((prev) => {
      const newPresets = [...prev.presets];
      newPresets[i] = { ...newPresets[i], name: newName };
      const next = { ...prev, presets: newPresets };
      return next;
    });
  };

  const updatePreset = (i: number, newConfig: Config) => {
    setPresetStorage((prev) => {
      const newPresets = [...prev.presets];
      newPresets[i] = { ...newPresets[i], config: newConfig };
      const next = { ...prev, presets: newPresets };
      return next;
    });
  };

  const savePreset = (config: Config) => {
    setPresetStorage((prev) => {
      const newPresets = [...prev.presets];
      newPresets[activeIndex] = { ...newPresets[activeIndex], config };
      const next = { ...prev, index: activeIndex, presets: newPresets };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  return {
    activeIndex,
    activeConfig: presetStorage.presets[activeIndex]?.config,
    presets: presetStorage.presets,
    setActiveIndex,
    setNamePreset,
    updatePreset,
    savePreset,
  };
}
