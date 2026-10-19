import "./Metric.css";

interface MetricProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  icon?: React.ReactNode;
}

export function Metric({ label, value, sub, color, icon }: MetricProps) {
  return (
    <div className="metric">
      <div className="metric__label">
        {icon && <span className="metric__icon">{icon}</span>}
        {label}
      </div>
      <div
        className="metric__value tabular"
        style={color ? { color } : undefined}
      >
        {value}
      </div>
      {sub && <div className="metric__sub">{sub}</div>}
    </div>
  );
}
