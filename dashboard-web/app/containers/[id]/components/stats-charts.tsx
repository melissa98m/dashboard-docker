"use client";

import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const HISTORY_LENGTH = 120;
const CHART_HEIGHT = 140;

export interface StatsDataPoint {
  ts: number;
  cpu_percent: number;
  memory_mb: number;
  memory_percent: number;
}

interface StatsChartsProps {
  data: StatsDataPoint[];
  isRunning: boolean;
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function StatsCharts({ data, isRunning }: StatsChartsProps) {
  const cpuChartData = data.map((p) => ({
    ts: p.ts,
    time: formatTime(p.ts),
    value: p.cpu_percent,
  }));

  const ramChartData = data.map((p) => ({
    ts: p.ts,
    time: formatTime(p.ts),
    value: p.memory_mb,
  }));

  const chartStyle = {
    stroke: "var(--link)",
    fill: "color-mix(in srgb, var(--link) 18%, transparent)",
  };

  if (!isRunning || data.length === 0) {
    return (
      <div className="text-slate-400 text-sm mt-2">
        {!isRunning
          ? "Stats indisponibles (conteneur arrêté)."
          : "En attente de données…"}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-400 mb-2">CPU %</h3>
        <div style={{ height: CHART_HEIGHT }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={cpuChartData} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
              <defs>
                <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--link)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--link)" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fontSize: 10, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={[0, "auto"]}
                tick={{ fontSize: 10, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={false}
                width={32}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "0.78rem",
                }}
                labelStyle={{ color: "var(--muted)" }}
                formatter={(value: number) => [`${value.toFixed(2)}%`, "CPU"]}
                labelFormatter={(label) => `Heure: ${label}`}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={chartStyle.stroke}
                fill="url(#cpuGradient)"
                strokeWidth={2}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div>
        <h3 className="text-sm font-semibold text-slate-400 mb-2">RAM (MB)</h3>
        <div style={{ height: CHART_HEIGHT }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={ramChartData} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
              <defs>
                <linearGradient id="ramGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--success)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--success)" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fontSize: 10, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={[0, "auto"]}
                tick={{ fontSize: 10, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={false}
                width={40}
                tickFormatter={(v) => `${v}`}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "0.78rem",
                }}
                labelStyle={{ color: "var(--muted)" }}
                formatter={(value: number) => [`${value.toFixed(2)} MB`, "RAM"]}
                labelFormatter={(label) => `Heure: ${label}`}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="var(--success)"
                fill="url(#ramGradient)"
                strokeWidth={2}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

export { HISTORY_LENGTH };
