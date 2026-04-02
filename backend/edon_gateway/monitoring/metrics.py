"""Metrics collection for EDON Gateway."""

from typing import Dict, Any
from datetime import datetime, UTC
from .prometheus import PrometheusMetrics


class MetricsCollector:
    """Collects and exposes metrics for monitoring."""
    
    def __init__(self):
        """Initialize metrics collector."""
        self.prometheus = PrometheusMetrics()
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list] = {}
    
    def increment_counter(self, name: str, labels: Dict[str, str] = None):
        """Increment a counter metric."""
        key = f"{name}:{labels or {}}"
        self._counters[key] = self._counters.get(key, 0) + 1
        self.prometheus.increment_counter(name, labels)
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric."""
        key = f"{name}:{labels or {}}"
        self._gauges[key] = value
        self.prometheus.set_gauge(name, value, labels)
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a histogram value."""
        key = f"{name}:{labels or {}}"
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        self.prometheus.observe_histogram(name, value, labels)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics as dictionary."""
        return {
            "counters": self._counters,
            "gauges": self._gauges,
            "histograms": {
                k: {
                    "count": len(v),
                    "sum": sum(v),
                    "min": min(v) if v else 0,
                    "max": max(v) if v else 0,
                    "avg": sum(v) / len(v) if v else 0
                }
                for k, v in self._histograms.items()
            },
            "prometheus": self.prometheus.get_metrics()
        }


# Global metrics instance
metrics = MetricsCollector()
