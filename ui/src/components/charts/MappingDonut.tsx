import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { LAYER_COLORS } from "../../utils/colors";

interface MappingDonutProps {
  byLayer: Record<string, number>;
}

export function MappingDonut({ byLayer }: MappingDonutProps) {
  const data = Object.entries(byLayer).map(([key, value]) => ({
    name: key.toUpperCase(),
    value,
    color: LAYER_COLORS[key] ?? "hsl(220, 14%, 46%)",
  }));

  if (data.length === 0) {
    return <div className="text-muted text-sm text-center py-4">No mapping data available</div>;
  }

  return (
    <div style={{ width: "100%", height: 200 }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={75}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "var(--bg-elevated)",
              borderColor: "var(--border)",
              borderRadius: "var(--radius-md)",
              color: "var(--text-primary)",
              fontSize: "12px",
            }}
            formatter={(value: any, name: any) => [`${value} lines`, name]}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
