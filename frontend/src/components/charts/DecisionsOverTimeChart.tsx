import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { edonApi, TimeSeriesPoint } from '@/lib/api';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

type DecisionsOverTimeChartProps = { supported?: boolean };

export function DecisionsOverTimeChart({ supported = true }: DecisionsOverTimeChartProps) {
  const [data, setData] = useState<TimeSeriesPoint[] | null>(supported ? [] : null);
  const [timeRange, setTimeRange] = useState<'24h' | '7d'>('24h');
  const [loading, setLoading] = useState(supported);
  const didRun = useRef(false);

  useEffect(() => {
    if (!supported) {
      setData(null);
      setLoading(false);
      return;
    }
    setData([]);
    setLoading(true);
    didRun.current = false;
  }, [supported, timeRange]);

  useEffect(() => {
    if (!supported || didRun.current) return;
    didRun.current = true;

    const fetchData = async () => {
      setLoading(true);
      try {
        const days = timeRange === '24h' ? 1 : 7;
        const result = await edonApi.getTimeSeriesData(days);
        setData(Array.isArray(result) ? result : []);
      } catch {
        setData([]);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [supported, timeRange]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="glass-card p-6"
    >
      <div className="flex items-center justify-between mb-6">
        <h3 className="font-semibold">Decisions Over Time</h3>
        <Tabs value={timeRange} onValueChange={(v) => setTimeRange(v as '24h' | '7d')}>
          <TabsList className="bg-white/5">
            <TabsTrigger value="24h" className="text-xs">24h</TabsTrigger>
            <TabsTrigger value="7d" className="text-xs">7d</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {!supported || data === null ? (
        <div className="h-[300px] flex items-center justify-center text-sm text-muted-foreground">
          Not supported by this gateway build.
        </div>
      ) : loading ? (
        <div className="h-[300px] flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="gradientAllowed" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(142 76% 50%)" stopOpacity={0.4} />
                <stop offset="95%" stopColor="hsl(142 76% 50%)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradientBlocked" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(0 84% 60%)" stopOpacity={0.4} />
                <stop offset="95%" stopColor="hsl(0 84% 60%)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradientConfirm" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(38 92% 50%)" stopOpacity={0.4} />
                <stop offset="95%" stopColor="hsl(38 92% 50%)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis 
              dataKey="label" 
              stroke="rgba(255,255,255,0.4)"
              tick={{ fill: 'rgba(255,255,255,0.6)', fontSize: 12 }}
              axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            />
            <YAxis 
              stroke="rgba(255,255,255,0.4)"
              tick={{ fill: 'rgba(255,255,255,0.6)', fontSize: 12 }}
              axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(240 10% 12% / 0.9)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '12px',
                boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
              }}
              labelStyle={{ color: 'rgba(255,255,255,0.8)' }}
            />
            <Legend 
              wrapperStyle={{ paddingTop: '20px' }}
              iconType="circle"
            />
            <Area
              type="monotone"
              dataKey="allowed"
              stroke="hsl(142 76% 50%)"
              strokeWidth={2}
              fill="url(#gradientAllowed)"
              name="Allowed"
            />
            <Area
              type="monotone"
              dataKey="blocked"
              stroke="hsl(0 84% 60%)"
              strokeWidth={2}
              fill="url(#gradientBlocked)"
              name="Blocked"
            />
            <Area
              type="monotone"
              dataKey="confirm"
              stroke="hsl(38 92% 50%)"
              strokeWidth={2}
              fill="url(#gradientConfirm)"
              name="Confirm"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </motion.div>
  );
}
