import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { TrendingUp } from 'lucide-react';
import { edonApi, BlockReason } from '@/lib/api';

type TopReasonsChartProps = { supported?: boolean };

export function TopReasonsChart({ supported = true }: TopReasonsChartProps) {
  const [data, setData] = useState<BlockReason[]>([]);
  const [loading, setLoading] = useState(supported);
  const didRun = useRef(false);

  useEffect(() => {
    if (!supported) {
      setData([]);
      setLoading(false);
      didRun.current = false;
      return;
    }
    setData([]);
    setLoading(true);
    didRun.current = false;
  }, [supported]);

  useEffect(() => {
    if (!supported || didRun.current) return;
    didRun.current = true;

    const fetchData = async () => {
      try {
        const result = await edonApi.getBlockReasons(7);
        setData(Array.isArray(result) ? result : []);
      } catch {
        setData([]);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [supported]);

  const maxCount = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="glass-card p-4">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="w-3.5 h-3.5 text-red-400" />
        <h3 className="font-semibold text-sm text-foreground">Top Block Reasons</h3>
      </div>

      {!supported ? (
        <p className="text-xs text-muted-foreground text-center py-8">
          Not supported by this gateway build.
        </p>
      ) : loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="space-y-1">
              <div className="h-3 bg-white/5 rounded animate-pulse w-3/4" />
              <div className="h-1.5 bg-white/5 rounded-full animate-pulse" />
            </div>
          ))}
        </div>
      ) : data.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-8">
          No blocked decisions in the last 7 days.
        </p>
      ) : (
        <div className="space-y-3">
          {data.map((r, i) => (
            <div key={r.reason}>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-muted-foreground">{r.reason}</span>
                <span className="text-foreground font-medium">{r.count}</span>
              </div>
              <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${(r.count / maxCount) * 100}%` }}
                  transition={{ delay: i * 0.05, duration: 0.6 }}
                  className="h-full rounded-full bg-red-400"
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
