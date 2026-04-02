import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  variant?: 'default' | 'success' | 'danger' | 'warning';
  delay?: number;
}

const accentClass: Record<string, string> = {
  default: 'text-primary',
  success: 'text-emerald-400',
  danger: 'text-red-400',
  warning: 'text-amber-400',
};

export function StatCard({
  title,
  value,
  icon: Icon,
  change,
  changeType = 'neutral',
  variant = 'default',
  delay = 0,
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: delay * 0.05, duration: 0.4 }}
      className="glass-card-hover p-5"
    >
      <div
        className="absolute inset-0 opacity-20 rounded-2xl pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at 80% 0%, hsl(142 70% 45% / 0.12) 0%, transparent 70%)',
        }}
      />
      <div className="relative">
        <div className="flex items-start justify-between mb-3">
          <p className="text-muted-foreground text-xs font-medium uppercase tracking-wider">{title}</p>
          <div className={`p-2 rounded-lg bg-white/5 ${accentClass[variant]}`}>
            <Icon size={16} />
          </div>
        </div>
        <p className="text-2xl font-bold text-foreground tabular-nums">{value}</p>
        {change && (
          <p className={`text-xs mt-1 ${
            changeType === 'positive' ? 'text-emerald-400' :
            changeType === 'negative' ? 'text-red-400' : 'text-muted-foreground'
          }`}>
            {change}
          </p>
        )}
      </div>
    </motion.div>
  );
}
