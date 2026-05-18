"""Async audit write queue. Decouples audit persistence from request latency."""
import asyncio
import logging
import os
from datetime import datetime, UTC
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_QUEUE_MAX = int(os.getenv("EDON_AUDIT_QUEUE_MAX", "1000"))


@dataclass
class AuditTask:
    action: Dict[str, Any]
    decision: Dict[str, Any]
    context: Dict[str, Any]
    intent_id: Optional[str] = None
    agent_id: Optional[str] = None
    customer_id: Optional[str] = None
    processing_latency_ms: Optional[float] = None
    anomaly_score: Optional[float] = None
    stated_intent: Optional[str] = None
    user_message: Optional[str] = None
    action_summary: Optional[str] = None
    policy_rule_id: Optional[str] = None
    request_hash: Optional[str] = None  # SHA-256 of action params; ties audit record to exact request
    decision_id: Optional[str] = None
    created_at_override: Optional[str] = None


_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None

# SSE pub-sub: list of asyncio.Queue objects — one per connected SIEM subscriber
_sse_subscribers: list = []


def subscribe_sse(maxsize: int = 200) -> asyncio.Queue:
    """Register a new SSE subscriber queue. Returns the queue to drain."""
    q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    _sse_subscribers.append(q)
    return q


def unsubscribe_sse(q: asyncio.Queue) -> None:
    """Deregister an SSE subscriber (called on disconnect)."""
    try:
        _sse_subscribers.remove(q)
    except ValueError:
        pass


def get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    return _queue


async def start_worker(db) -> None:
    """Start background worker consuming the audit queue."""
    global _worker_task, _queue
    # Always create a fresh queue bound to the current event loop.
    # Reusing a queue from a previous loop (e.g. after test teardown) causes
    # "bound to a different event loop" on shutdown.
    _queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _worker_task = asyncio.create_task(_worker_loop(db))
    logger.info("Audit queue worker started (max_size=%d)", _QUEUE_MAX)


async def _worker_loop(db) -> None:
    q = get_queue()
    while True:
        try:
            task: AuditTask = await q.get()
            try:
                db.save_audit_event(
                    action=task.action,
                    decision=task.decision,
                    intent_id=task.intent_id,
                    agent_id=task.agent_id,
                    context=task.context,
                    customer_id=task.customer_id,
                    processing_latency_ms=task.processing_latency_ms,
                    anomaly_score=task.anomaly_score,
                    stated_intent=task.stated_intent,
                    user_message=task.user_message,
                    action_summary=task.action_summary,
                    policy_rule_id=task.policy_rule_id,
                    request_hash=task.request_hash,
                    decision_id_override=task.decision_id,
                    created_at_override=task.created_at_override,
                )
                _broadcast_sse(task)
            except Exception as exc:
                logger.error("Async audit write failed: %s", exc)
            finally:
                q.task_done()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Audit worker error: %s", exc)


def _broadcast_sse(task: AuditTask) -> None:
    """Push a compact event dict to all active SSE subscribers. Drops on full queue."""
    if not _sse_subscribers:
        return
    event_dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": task.agent_id,
        "intent_id": task.intent_id,
        "action_tool": (task.action or {}).get("tool"),
        "action_op": (task.action or {}).get("op"),
        "action_id": (task.action or {}).get("id"),
        "verdict": (task.decision or {}).get("verdict"),
        "reason_code": (task.decision or {}).get("reason_code"),
        "explanation": (task.decision or {}).get("explanation"),
        "anomaly_score": task.anomaly_score,
        "tenant_id": task.customer_id,
    }
    for sub_q in list(_sse_subscribers):
        try:
            sub_q.put_nowait(event_dict)
        except asyncio.QueueFull:
            pass  # slow consumer — drop rather than block


async def stop_worker(timeout_sec: float = 10.0) -> None:
    """Drain the audit queue and stop the background worker.

    Called on application shutdown to ensure no pending audit events are lost.
    Waits up to `timeout_sec` for the queue to drain before forcefully cancelling.
    """
    global _worker_task, _queue
    if _queue is not None and not _queue.empty():
        logger.info("Draining audit queue (%d pending events)...", _queue.qsize())
        try:
            await asyncio.wait_for(_queue.join(), timeout=timeout_sec)
            logger.info("Audit queue drained successfully")
        except asyncio.TimeoutError:
            logger.warning(
                "Audit queue drain timed out after %.1fs — %d events may be lost",
                timeout_sec,
                _queue.qsize(),
            )
        except RuntimeError as exc:
            if "bound to a different event loop" in str(exc):
                # Queue was created in a different event loop (common in tests).
                # The worker has already stopped; pending events in that loop are gone.
                logger.warning("Audit queue shutdown: loop mismatch, pending events discarded")
            else:
                raise
    if _worker_task is not None and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None
    _queue = None  # release reference so next start_worker() binds to the new loop
    logger.info("Audit queue worker stopped")


async def enqueue_audit(task: AuditTask, db) -> Optional[str]:
    """Non-blocking enqueue. Falls back to sync write if queue is full."""
    q = get_queue()
    try:
        q.put_nowait(task)
        return task.decision_id
    except asyncio.QueueFull:
        logger.warning("Audit queue full — falling back to sync write")
        return db.save_audit_event(
            action=task.action,
            decision=task.decision,
            intent_id=task.intent_id,
            agent_id=task.agent_id,
            context=task.context,
            customer_id=task.customer_id,
            processing_latency_ms=task.processing_latency_ms,
            anomaly_score=task.anomaly_score,
            stated_intent=task.stated_intent,
            user_message=task.user_message,
            action_summary=task.action_summary,
            policy_rule_id=task.policy_rule_id,
            request_hash=task.request_hash,
            decision_id_override=task.decision_id,
            created_at_override=task.created_at_override,
        )
    return task.decision_id
