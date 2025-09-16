import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { MOOD } from "@/constants";

type Props = {
  minimumMood: string;
  setMood: (newMood: string) => void;
};

export default function Mood({ minimumMood, setMood }: Props) {
  return (
    <div className="w-fit px-4">
      <label htmlFor="mood" className="flex gap-2 items-center">
        <span className="text-xl">Minimum Mood</span>
        <Select value={minimumMood} onValueChange={(val) => setMood(val)}>
          <SelectTrigger className="w-28">
            <SelectValue placeholder="Mood" />
          </SelectTrigger>
          <SelectContent>
            {MOOD.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>
    </div>
  );
}
