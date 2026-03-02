"use client";

import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const CHART_HEIGHT = 140;

export type StatsRangeId = "2m" | "30m" | "2h" | "1d";

export const STATS_RANGE_OPTIONS: {
  id: StatsRangeId;
  label: string;
  intervalSec: number;
  maxPoints: number;
  minPoints: number;
}[] = [
  { id: "2m", label: "2 min", intervalSec: 1, maxPoints: 120, minPoints: 2 },
  { id: "30m", label: "30 min", intervalSec: 5, maxPoints: 360, minPoints: 3 },
  { id: "2h", label: "2 h", intervalSec: 20, maxPoints: 360, minPoints: 5 },
  { id: "1d", label: "1 jour", intervalSec: 60, maxPoints: 120, minPoints: 5 },
];

export interface StatsDataPoint {
  ts: number;
  cpu_percent: number;
  memory_mb: number;
  memory_percent: number;
}

interface StatsChartsProps {
  data: StatsDataPoint[];
  isRunning: boolean;
  range: StatsRangeId;
  onRangeChange: (range: StatsRangeId) => void;
}

function formatTime(ts: number, range: StatsRangeId): string {
  const d = new Date(ts);
  if (range === "1d") {
    return d.toLocaleString("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function StatsCharts({ data, isRunning, range, onRangeChange }: StatsChartsProps) {
  const cpuChartData = data.map((p) => ({
    ts: p.ts,
    time: formatTime(p.ts, range),
    value: p.cpu_percent,
  }));

  const ramChartData = data.map((p) => ({
    ts: p.ts,
    time: formatTime(p.ts, range),
    value: p.memory_mb,
  }));

  const chartStyle = {
    stroke: "var(--link)",
    fill: "color-mix(in srgb, var(--link) 18%, transparent)",
  };

  if (!isRunning) {
    return (
      <div className="text-slate-400 text-sm mt-2">
        Stats indisponibles (conteneur arrêté).
      </div>
    );
  }

  const rangeConfig = STATS_RANGE_OPTIONS.find((o) => o.id === range) ?? STATS_RANGE_OPTIONS[0];
  const minPoints = rangeConfig.minPoints;
  if (data.length < minPoints) {
    return (
      <div className="mt-4">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium text-slate-500">Plage :</span>
          {STATS_RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => onRangeChange(opt.id)}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md border transition-colors ${
                range === opt.id
                  ? "bg-sky-600 border-sky-500 text-white"
                  : "bg-slate-800 border-slate-600 text-slate-400 hover:border-slate-500"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <p className="text-slate-400 text-sm mt-2">
          Pas assez de données ({data.length}/{minPoints} points min.).
        </p>
      </div>
    );
  }

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-xs font-medium text-slate-500">Plage :</span>
        {STATS_RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => onRangeChange(opt.id)}
            className={`px-2.5 py-1 text-xs font-semibold rounded-md border transition-colors ${
              range === opt.id
                ? "bg-sky-600 border-sky-500 text-white"
                : "bg-slate-800 border-slate-600 text-slate-400 hover:border-slate-500"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
    </div>
  );
}
