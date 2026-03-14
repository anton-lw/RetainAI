import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RetentionCurves } from "./types";

interface RetentionChartProps {
  curves: RetentionCurves;
}

function RetentionChart({ curves }: RetentionChartProps) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={curves.data}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(15, 23, 42, 0.08)" />
        <XAxis dataKey="period" stroke="#475569" />
        <YAxis domain={[70, 100]} stroke="#475569" />
        <Tooltip />
        <Legend />
        {curves.series.map((series) => (
          <Line
            key={series.key}
            type="monotone"
            dataKey={series.key}
            name={series.label}
            stroke={series.color}
            strokeWidth={3}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export default RetentionChart;
