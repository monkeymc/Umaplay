import { Checkbox } from "./ui/checkbox";

type Props = {
  cancelConsecutive: boolean;
  setCancelConsecutive: (newState: boolean) => void;
};

export default function CancelConsecutive({ cancelConsecutive, setCancelConsecutive }: Props) {
  return (
    <div className="w-fit px-4">
      <label htmlFor="prioritize-g1" className="flex gap-2 items-center">
        <span className="text-xl shrink-0">Cancel Consecutive Race?</span>
        <Checkbox id="prioritize-g1" checked={cancelConsecutive} onCheckedChange={() => setCancelConsecutive(!cancelConsecutive)} />
      </label>
    </div>
  );
}
