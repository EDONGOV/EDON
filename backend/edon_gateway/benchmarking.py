"""
Benchmarking Module - Measure and publish key metrics.

Publishes 3 critical numbers:
1. Latency overhead (target: <10-25ms locally, <50ms network)
2. Block rate (% of risky attempts blocked)
3. Bypass resistance (time to integrate, security score)
"""

import time
import statistics
from typing import Dict, Any, List, Optional
from datetime import datetime, UTC
from dataclasses import dataclass


@dataclass
class LatencyMeasurement:
    """Single latency measurement."""
    timestamp: datetime
    endpoint: str
    latency_ms: float
    verdict: str
    cached: bool = False


class BenchmarkCollector:
    """Collects benchmark metrics."""
    
    def __init__(self):
        self.latency_measurements: List[LatencyMeasurement] = []
        self.decision_counts: Dict[str, int] = {}
        self.total_decisions = 0
    
    def record_decision(self, verdict: str, latency_ms: float, endpoint: str = "/execute", cached: bool = False):
        """Record a decision with latency."""
        measurement = LatencyMeasurement(
            timestamp=datetime.now(UTC),
            endpoint=endpoint,
            latency_ms=latency_ms,
            verdict=verdict,
            cached=cached
        )
        self.latency_measurements.append(measurement)
        
        self.decision_counts[verdict] = self.decision_counts.get(verdict, 0) + 1
        self.total_decisions += 1
    
    def get_latency_stats(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """Get latency statistics."""
        measurements = self.latency_measurements
        if endpoint:
            measurements = [m for m in measurements if m.endpoint == endpoint]
        
        if not measurements:
            return {
                "count": 0,
                "median_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "min_ms": 0,
                "max_ms": 0
            }
        
        latencies = [m.latency_ms for m in measurements]
        sorted_latencies = sorted(latencies)
        
        return {
            "count": len(latencies),
            "median_ms": statistics.median(sorted_latencies),
            "p95_ms": sorted_latencies[int(len(sorted_latencies) * 0.95)] if len(sorted_latencies) > 0 else 0,
            "p99_ms": sorted_latencies[int(len(sorted_latencies) * 0.99)] if len(sorted_latencies) > 0 else 0,
            "min_ms": min(sorted_latencies),
            "max_ms": max(sorted_latencies),
            "mean_ms": statistics.mean(sorted_latencies)
        }
    
    def get_block_rate(self) -> Dict[str, Any]:
        """Calculate block rate statistics."""
        if self.total_decisions == 0:
            return {
                "total_decisions": 0,
                "block_rate_percent": 0,
                "allow_rate_percent": 0,
                "escalate_rate_percent": 0
            }
        
        block_count = self.decision_counts.get("BLOCK", 0)
        allow_count = self.decision_counts.get("ALLOW", 0)
        escalate_count = self.decision_counts.get("ESCALATE", 0)
        
        return {
            "total_decisions": self.total_decisions,
            "block_rate_percent": (block_count / self.total_decisions) * 100,
            "allow_rate_percent": (allow_count / self.total_decisions) * 100,
            "escalate_rate_percent": (escalate_count / self.total_decisions) * 100,
            "block_count": block_count,
            "allow_count": allow_count,
            "escalate_count": escalate_count
        }
    
    def get_benchmark_report(self) -> Dict[str, Any]:
        """Get comprehensive benchmark report."""
        latency_stats = self.get_latency_stats()
        block_rate = self.get_block_rate()
        
        # Check if latency targets are met
        latency_target_local = 25  # ms
        latency_target_network = 50  # ms
        
        return {
            "latency": {
                **latency_stats,
                "target_local_ms": latency_target_local,
                "target_network_ms": latency_target_network,
                "meets_local_target": latency_stats["median_ms"] <= latency_target_local,
                "meets_network_target": latency_stats["median_ms"] <= latency_target_network
            },
            "block_rate": block_rate,
            "timestamp": datetime.now(UTC).isoformat()
        }


# Global benchmark collector
_benchmark_collector = BenchmarkCollector()


def get_benchmark_collector() -> BenchmarkCollector:
    """Get global benchmark collector instance."""
    return _benchmark_collector


def measure_latency(func):
    """Decorator to measure function latency."""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        latency_ms = (time.time() - start_time) * 1000
        
        # Try to extract verdict from result
        verdict = "UNKNOWN"
        if isinstance(result, dict):
            verdict = result.get("verdict", "UNKNOWN")
        elif hasattr(result, "verdict"):
            verdict = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)
        
        _benchmark_collector.record_decision(
            verdict=verdict,
            latency_ms=latency_ms,
            endpoint=getattr(func, "__name__", "unknown")
        )
        
        return result
    return wrapper


def get_trust_spec_sheet() -> Dict[str, Any]:
    """Generate trust spec sheet with key metrics.
    
    This is what blitzscaling/adopters will ask for.
    """
    collector = get_benchmark_collector()
    report = collector.get_benchmark_report()
    
    from .security.anti_bypass import get_bypass_resistance_score
    
    bypass_resistance = get_bypass_resistance_score()
    
    # --- schema-tolerant block/allow counts (v1/v2 compatible) ---
    block_rate_obj = report.get("block_rate") or {}
    
    # Preferred keys (newer)
    block_count = block_rate_obj.get("block_count")
    allow_count = block_rate_obj.get("allow_count")
    
    # Alternate keys (older / different naming)
    if block_count is None:
        block_count = block_rate_obj.get("blocked") or block_rate_obj.get("blocks")
    if allow_count is None:
        allow_count = block_rate_obj.get("allowed") or block_rate_obj.get("allows")
    
    # Derive from decisions summary if still missing
    if block_count is None or allow_count is None:
        verdicts = report.get("decisions_by_verdict") or report.get("verdict_counts") or {}
        if block_count is None:
            block_count = verdicts.get("BLOCK")
        if allow_count is None:
            allow_count = verdicts.get("ALLOW")
    
    # Final fallback: 0 instead of crashing
    block_count = int(block_count or 0)
    allow_count = int(allow_count or 0)
    
    return {
        "latency_overhead": {
            "median_ms": report["latency"]["median_ms"],
            "p95_ms": report["latency"]["p95_ms"],
            "target_local_ms": 25,
            "target_network_ms": 50,
            "meets_targets": report["latency"]["meets_local_target"]
        },
        "block_rate": {
            "block_count": block_count,
            "allow_count": allow_count,
            "block_percentage": (block_count / (block_count + allow_count) * 100) if (block_count + allow_count) > 0 else 0.0
        },
        "bypass_resistance": {
            "score": bypass_resistance["score"],
            "max_score": bypass_resistance["max_score"],
            "level": bypass_resistance["level"],
            "factors": bypass_resistance["factors"]
        },
        "integration_time": {
            "estimated_minutes": 5,
            "description": "5-minute migration: Change URL and token header"
        },
        "timestamp": datetime.now(UTC).isoformat()
    }
