import type { MapSpec } from "../mapSpec";
import { fmt } from "../utils";
export default function ExactMapThresholds({ spec }: { spec: MapSpec }) {
  return (
    <details className="exact-map-thresholds">
      <summary>Exact numeric color thresholds</summary>
      <div>
        {spec.colors.map((color, index) => (
          <span key={color}>
            <i style={{ background: color }} />
            {fmt(spec.bins[index], 1)} to {fmt(spec.bins[index + 1], 1)}{" "}
            {spec.unit}
          </span>
        ))}
      </div>
    </details>
  );
}
