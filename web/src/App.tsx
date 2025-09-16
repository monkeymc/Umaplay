import defaultConfig from "../../config.json";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Checkbox } from "./components/ui/checkbox";
import { useConfig } from "./hooks/useConfig";
import SkillList from "./components/SkillList";
import PriorityStat from "./components/PriorityStat";
import StatCaps from "./components/StatCaps";
import Mood from "./components/Mood";
import FailChance from "./components/FailChance";
import PrioritizeG1 from "./components/PrioritizeG1";
import CancelConsecutive from "./components/CancelConsecutive";
import { useConfigPreset } from "./hooks/useConfigPreset";
import { useEffect, useState } from "react";

function App() {
  const { activeIndex, activeConfig, presets, setActiveIndex, setNamePreset, savePreset } = useConfigPreset();
  const { config, setConfig, saveConfig } = useConfig(activeConfig ?? defaultConfig);
  const [presetName, setPresetName] = useState<string>("");

  useEffect(() => {
    if (presets[activeIndex]) {
      setPresetName(presets[activeIndex].name);
      setConfig(presets[activeIndex].config ?? defaultConfig);
    } else {
      setPresetName("");
      setConfig(defaultConfig);
    }
  }, [activeIndex, presets, setConfig]);

  const { priority_stat, minimum_mood, maximum_failure, prioritize_g1_race, cancel_consecutive_race, stat_caps, skill } = config;
  const { is_auto_buy_skill, skill_pts_check, skill_list } = skill;

  const setPriorityStat = (newList: string[]) => {
    setConfig((prev) => ({ ...prev, priority_stat: newList }));
  };

  const setMood = (newMood: string) => {
    setConfig((prev) => ({ ...prev, minimum_mood: newMood }));
  };

  const setFail = (newFail: number) => {
    setConfig((prev) => ({ ...prev, maximum_failure: isNaN(newFail) ? 0 : newFail }));
  };

  const setPrioritizeG1 = (newState: boolean) => {
    setConfig((prev) => ({ ...prev, prioritize_g1_race: newState }));
  };

  const setCancelConsecutive = (newState: boolean) => {
    setConfig((prev) => ({ ...prev, cancel_consecutive_race: newState }));
  };

  const setStatCaps = (keys: string, value: number) => {
    setConfig((prev) => ({ ...prev, stat_caps: { ...prev.stat_caps, [keys]: isNaN(value) ? 0 : value } }));
  };

  const setAutoBuySkill = (newState: boolean) => {
    setConfig((prev) => ({ ...prev, skill: { is_auto_buy_skill: newState, skill_pts_check, skill_list } }));
  };

  const setSkillPtsCheck = (newPts: number) => {
    setConfig((prev) => ({ ...prev, skill: { is_auto_buy_skill, skill_pts_check: isNaN(newPts) ? 0 : newPts, skill_list } }));
  };

  const addSkillList = (newList: string) => {
    setConfig((prev) => ({ ...prev, skill: { is_auto_buy_skill, skill_pts_check, skill_list: [newList, ...skill_list] } }));
  };

  const deleteSkillList = (newList: string) => {
    setConfig((prev) => ({ ...prev, skill: { is_auto_buy_skill, skill_pts_check, skill_list: skill_list.filter((s) => s !== newList) } }));
  };

  return (
    <div className="w-full flex justify-center">
      <div className="mt-24 w-3/4">
        <h1 className="text-4xl font-bold">Uma Auto Train</h1>
        <div className="flex flex-col gap-2 mt-4">
          <div className="flex gap-2">
            {presets.map((_, i) => (
              <Button className="w-8 font-medium cursor-pointer" key={_.name} variant={i === activeIndex ? "default" : "outline"} size="sm" onClick={() => setActiveIndex(i)}>
                {i + 1}
              </Button>
            ))}
          </div>
          <Input className="mt-2 w-52" value={presetName} onChange={(e) => setPresetName(e.target.value)} />
        </div>

        <div className="flex flex-col mt-2 gap-4">
          <div className="flex divide-x-2">
            {/* PRIORITY STAT */}
            <PriorityStat priorityStat={priority_stat} setPriorityStat={setPriorityStat} />

            {/* STAT CAPS */}
            <StatCaps statCaps={stat_caps} setStatCaps={setStatCaps} />

            {/* SKILL */}
            <div className="flex flex-col gap-2 w-fit px-4">
              <p className="text-xl">Skill</p>
              <div className="flex flex-col gap-2">
                <label htmlFor="buy-auto-skill" className="flex gap-2 items-center">
                  <span className="text-xl shrink-0">Auto Buy Skill? </span>
                  <Checkbox id="buy-auto-skill" checked={is_auto_buy_skill} onCheckedChange={() => setAutoBuySkill(!is_auto_buy_skill)} />
                </label>
                <label className="flex items-center gap-4">
                  <span className="text-xl shrink-0">Skill Pts Check</span>
                  <Input type="number" min={0} value={skill_pts_check} onChange={(e) => setSkillPtsCheck(e.target.valueAsNumber)} />
                </label>
                <SkillList list={skill_list} addSkillList={addSkillList} deleteSkillList={deleteSkillList} />
              </div>
            </div>
          </div>

          {/* MINIMUM MOOD */}
          <Mood minimumMood={minimum_mood} setMood={setMood} />

          {/* MAX FAIL CHANCE */}
          <FailChance maximumFailure={maximum_failure} setFail={setFail} />

          {/* PRIORITIZE G1 */}
          <PrioritizeG1 prioritizeG1Race={prioritize_g1_race} setPrioritizeG1={setPrioritizeG1} />

          {/* CANCEL CONSECUTIVE RACE */}
          <CancelConsecutive cancelConsecutive={cancel_consecutive_race} setCancelConsecutive={setCancelConsecutive} />
        </div>
        <p className="mt-4">
          Press <span className="font-bold">f1</span> to start/stop the bot.
        </p>
        <Button
          type="button"
          size={"lg"}
          className="px-3 py-1 font-semibold text-lg cursor-pointer mt-6"
          onClick={() => {
            setNamePreset(activeIndex, presetName);
            savePreset(config);
            saveConfig();
          }}
        >
          Save Config
        </Button>
      </div>
    </div>
  );
}

export default App;
