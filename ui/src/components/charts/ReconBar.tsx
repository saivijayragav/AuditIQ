import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { CLASSIFICATION_COLORS } from "../../utils/colors";

interface ReconBarProps {
  tied: number;
  rounding: number;
  minor: number;
  watch: number;
  material: number;
}

export function ReconBar({ tied, rounding, minor, watch, material }: ReconBarProps) {
  const data = [
    { name: "Tied", count: tied, key: "tied" },
    { name: "Rounding", count: rounding, key: "rounding" },
    { name: "Minor", count: minor, key: "minor" },
    { name: "Watch", count: watch, key: "watch" },
    { name: "Material", count: material, key: "material" },
  ];

  return (
    <div style={{ width: "100%", height: 160 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
          <XAxis type="number" stroke="var(--text-muted)" fontSize={12} tickLine={false} />
          <YAxis
            type="category"
            dataKey="name"
            stroke="var(--text-secondary)"
            fontSize={12}
            tickLine={false}
            width={65}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-elevated)",
              borderColor: "var(--border)",
              borderRadius: "var(--radius-md)",
              color: "var(--text-primary)",
              fontSize: "12px",
            }}
            formatter={(val: any) => [`${val} line items`, "Count"]}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {data.map((entry) => (
              <Cell
                key={entry.key}
                fill={CLASSIFICATION_COLORS[entry.key] ?? "var(--text-secondary)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
