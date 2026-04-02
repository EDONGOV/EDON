"""Async audit write queue. Decouples audit persistence from request latency."""
import asyncio
import logging
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_QUEUE_MAX = int(os.getenv("EDON_AUDIT_QUEUE_MAX", "1000"))


@dataclass
class AuditTask:
    action: Dict[str, Any]
    decision: Dict[str, Any]
    intent_id: Optional[str]
    agent_id: Optional[str]
    context: Dict[str, Any]
    customer_id: Optional[str]
    processing_latency_ms: Optional[float]
    anomaly_score: Optional[float]
    stated_intent: Optional[str]
    user_message: Optional[str]
    action_summary: Optional[str]
    policy_rule_id: Optional[str]


_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None


def get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    return _queue


async def start_worker(db) -> None:
    """Start background worker consuming the audit queue."""
    global _worker_task
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
                )
            except Exception as exc:
                logger.error("Async audit write failed: %s", exc)
            finally:
                q.task_done()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Audit worker error: %s", exc)


async def stop_worker(timeout_sec: float = 10.0) -> None:
    """Drain the audit queue and stop the background worker.

    Called on application shutdown to ensure no pending audit events are lost.
    Waits up to `timeout_sec` for the queue to drain before forcefully cancelling.
    """
    global _worker_task
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
    if _worker_task is not None and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
        logger.info("Audit queue worker stopped")


async def enqueue_audit(task: AuditTask, db) -> Optional[str]:
    """Non-blocking enqueue. Falls back to sync write if queue is full."""
    q = get_queue()
    try:
        q.put_nowait(task)
        return None  # ID will be assigned by worker; caller gets None
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
        )
