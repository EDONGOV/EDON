"""Prometheus metrics integration."""

from typing import Dict, Any, Optional
from collections import defaultdict


class PrometheusMetrics:
    """Prometheus-compatible metrics."""
    
    def __init__(self):
        """Initialize Prometheus metrics."""
        self._counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
    
    def _label_key(self, labels: Optional[Dict[str, str]]) -> str:
        """Convert labels dict to key string."""
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    
    def increment_counter(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Increment a counter."""
        key = self._label_key(labels)
        self._counters[name][key] += 1
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge value."""
        key = self._label_key(labels)
        self._gauges[name][key] = value
    
    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Observe a histogram value."""
        key = self._label_key(labels)
        self._histograms[name][key].append(value)
    
    def get_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        lines = []
        
        # Counters
        for name, labels_dict in self._counters.items():
            for labels, value in labels_dict.items():
                label_str = f"{{{labels}}}" if labels else ""
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{label_str} {value}")
        
        # Gauges
        for name, labels_dict in self._gauges.items():
            for labels, value in labels_dict.items():
                label_str = f"{{{labels}}}" if labels else ""
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{label_str} {value}")
        
        # Histograms (simplified - just sum and count)
        for name, labels_dict in self._histograms.items():
            for labels, values in labels_dict.items():
                if values:
                    label_str = f"{{{labels}}}" if labels else ""
                    lines.append(f"# TYPE {name}_sum counter")
                    lines.append(f"{name}_sum{label_str} {sum(values)}")
                    lines.append(f"# TYPE {name}_count counter")
                    lines.append(f"{name}_count{label_str} {len(values)}")
        
        return "\n".join(lines) if lines else "# No metrics collected yet"
