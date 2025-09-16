import { Checkbox } from "./ui/checkbox";

type Props = {
  prioritizeG1Race: boolean;
  setPrioritizeG1: (newState: boolean) => void;
};

export default function PrioritizeG1({ prioritizeG1Race, setPrioritizeG1 }: Props) {
  return (
    <div className="w-fit px-4">
      <label htmlFor="prioritize-g1" className="flex gap-2 items-center">
        <span className="text-xl shrink-0">Prioritize G1 Race?</span>
        <Checkbox id="prioritize-g1" checked={prioritizeG1Race} onCheckedChange={() => setPrioritizeG1(!prioritizeG1Race)} />
      </label>
    </div>
  );
}
