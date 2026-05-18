"""EDON Bootstrap Parser.

Converts three artifact types into a normalized ParsedSystem:

  1. OpenAPI spec  (JSON or YAML) — extracts endpoints, auth schemes, data models
  2. Agent config  (JSON)         — extracts agent IDs, tool lists, permission levels
  3. Log sample    (JSONL)        — extracts agent→action→payload patterns from real traffic

Design rules:
  - Never makes assumptions beyond what the artifact contains
  - Schema-derived paths are tagged verified=False (no trace evidence yet)
  - Log-derived paths are tagged verified=True (real traffic observed)
  - Fail-open: partial parse always beats a crash
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Sensitive field detection ──────────────────────────────────────────────────

_PHI_PATTERNS  = re.compile(r"\b(patient|mrn|diagnosis|medication|dob|npi|ssn|health|clinical|"
                             r"medical|prescription|lab_result|icd|hipaa)\b", re.I)
_PII_PATTERNS  = re.compile(r"\b(email|name|phone|address|user_id|user_email|first_name|"
                             r"last_name|birth|gender|location|ip_address|device_id)\b", re.I)
_PCI_PATTERNS  = re.compile(r"\b(card|cvv|pan|account_number|routing|billing|payment|"
                             r"credit|debit|stripe|transaction)\b", re.I)
_AUTH_PATTERNS = re.compile(r"\b(token|api_key|secret|password|credential|auth|bearer|"
                             r"oauth|jwt|session|cookie)\b", re.I)


def _infer_data_classes(text: str) -> list[str]:
    """Infer data sensitivity classes from field names / schema text."""
    classes = []
    if _PHI_PATTERNS.search(text):
        classes.append("PHI")
    if _PCI_PATTERNS.search(text):
        classes.append("PCI")
    if _PII_PATTERNS.search(text):
        classes.append("PII")
    if _AUTH_PATTERNS.search(text):
        classes.append("AUTH")
    return classes or ["INTERNAL"]


# ── HTTP method → EDON operation mapping ──────────────────────────────────────

_HTTP_TO_OP: dict[str, str] = {
    "get":    "read",
    "post":   "create",
    "put":    "update",
    "patch":  "update",
    "delete": "delete",
    "head":   "read",
    "options": "read",
}

# URL path pattern → EDON tool type
_PATH_TO_TOOL: list[tuple[re.Pattern, str]] = [
    (re.compile(r"/auth|/login|/token|/oauth|/session", re.I), "auth"),
    (re.compile(r"/user|/account|/profile|/customer", re.I),   "database"),
    (re.compile(r"/payment|/billing|/invoice|/charge", re.I),  "billing"),
    (re.compile(r"/file|/upload|/download|/storage|/blob", re.I), "file"),
    (re.compile(r"/email|/mail|/message|/notify|/send", re.I), "email"),
    (re.compile(r"/slack|/discord|/chat|/webhook", re.I),       "slack"),
    (re.compile(r"/github|/repo|/code|/deploy|/ci", re.I),      "github"),
    (re.compile(r"/admin|/internal|/manage|/config", re.I),     "shell"),
    (re.compile(r"/agent|/ai|/llm|/completion|/chat", re.I),    "agent"),
    (re.compile(r"/search|/query|/find", re.I),                 "database"),
    (re.compile(r"/health|/status|/ping", re.I),                "http"),
]

_DEFAULT_TOOL = "http"


def _path_to_tool(path: str) -> str:
    for pattern, tool in _PATH_TO_TOOL:
        if pattern.search(path):
            return tool
    return _DEFAULT_TOOL


# ── Output model ───────────────────────────────────────────────────────────────

@dataclass
class ParsedAgent:
    agent_id: str
    tools: list[str]              # tool names this agent can call
    operations: dict[str, list[str]]  # tool → list of operations
    permission_level: str         # "read_only" | "read_write" | "admin" | "unknown"
    source: str                   # "agent_config" | "log" | "openapi"


@dataclass
class ParsedEndpoint:
    path: str
    method: str
    tool: str                     # mapped EDON tool type
    operation: str                # EDON operation
    data_classes: list[str]
    auth_required: bool
    is_external: bool             # does this path talk to external systems?
    description: str = ""


@dataclass
class ParsedLogEdge:
    agent_id: str
    action_type: str              # "tool.op" format
    payload_keys: list[str]
    data_classes: list[str]
    count: int = 1
    sample_verdict: Optional[str] = None


@dataclass
class ParsedSystem:
    """Normalized representation of a customer's system from static artifacts."""
    tenant_id: Optional[str]
    agents:    list[ParsedAgent]       = field(default_factory=list)
    endpoints: list[ParsedEndpoint]    = field(default_factory=list)
    log_edges: list[ParsedLogEdge]     = field(default_factory=list)
    source_types: list[str]            = field(default_factory=list)  # which artifacts were provided
    parse_warnings: list[str]          = field(default_factory=list)

    @property
    def has_traffic(self) -> bool:
        return bool(self.log_edges)

    @property
    def has_schema(self) -> bool:
        return bool(self.endpoints)

    @property
    def has_agents(self) -> bool:
        return bool(self.agents)


# ── OpenAPI parser ─────────────────────────────────────────────────────────────

def _extract_schema_data_classes(schema: dict, depth: int = 0) -> list[str]:
    """Recursively extract data class hints from a JSON Schema object."""
    if depth > 4 or not isinstance(schema, dict):
        return []
    classes: set[str] = set()
    # Check property names
    for key in list(schema.get("properties", {}).keys()):
        classes.update(_infer_data_classes(key))
    # Check description
    desc = schema.get("description", "") + " " + schema.get("title", "")
    classes.update(_infer_data_classes(desc))
    # Recurse into nested schemas
    for prop in schema.get("properties", {}).values():
        classes.update(_extract_schema_data_classes(prop, depth + 1))
    for sub in ["items", "additionalProperties"]:
        if sub in schema:
            classes.update(_extract_schema_data_classes(schema[sub], depth + 1))
    return list(classes) or ["INTERNAL"]


def parse_openapi(spec: dict, tenant_id: Optional[str] = None) -> list[ParsedEndpoint]:
    """Parse an OpenAPI 3.x or Swagger 2.x spec into ParsedEndpoint list."""
    endpoints: list[ParsedEndpoint] = []
    paths = spec.get("paths", {})

    # Detect auth schemes
    security_schemes = (
        spec.get("components", {}).get("securitySchemes", {})
        or spec.get("securityDefinitions", {})
    )
    has_global_auth = bool(spec.get("security") or security_schemes)

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        tool = _path_to_tool(path)

        for http_method in ["get", "post", "put", "patch", "delete", "head"]:
            operation = path_item.get(http_method)
            if not isinstance(operation, dict):
                continue

            op_name = _HTTP_TO_OP.get(http_method, "unknown")

            # Collect data class signals from: path, description, request body, response schemas
            signals = path + " " + operation.get("summary", "") + " " + operation.get("description", "")
            data_classes: set[str] = set(_infer_data_classes(signals))

            # Request body schema
            req_body = operation.get("requestBody", {})
            for content in req_body.get("content", {}).values():
                schema = content.get("schema", {})
                data_classes.update(_extract_schema_data_classes(schema))

            # Parameter names
            for param in operation.get("parameters", []):
                data_classes.update(_infer_data_classes(param.get("name", "")))

            # Response schemas
            for resp in operation.get("responses", {}).values():
                if isinstance(resp, dict):
                    for content in resp.get("content", {}).values():
                        data_classes.update(_extract_schema_data_classes(content.get("schema", {})))

            # Auth: operation-level override or fall back to global
            op_security = operation.get("security")
            auth_required = (op_security is not None and len(op_security) > 0) or has_global_auth

            # External sink: external URLs in servers, or known external paths
            is_external = tool in ("email", "slack", "http", "browser", "discord", "github")

            endpoints.append(ParsedEndpoint(
                path=path,
                method=http_method.upper(),
                tool=tool,
                operation=op_name,
                data_classes=list(data_classes) or ["INTERNAL"],
                auth_required=auth_required,
                is_external=is_external,
                description=operation.get("summary", "")[:120],
            ))

    logger.info("[bootstrap/parser] openapi: %d endpoints extracted", len(endpoints))
    return endpoints


# ── Agent config parser ────────────────────────────────────────────────────────

def _permission_from_operations(ops: list[str]) -> str:
    """Infer permission level from operation list."""
    ops_lower = {o.lower() for o in ops}
    admin_ops = {"delete", "drop", "exec", "execute", "admin", "grant", "deploy"}
    write_ops = {"write", "create", "update", "send", "post", "put", "patch"}
    if ops_lower & admin_ops:
        return "admin"
    if ops_lower & write_ops:
        return "read_write"
    if ops_lower:
        return "read_only"
    return "unknown"


def parse_agent_config(config: dict | list) -> list[ParsedAgent]:
    """Parse an agent config into ParsedAgent list.

    Supports multiple formats:
      - EDON format: {"agents": [{"id": "...", "tools": [...]}]}
      - OpenAI/Anthropic format: {"tools": [{"name": "...", "description": "..."}]}
      - Array of tool definitions
      - Single agent object
    """
    agents: list[ParsedAgent] = []

    # Normalise to list of agent dicts
    if isinstance(config, list):
        # Could be a list of tools (OpenAI format) or a list of agents
        first = config[0] if config else {}
        if isinstance(first, dict) and ("name" in first or "function" in first):
            # OpenAI / Anthropic tool list — treat as single agent
            config = [{"id": "agent_0", "tools": config}]
        # Otherwise treat as list of agent objects
    elif isinstance(config, dict):
        if "agents" in config:
            config = config["agents"]
        elif "tools" in config and not "id" in config and not "agent_id" in config:
            # Top-level tools list for a single agent
            config = [{"id": config.get("name", "agent_0"), "tools": config["tools"]}]
        else:
            config = [config]

    for raw in config:
        if not isinstance(raw, dict):
            continue

        agent_id = (
            raw.get("id") or raw.get("agent_id") or raw.get("name") or "unknown_agent"
        )

        # Extract tool list — handle OpenAI / Anthropic / EDON formats
        raw_tools = raw.get("tools") or raw.get("capabilities") or raw.get("functions") or []
        tool_names: list[str] = []
        tool_ops: dict[str, list[str]] = {}

        for t in raw_tools:
            if isinstance(t, str):
                tool_names.append(t)
                tool_ops[t] = ["unknown"]
            elif isinstance(t, dict):
                # OpenAI: {"type": "function", "function": {"name": "...", "parameters": {...}}}
                fn = t.get("function") or t
                name = fn.get("name") or t.get("name") or t.get("type") or "unknown"
                # Infer tool type from name
                tool_type = _path_to_tool("/" + name.replace("_", "/"))
                ops = []
                # Try to infer operation from name
                for op_word in ["read", "write", "create", "update", "delete",
                                "send", "get", "list", "search", "run", "execute"]:
                    if op_word in name.lower():
                        ops.append(op_word)
                        break
                if not ops:
                    ops = ["call"]
                tool_names.append(tool_type)
                existing = tool_ops.get(tool_type, [])
                tool_ops[tool_type] = list(set(existing + ops))

        # Deduplicate tool names
        tool_names = list(set(tool_names))
        all_ops = [op for ops in tool_ops.values() for op in ops]
        permission = _permission_from_operations(all_ops)

        agents.append(ParsedAgent(
            agent_id=agent_id,
            tools=tool_names,
            operations=tool_ops,
            permission_level=permission,
            source="agent_config",
        ))

    logger.info("[bootstrap/parser] agent_config: %d agents extracted", len(agents))
    return agents


# ── Log parser (JSONL) ─────────────────────────────────────────────────────────

# Flexible field name mappings for log line parsing
_AGENT_FIELDS  = ("agent_id", "agent", "source", "caller", "service", "client_id")
_ACTION_FIELDS = ("action_type", "action", "tool", "event", "operation", "method", "type")
_PAYLOAD_FIELDS = ("action_payload", "payload", "params", "parameters", "body", "data", "request")
_VERDICT_FIELDS = ("decision", "verdict", "result", "status", "outcome")


def _pick(d: dict, candidates: tuple) -> Optional[str]:
    for k in candidates:
        if k in d:
            return str(d[k])
    return None


def _pick_dict(d: dict, candidates: tuple) -> dict:
    for k in candidates:
        if k in d and isinstance(d[k], dict):
            return d[k]
    return {}


def parse_log_sample(lines: list[str]) -> list[ParsedLogEdge]:
    """Parse JSONL log lines into ParsedLogEdge list.

    Aggregates identical agent+action_type patterns, counting occurrences.
    Fail-open: unparseable lines are skipped with a debug log.
    """
    edge_counts: dict[tuple, dict] = {}  # (agent_id, action_type) → aggregated edge

    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("[bootstrap/parser] skipping non-JSON log line %d", i)
            continue

        if not isinstance(record, dict):
            continue

        agent_id    = _pick(record, _AGENT_FIELDS) or "unknown"
        action_type = _pick(record, _ACTION_FIELDS) or "unknown.unknown"
        payload     = _pick_dict(record, _PAYLOAD_FIELDS)
        verdict     = _pick(record, _VERDICT_FIELDS)

        # Normalise action_type to "tool.op" format
        if "." not in action_type:
            # Try to infer from HTTP method + path patterns
            action_type = action_type.lower().replace("/", ".").replace("-", "_")
            if not action_type:
                action_type = "unknown.unknown"

        payload_keys = list(payload.keys()) if payload else []
        data_classes = _infer_data_classes(" ".join(payload_keys) + " " + action_type)

        key = (agent_id, action_type)
        if key in edge_counts:
            edge_counts[key]["count"] += 1
            edge_counts[key]["payload_keys"] = list(
                set(edge_counts[key]["payload_keys"]) | set(payload_keys)
            )
            if verdict and not edge_counts[key]["sample_verdict"]:
                edge_counts[key]["sample_verdict"] = verdict
        else:
            edge_counts[key] = {
                "agent_id": agent_id,
                "action_type": action_type,
                "payload_keys": payload_keys,
                "data_classes": data_classes,
                "count": 1,
                "sample_verdict": verdict,
            }

    edges = [
        ParsedLogEdge(**v) for v in edge_counts.values()
    ]
    logger.info("[bootstrap/parser] logs: %d unique edges extracted from %d lines",
                len(edges), len(lines))
    return edges


# ── Master parse function ──────────────────────────────────────────────────────

def parse_artifacts(
    *,
    openapi_spec: Optional[dict] = None,
    openapi_yaml: Optional[str] = None,
    agent_config: Optional[dict | list] = None,
    log_lines: Optional[list[str]] = None,
    tenant_id: Optional[str] = None,
) -> ParsedSystem:
    """Parse all provided artifacts into a unified ParsedSystem.

    Any combination of artifacts is accepted — the system degrades gracefully
    when only one or two artifact types are present.
    """
    system = ParsedSystem(tenant_id=tenant_id)

    # OpenAPI
    if openapi_yaml and not openapi_spec:
        try:
            try:
                import yaml
                openapi_spec = yaml.safe_load(openapi_yaml)
            except ImportError:
                # Fall back to JSON if yaml not available
                openapi_spec = json.loads(openapi_yaml)
        except Exception as exc:
            system.parse_warnings.append(f"openapi_parse_failed: {exc}")

    if openapi_spec and isinstance(openapi_spec, dict):
        try:
            system.endpoints = parse_openapi(openapi_spec, tenant_id)
            system.source_types.append("openapi")
        except Exception as exc:
            system.parse_warnings.append(f"openapi_extract_failed: {exc}")

    # Agent config
    if agent_config is not None:
        try:
            system.agents = parse_agent_config(agent_config)
            system.source_types.append("agent_config")
        except Exception as exc:
            system.parse_warnings.append(f"agent_config_failed: {exc}")

    # Logs
    if log_lines:
        try:
            system.log_edges = parse_log_sample(log_lines)
            system.source_types.append("logs")
        except Exception as exc:
            system.parse_warnings.append(f"log_parse_failed: {exc}")

    logger.info(
        "[bootstrap/parser] parsed system: sources=%s agents=%d endpoints=%d log_edges=%d warnings=%d",
        system.source_types, len(system.agents), len(system.endpoints),
        len(system.log_edges), len(system.parse_warnings),
    )
    return system
