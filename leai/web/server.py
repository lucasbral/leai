from __future__ import annotations

import json
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

from leai.ai import get_llm_client
from leai.ai.base import BaseLLMClient
from leai.config import LeaiConfig
from leai.docs import generate_mermaid_graph, write_schema_docs
from leai.enrich import enrich_code_object_annotation, enrich_table_annotation
from leai.models import ObjectAnnotation, SchemaMetadata, TableMeta
from leai.raw import load_raw_schemas, trace_raw_dependencies


def _sanitize_name(val: str) -> str:
    """Sanitizes names to prevent path traversal and invalid filesystem characters."""
    if not val:
        return ""
    return val.replace("/", "_").replace("\\", "_").replace("..", "").strip()


def _get_object_folder(obj_type: str) -> str:
    """Returns official annotations/docs folder name for a given database object type."""
    norm = obj_type.strip().upper()
    if norm == "TABLE":
        return "tables"
    if norm == "VIEW":
        return "views"
    if norm in ("MVIEW", "MATERIALIZED VIEW", "MATERIALIZED_VIEW"):
        return "mviews"
    if norm == "PACKAGE":
        return "packages"
    if norm == "PROCEDURE":
        return "procedures"
    if norm == "FUNCTION":
        return "functions"
    if norm == "TRIGGER":
        return "triggers"
    if norm == "SYNONYM":
        return "synonyms"
    if norm == "SEQUENCE":
        return "sequences"
    if norm in ("TYPE", "TYPE BODY"):
        return "types"
    if norm == "INDEX":
        return "indexes"
    return norm.lower().replace(" ", "_") + "s"


class LEAIStudioHandler(BaseHTTPRequestHandler):
    """Zero-dependency HTTP Handler for LEAI Web Studio REST APIs and Static Assets."""

    server: LEAIStudioServer  # Type annotation for custom server reference

    def log_message(self, format: str, *args: Any) -> None:
        """Silences standard HTTP server access logs to prevent CLI clutter."""
        pass

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._send_json({"success": False, "error": message}, status=status)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_DELETE(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/glossary":
            self._handle_api_delete_glossary(query=parsed_url.query)
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ("", "/"):
            self._serve_index_html()
            return

        if path == "/api/status":
            self._handle_api_status()
            return

        if path == "/api/catalog":
            self._handle_api_catalog()
            return

        if path == "/api/object":
            self._handle_api_get_object(parsed_url.query)
            return

        if path == "/api/config":
            self._handle_api_get_config()
            return

        if path == "/api/chat/models":
            self._handle_api_chat_models()
            return

        if path == "/api/glossary":
            self._handle_api_get_glossary()
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body) if body else {}
        except Exception as exc:
            self._send_error(f"Invalid JSON payload: {exc}")
            return

        if path in ("/api/chat/stream", "/api/chat"):
            self._handle_api_chat_stream(payload)
            return

        if path == "/api/annotations":
            self._handle_api_save_annotations(payload)
            return

        if path == "/api/enrich":
            self._handle_api_enrich(payload)
            return

        if path == "/api/compile":
            self._handle_api_compile(payload)
            return

        if path == "/api/config":
            self._handle_api_save_config(payload)
            return

        if path == "/api/glossary":
            if payload.get("action") == "delete":
                self._handle_api_delete_glossary(payload=payload)
            else:
                self._handle_api_save_glossary(payload)
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def _serve_index_html(self) -> None:
        static_file = Path(__file__).parent / "static" / "index.html"
        if not static_file.exists():
            self._send_error("Static index.html not found.", status=HTTPStatus.NOT_FOUND)
            return
        content = static_file.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_api_chat_models(self) -> None:
        cfg = self.server.config
        providers_data = {}
        if cfg.ai and cfg.ai.providers:
            for prov_name, prov_cfg in cfg.ai.providers.items():
                providers_data[prov_name] = {
                    "model": prov_cfg.model or "",
                    "has_key": bool(prov_cfg.api_key),
                }
        self._send_json(
            {
                "success": True,
                "default_provider": cfg.ai.default_provider if cfg.ai else "openai",
                "providers": providers_data,
                "active_model": self.server.client.model if self.server.client else "offline",
            }
        )

    def _handle_api_chat_stream(self, payload: dict) -> None:
        """Handles real-time streaming AI chat responses via Server-Sent Events (SSE)."""
        import time

        from leai.chat_session import ChatSession

        prompt = payload.get("prompt", "").strip()
        if not prompt:
            self._send_error("Prompt is required.")
            return

        provider_override = payload.get("provider")
        model_override = payload.get("model")
        history = payload.get("history", [])

        try:
            client = get_llm_client(
                self.server.config,
                provider_override=provider_override,
                model_override=model_override,
            )
        except Exception as exc:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            err_msg = json.dumps({"type": "error", "error": f"Failed to initialize AI client: {exc}"}, ensure_ascii=False)
            self.wfile.write(f"data: {err_msg}\n\n".encode("utf-8"))
            self.wfile.flush()
            return

        session = ChatSession(
            schemas=self.server.schemas,
            config=self.server.config,
            client=client,
        )

        # Restore message history if provided
        if history and isinstance(history, list):
            for h in history:
                role = h.get("role", "user")
                content = h.get("content", "")
                if content:
                    session.messages.append({"role": role, "content": content})

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        write_lock = threading.Lock()

        def _safe_write(data_bytes: bytes) -> bool:
            with write_lock:
                try:
                    self.wfile.write(data_bytes)
                    self.wfile.flush()
                    return True
                except Exception:
                    return False

        stop_ping = threading.Event()

        def _ping_worker() -> None:
            while not stop_ping.wait(2.5):
                if not _safe_write(b": ping\n\n"):
                    break

        ping_thread = threading.Thread(target=_ping_worker, daemon=True)
        ping_thread.start()

        def _send_sse_event(event_type: str, data: dict) -> bool:
            data["type"] = event_type
            line = f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
            return _safe_write(line)

        def _on_tool_start(t_name: str, t_args: dict, step_idx: int = 1) -> None:
            _send_sse_event("tool_start", {"name": t_name, "arguments": t_args, "step": step_idx})

        def _on_tool_end(t_name: str, t_out: str, summary: str = "", dur: float = 0.0) -> None:
            _send_sse_event("tool_end", {"name": t_name, "summary": summary or "OK", "duration": round(dur, 2)})

        def _on_token(token: str) -> None:
            _send_sse_event("token", {"text": token})

        # 1. Check for workflow command (e.g. /workflow impact VINCULOS)
        if prompt.startswith("/workflow"):
            from leai.workflows import get_workflow, list_workflows

            parts = prompt.split()
            if len(parts) < 2 or parts[1].lower() == "list":
                wfs = list_workflows()
                lines = ["### ⚙️ LEAI Autonomous Workflows\n\n| Workflow | Description |\n|---|---|"]
                for w in wfs:
                    lines.append(f"| `/workflow {w['name']}` | {w['description']} |")
                lines.append("\n*Usage: `/workflow impact <OBJECT_NAME>`*")
                _send_sse_event("done", {"reply": "\n".join(lines), "tokens": 0, "latency": 0.05, "detected": []})
                _safe_write(b"data: [DONE]\n\n")
                stop_ping.set()
                self.close_connection = True
                return

            wf_name = parts[1].lower()
            if wf_name in ("run", "exec") and len(parts) >= 4:
                wf_name = parts[2].lower()
                target_obj = parts[3].lstrip("@")
            elif len(parts) >= 3:
                target_obj = parts[2].lstrip("@")
            else:
                _send_sse_event("error", {"error": f"Usage: /workflow {wf_name} <target_object>"})
                _safe_write(b"data: [DONE]\n\n")
                stop_ping.set()
                self.close_connection = True
                return

            wf = get_workflow(name=wf_name, schemas=self.server.schemas, config=self.server.config, client=client)
            if not wf:
                from leai.workflows import WORKFLOW_REGISTRY

                available = ", ".join(sorted(set(WORKFLOW_REGISTRY.keys())))
                _send_sse_event("error", {"error": f"Unknown workflow '{wf_name}'. Available: {available}"})
                _safe_write(b"data: [DONE]\n\n")
                stop_ping.set()
                self.close_connection = True
                return

            def _on_wf_start(step: Any) -> None:
                _send_sse_event(
                    "tool_start",
                    {
                        "name": f"Workflow Step {step.step_number}: {step.name}",
                        "arguments": {"target": target_obj},
                        "step": step.step_number,
                    },
                )

            def _on_wf_end(step: Any) -> None:
                _send_sse_event(
                    "tool_end",
                    {
                        "name": f"Step {step.step_number}: {step.name}",
                        "summary": step.status.upper(),
                        "duration": round(step.duration_seconds, 2),
                    },
                )

            start_t = time.perf_counter()
            try:
                wf_res = wf.run(target_obj, on_step_start=_on_wf_start, on_step_end=_on_wf_end)
                latency = time.perf_counter() - start_t
                _send_sse_event(
                    "done",
                    {
                        "reply": wf_res.report_markdown or wf_res.summary,
                        "tokens": 0,
                        "latency": round(latency, 2),
                        "detected": [target_obj.upper()],
                    },
                )
                _safe_write(b"data: [DONE]\n\n")
            except Exception as exc:
                _send_sse_event("error", {"error": f"Workflow execution failed: {exc}"})
                _safe_write(b"data: [DONE]\n\n")
            finally:
                stop_ping.set()
                self.close_connection = True
            return

        # 2. Check for specialist subagent (@catalog_researcher, /agent plsql_analyst ...)
        from leai.ai.subagents import SUBAGENT_REGISTRY, execute_subagent

        sub_role = None
        sub_task = None
        if prompt.startswith("/agent"):
            parts = prompt.split()
            if len(parts) >= 3:
                cand = parts[1].lower().lstrip("@")
                if cand in SUBAGENT_REGISTRY:
                    sub_role = cand
                    sub_task = " ".join(parts[2:])
        else:
            first_token = prompt.split()[0] if prompt.split() else ""
            if first_token.startswith("@"):
                cand = first_token[1:].lower()
                if cand in SUBAGENT_REGISTRY:
                    sub_role = cand
                    sub_task = prompt[len(first_token) :].strip()

        if sub_role and sub_task:
            start_t = time.perf_counter()
            try:
                sub_reply = execute_subagent(
                    role=sub_role,
                    task=sub_task,
                    schemas=self.server.schemas,
                    config=self.server.config,
                    client=client,
                    on_token=_on_token,
                    on_tool_start=_on_tool_start,
                    on_tool_end=_on_tool_end,
                )
                latency = time.perf_counter() - start_t
                _send_sse_event(
                    "done",
                    {
                        "reply": sub_reply,
                        "tokens": 0,
                        "latency": round(latency, 2),
                        "detected": [],
                    },
                )
                _safe_write(b"data: [DONE]\n\n")
            except Exception as exc:
                _send_sse_event("error", {"error": f"Specialist '{sub_role}' failed: {exc}"})
                _safe_write(b"data: [DONE]\n\n")
            finally:
                stop_ping.set()
                self.close_connection = True
            return

        # 3. Standard autonomous multi-turn Agent / ChatSession
        start_t = time.perf_counter()
        try:
            reply, detected = session.send(
                prompt,
                on_tool_start=_on_tool_start,
                on_tool_end=_on_tool_end,
                on_token=_on_token,
            )
            latency = time.perf_counter() - start_t
            _send_sse_event(
                "done",
                {
                    "reply": reply,
                    "tokens": session.last_turn_tokens or 0,
                    "latency": round(latency, 2),
                    "detected": detected or [],
                },
            )
            _safe_write(b"data: [DONE]\n\n")
        except Exception as exc:
            _send_sse_event("error", {"error": str(exc)})
            _safe_write(b"data: [DONE]\n\n")
        finally:
            stop_ping.set()
            self.close_connection = True

    def _handle_api_status(self) -> None:
        cfg = self.server.config
        client = self.server.client
        git_data = {"is_repo": False}
        try:
            from leai.git_ops import get_git_status

            g_info = get_git_status(fetch=False)
            if g_info.is_repo:
                git_data = {
                    "is_repo": True,
                    "platform": g_info.platform_name,
                    "branch": g_info.branch,
                    "behind": g_info.behind,
                    "ahead": g_info.ahead,
                    "has_uncommitted": g_info.has_uncommitted,
                }
        except Exception:
            pass

        self._send_json(
            {
                "status": "online",
                "schemas_count": len(self.server.schemas),
                "provider": self.server.provider_name or "offline",
                "model": client.model if client else "offline",
                "annotations_path": str(cfg.annotationsPath),
                "docs_path": str(cfg.docPath),
                "git": git_data,
            }
        )

    def _handle_api_catalog(self) -> None:
        schemas_data = []
        cfg = self.server.config

        for s in self.server.schemas:
            s_name = s.schema_name or "DEFAULT"

            def _check_ann(cat: str, name: str) -> bool:
                p1 = cfg.annotationsPath / s_name / cat / f"{name}.yml"
                p2 = cfg.annotationsPath / cat / f"{name}.yml"
                p3 = cfg.annotationsPath / s_name / cat / f"{name}.yaml"
                p4 = cfg.annotationsPath / cat / f"{name}.yaml"
                return p1.exists() or p2.exists() or p3.exists() or p4.exists()

            tables = [{"name": t.name, "comment": t.comment or "", "is_annotated": _check_ann("tables", t.name)} for t in s.tables]
            views = [{"name": v.name, "comment": v.comment or "", "is_annotated": _check_ann("views", v.name)} for v in s.views]
            mviews = [
                {"name": mv.name, "comment": mv.comment or "", "is_annotated": _check_ann("mviews", mv.name)}
                for mv in getattr(s, "mviews", [])
            ]
            code_objects = [
                {
                    "name": co.name,
                    "type": co.object_type,
                    "comment": co.comment or "",
                    "is_annotated": _check_ann(_get_object_folder(co.object_type), co.name),
                }
                for co in s.code_objects
            ]
            triggers = [{"name": tr.name, "is_annotated": _check_ann("triggers", tr.name)} for tr in s.triggers]
            synonyms = [{"name": sy.name, "is_annotated": _check_ann("synonyms", sy.name)} for sy in s.synonyms]
            sequences = [{"name": sq.name, "is_annotated": _check_ann("sequences", sq.name)} for sq in s.sequences]

            schemas_data.append(
                {
                    "schema_name": s_name,
                    "tables": tables,
                    "views": views,
                    "mviews": mviews,
                    "code_objects": code_objects,
                    "triggers": triggers,
                    "synonyms": synonyms,
                    "sequences": sequences,
                }
            )

        self._send_json({"schemas": schemas_data})

    def _handle_api_get_object(self, query_str: str) -> None:
        params = urllib.parse.parse_qs(query_str)
        schema_name = _sanitize_name(params.get("schema", [""])[0].strip())
        obj_name = _sanitize_name(params.get("name", [""])[0].strip())
        depth_raw = params.get("depth", ["1"])[0].strip()
        try:
            depth = max(1, min(2, int(depth_raw)))
        except (ValueError, TypeError):
            depth = 1

        if not obj_name:
            self._send_error("Parameter 'name' is required.")
            return

        cfg = self.server.config
        matched_obj = None
        matched_schema = None
        resolved_type = "TABLE"

        for s in self.server.schemas:
            if schema_name and s.schema_name.upper() != schema_name.upper():
                continue

            # 1. Tables
            for t in s.tables:
                if t.name.upper() == obj_name.upper():
                    matched_obj = t
                    matched_schema = s
                    resolved_type = "TABLE"
                    break
            if matched_obj:
                break

            # 2. Views
            for v in s.views:
                if v.name.upper() == obj_name.upper():
                    matched_obj = v
                    matched_schema = s
                    resolved_type = "VIEW"
                    break
            if matched_obj:
                break

            # 3. Materialized Views
            for mv in getattr(s, "mviews", []):
                if mv.name.upper() == obj_name.upper():
                    matched_obj = mv
                    matched_schema = s
                    resolved_type = "MVIEW"
                    break
            if matched_obj:
                break

            # 4. Code Objects (Procedures, Functions, Packages, Types)
            for co in s.code_objects:
                if co.name.upper() == obj_name.upper():
                    matched_obj = co
                    matched_schema = s
                    resolved_type = co.object_type
                    break
            if matched_obj:
                break

            # 5. Triggers
            for trg in getattr(s, "triggers", []):
                if trg.name.upper() == obj_name.upper():
                    matched_obj = trg
                    matched_schema = s
                    resolved_type = "TRIGGER"
                    break
            if matched_obj:
                break

            # 6. Synonyms
            for syn in getattr(s, "synonyms", []):
                if syn.name.upper() == obj_name.upper():
                    matched_obj = syn
                    matched_schema = s
                    resolved_type = "SYNONYM"
                    break
            if matched_obj:
                break

            # 7. Sequences
            for seq in getattr(s, "sequences", []):
                if seq.name.upper() == obj_name.upper():
                    matched_obj = seq
                    matched_schema = s
                    resolved_type = "SEQUENCE"
                    break
            if matched_obj:
                break

        if not matched_obj or not matched_schema:
            self._send_error(f"Object '{obj_name}' not found in catalog.")
            return

        s_name = matched_schema.schema_name or "DEFAULT"
        ann_folder = _get_object_folder(resolved_type)

        # Load YAML annotations if existing
        ann_path = cfg.annotationsPath / s_name / ann_folder / f"{obj_name}.yml"
        if not ann_path.exists():
            ann_path = cfg.annotationsPath / ann_folder / f"{obj_name}.yml"

        ann_data = {}
        if ann_path.exists():
            try:
                ann_data = yaml.safe_load(ann_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass

        # Load compiled markdown doc if existing
        doc_path = cfg.docPath / s_name / ann_folder / f"{obj_name}.md"
        if not doc_path.exists():
            doc_path = cfg.docPath / ann_folder / f"{obj_name}.md"

        doc_content = ""
        if doc_path.exists():
            try:
                doc_content = doc_path.read_text(encoding="utf-8")
            except Exception:
                pass

        # Generate Mermaid Lineage code & structured lineage
        mermaid_code = ""
        lineage_data = {
            "depth": depth,
            "total": 0,
            "upstream_count": 0,
            "downstream_count": 0,
            "links": [],
            "mermaid_code": "",
        }
        try:
            trace_res = trace_raw_dependencies(
                self.server.schemas,
                obj_name,
                max_depth=depth,
                schema_name=s_name,
                expected_type=resolved_type,
            )
            raw_graph = generate_mermaid_graph(obj_name, trace_res.dependencies)
            mermaid_code = raw_graph.replace("```mermaid", "").replace("```", "").strip()

            target_upper = obj_name.strip().upper()
            links_list = []
            upstream_count = 0
            downstream_count = 0

            for dep in trace_res.dependencies:
                is_upstream = dep.source_name.upper() == target_upper
                if is_upstream:
                    upstream_count += 1
                    direction = "upstream"
                    rel_obj = dep.target_name
                    rel_type = dep.target_type
                else:
                    downstream_count += 1
                    direction = "downstream"
                    rel_obj = dep.source_name
                    rel_type = dep.source_type

                links_list.append(
                    {
                        "source_name": dep.source_name,
                        "source_type": dep.source_type,
                        "target_name": dep.target_name,
                        "target_type": dep.target_type,
                        "relation_type": dep.relation_type,
                        "depth": getattr(dep, "depth", 1),
                        "direction": direction,
                        "related_object": rel_obj,
                        "related_type": rel_type,
                        "details": getattr(dep, "details", "") or "",
                    }
                )

            lineage_data = {
                "depth": depth,
                "total": len(trace_res.dependencies),
                "upstream_count": upstream_count,
                "downstream_count": downstream_count,
                "links": links_list,
                "mermaid_code": mermaid_code,
            }
        except Exception:
            mermaid_code = ""

        # Build response object
        cols_data = []
        if hasattr(matched_obj, "columns") and matched_obj.columns:
            for col in matched_obj.columns:
                cols_data.append(
                    {
                        "name": col.name,
                        "data_type": col.data_type,
                        "nullable": col.nullable,
                        "comment": col.comment or "",
                    }
                )

        pks = getattr(matched_obj, "primary_keys", []) or []
        fks = []
        if hasattr(matched_obj, "foreign_keys") and matched_obj.foreign_keys:
            for fk in matched_obj.foreign_keys:
                fks.append(
                    {
                        "constraint_name": getattr(fk, "name", "") or getattr(fk, "constraint_name", ""),
                        "column": getattr(fk, "column", ""),
                        "referenced_table": getattr(fk, "referenced_table", ""),
                        "referenced_column": getattr(fk, "referenced_column", ""),
                    }
                )

        type_meta = {}
        if resolved_type == "TRIGGER":
            type_meta = {
                "table_name": getattr(matched_obj, "table_name", None),
                "trigger_type": getattr(matched_obj, "trigger_type", None),
                "triggering_event": getattr(matched_obj, "triggering_event", None),
                "status": getattr(matched_obj, "status", None),
            }
        elif resolved_type == "SYNONYM":
            type_meta = {
                "table_owner": getattr(matched_obj, "table_owner", None),
                "table_name": getattr(matched_obj, "table_name", None),
                "db_link": getattr(matched_obj, "db_link", None),
            }
        elif resolved_type == "SEQUENCE":
            type_meta = {
                "min_value": getattr(matched_obj, "min_value", None),
                "max_value": getattr(matched_obj, "max_value", None),
                "increment_by": getattr(matched_obj, "increment_by", None),
                "last_number": getattr(matched_obj, "last_number", None),
            }

        self._send_json(
            {
                "schema": s_name,
                "object_name": obj_name,
                "object_type": resolved_type,
                "comment": getattr(matched_obj, "comment", "") or "",
                "columns": cols_data,
                "primary_keys": pks,
                "foreign_keys": fks,
                "type_metadata": type_meta,
                "annotations": ann_data,
                "markdown_doc": doc_content,
                "lineage_mermaid": mermaid_code,
                "lineage": lineage_data,
            }
        )

    def _handle_api_save_annotations(self, payload: dict[str, Any]) -> None:
        schema_name = _sanitize_name(payload.get("schema", "").strip())
        obj_type = payload.get("object_type", "TABLE").strip().upper()
        obj_name = _sanitize_name(payload.get("object_name", "").strip().upper())

        if not obj_name:
            self._send_error("Parameter 'object_name' is required.")
            return

        cfg = self.server.config
        ann_folder = _get_object_folder(obj_type)
        multi_schema = len(self.server.schemas) > 1
        if multi_schema and schema_name:
            target_dir = cfg.annotationsPath / schema_name / ann_folder
        else:
            target_dir = cfg.annotationsPath / ann_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{obj_name}.yml"

        cols_payload = payload.get("columns", {})
        columns_dict: dict[str, str] = {}
        for col_k, col_v in cols_payload.items():
            if isinstance(col_v, dict):
                columns_dict[col_k] = str(col_v.get("description", ""))
            else:
                columns_dict[col_k] = str(col_v or "")

        ann_content: dict[str, Any] = {
            "description": payload.get("business_description") or payload.get("description", ""),
            "tags": payload.get("tags", []),
            "business_rules": payload.get("business_rules", []),
            "use_cases": payload.get("use_cases", []),
            "warnings": payload.get("warnings", []),
            "related_objects": payload.get("related_objects", []),
            "columns": columns_dict,
        }

        # Write YAML
        with open(target_file, "w", encoding="utf-8") as f:
            yaml.dump(ann_content, f, allow_unicode=True, sort_keys=False)

        # Recompile documentation for this object
        try:
            for s in self.server.schemas:
                if schema_name and s.schema_name.upper() != schema_name.upper():
                    continue
                write_schema_docs(
                    schema=s,
                    doc_path=cfg.docPath,
                    annotations_path=cfg.annotationsPath,
                    object_types=cfg.object_types,
                    multi_schema=multi_schema,
                    all_schemas=self.server.schemas,
                    target_object=obj_name,
                )
        except Exception as exc:
            self._send_error(f"Annotation saved, but failed to recompile Markdown: {exc}")
            return

        self._send_json(
            {
                "success": True,
                "saved_file": str(target_file),
                "object_name": obj_name,
            }
        )

    def _handle_api_enrich(self, payload: dict[str, Any]) -> None:
        schema_name = payload.get("schema", "").strip()
        obj_type = payload.get("object_type", "TABLE").strip().upper()
        obj_name = payload.get("object_name", "").strip().upper()

        client = self.server.client
        if not client:
            self._send_error("AI client is offline. Configure an API key to enable AI auto-enrichment.")
            return

        matched_obj = None
        for s in self.server.schemas:
            if schema_name and s.schema_name.upper() != schema_name.upper():
                continue
            for t in s.tables:
                if t.name.upper() == obj_name:
                    matched_obj = t
                    break
            if matched_obj:
                break
            for co in s.code_objects:
                if co.name.upper() == obj_name:
                    matched_obj = co
                    break
            if matched_obj:
                break

        if not matched_obj:
            self._send_error(f"Object '{obj_name}' not found.")
            return

        try:
            ann = ObjectAnnotation(
                name=obj_name,
                object_type=obj_type,
                schema_name=schema_name,
            )
            if isinstance(matched_obj, TableMeta):
                enriched = enrich_table_annotation(matched_obj, ann, client, overwrite=True)
            else:
                enriched = enrich_code_object_annotation(matched_obj, ann, client, overwrite=True)

            self._send_json(
                {
                    "success": True,
                    "enrichment": {
                        "business_description": enriched.description,
                        "business_rules": enriched.business_rules,
                        "use_cases": enriched.use_cases,
                        "warnings": enriched.warnings,
                        "related_objects": enriched.related_objects,
                        "tags": enriched.tags,
                        "columns": enriched.columns,
                    },
                }
            )
        except Exception as exc:
            self._send_error(f"AI enrichment failed: {exc}")

    def _handle_api_compile(self, payload: dict[str, Any]) -> None:
        try:
            for s in self.server.schemas:
                write_schema_docs(
                    schema=s,
                    doc_path=self.server.config.docPath,
                    annotations_path=self.server.config.annotationsPath,
                    multi_schema=len(self.server.schemas) > 1,
                    all_schemas=self.server.schemas,
                )
            self._send_json({"success": True, "message": "All documentation compiled successfully."})
        except Exception as exc:
            self._send_error(f"Compilation failed: {exc}")

    def _handle_api_get_config(self) -> None:
        try:
            config_path = getattr(self.server, "config_path", Path("leai.yml"))
            raw_yaml: dict[str, Any] = {}
            if config_path.exists():
                try:
                    raw_yaml = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    raw_yaml = {}

            cfg = self.server.config

            # DSN
            dsn_val = raw_yaml.get("dsn") if "dsn" in raw_yaml else (cfg.dsn or "")

            # Schemas
            raw_schemas = raw_yaml.get("schemas") or raw_yaml.get("schema")
            if raw_schemas:
                schemas_list = [raw_schemas] if isinstance(raw_schemas, str) else list(raw_schemas)
            else:
                schemas_list = cfg.schemas if cfg.schemas else [s.schema_name for s in self.server.schemas]

            # Include / Exclude
            include_list = raw_yaml.get("include", cfg.include or [])
            exclude_list = raw_yaml.get("exclude", cfg.exclude or [])

            # Object types
            obj_types = raw_yaml.get("object_types", cfg.object_types or [])

            # Paths (preserve relative paths if written in leai.yml)
            raw_path_str = str(raw_yaml.get("rawPath", cfg.rawPath))
            ann_path_str = str(raw_yaml.get("annotationsPath", cfg.annotationsPath))
            doc_path_str = str(raw_yaml.get("docPath", cfg.docPath))

            # AI
            raw_ai = raw_yaml.get("ai", {})
            default_prov = raw_ai.get("default_provider") or (cfg.ai.default_provider if cfg.ai else "openai")
            temp = raw_ai.get("temperature") if "temperature" in raw_ai else (cfg.ai.temperature if cfg.ai else 0.2)

            raw_providers = raw_ai.get("providers", {}) if isinstance(raw_ai, dict) else {}
            providers_data: dict[str, Any] = {}

            all_prov_names = set(raw_providers.keys())
            if cfg.ai and cfg.ai.providers:
                all_prov_names.update(cfg.ai.providers.keys())

            for p_name in all_prov_names:
                p_raw = raw_providers.get(p_name, {}) if isinstance(raw_providers, dict) else {}
                p_cfg = cfg.ai.providers.get(p_name) if cfg.ai else None

                m = p_raw.get("model") or (getattr(p_cfg, "model", "") if p_cfg else "") or ""
                b = p_raw.get("base_url") or (getattr(p_cfg, "base_url", "") if p_cfg else "") or ""
                k = bool(p_raw.get("api_key") or (getattr(p_cfg, "api_key", None) if p_cfg else None))

                providers_data[str(p_name)] = {
                    "model": m,
                    "base_url": b,
                    "has_api_key": k,
                }

            self._send_json(
                {
                    "dsn": dsn_val,
                    "schemas": schemas_list,
                    "include": include_list,
                    "exclude": exclude_list,
                    "object_types": obj_types,
                    "rawPath": raw_path_str,
                    "annotationsPath": ann_path_str,
                    "docPath": doc_path_str,
                    "ai": {
                        "default_provider": default_prov,
                        "temperature": temp,
                        "providers": providers_data,
                    },
                }
            )
        except Exception as exc:
            self._send_error(f"Error fetching configuration: {exc}")

    def _handle_api_save_config(self, payload: dict[str, Any]) -> None:
        cfg = self.server.config
        config_path = getattr(self.server, "config_path", Path("leai.yml"))
        if not config_path.exists():
            alt_path = cfg.docPath.parent / "leai.yml"
            if alt_path.exists():
                config_path = alt_path

        existing_yaml: dict[str, Any] = {}
        if config_path.exists():
            try:
                existing_yaml = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except Exception:
                existing_yaml = {}

        if "dsn" in payload:
            existing_yaml["dsn"] = payload["dsn"]
            cfg.dsn = payload["dsn"]

        if "schemas" in payload:
            raw_schemas = payload["schemas"]
            schemas_list = (
                [s.strip().upper() for s in raw_schemas if s.strip()]
                if isinstance(raw_schemas, list)
                else [s.strip().upper() for s in str(raw_schemas).split(",") if s.strip()]
            )
            existing_yaml["schemas"] = schemas_list
            cfg.schemas = schemas_list

        if "include" in payload:
            raw_inc = payload["include"]
            inc_list = (
                [i.strip().upper() for i in raw_inc if i.strip()]
                if isinstance(raw_inc, list)
                else [i.strip().upper() for i in str(raw_inc).split(",") if i.strip()]
            )
            existing_yaml["include"] = inc_list
            cfg.include = inc_list

        if "exclude" in payload:
            raw_exc = payload["exclude"]
            exc_list = (
                [e.strip().upper() for e in raw_exc if e.strip()]
                if isinstance(raw_exc, list)
                else [e.strip().upper() for e in str(raw_exc).split(",") if e.strip()]
            )
            existing_yaml["exclude"] = exc_list
            cfg.exclude = exc_list

        if "object_types" in payload and isinstance(payload["object_types"], list):
            existing_yaml["object_types"] = payload["object_types"]
            cfg.object_types = payload["object_types"]

        if "rawPath" in payload and payload["rawPath"]:
            existing_yaml["rawPath"] = str(payload["rawPath"])
            cfg.rawPath = Path(payload["rawPath"])

        if "annotationsPath" in payload and payload["annotationsPath"]:
            existing_yaml["annotationsPath"] = str(payload["annotationsPath"])
            cfg.annotationsPath = Path(payload["annotationsPath"])

        if "docPath" in payload and payload["docPath"]:
            existing_yaml["docPath"] = str(payload["docPath"])
            cfg.docPath = Path(payload["docPath"])

        ai_payload = payload.get("ai", {})
        if ai_payload:
            existing_ai = existing_yaml.setdefault("ai", {})
            if "default_provider" in ai_payload and ai_payload["default_provider"]:
                existing_ai["default_provider"] = ai_payload["default_provider"]
                cfg.ai.default_provider = ai_payload["default_provider"]
            if "temperature" in ai_payload:
                try:
                    temp_val = float(ai_payload["temperature"])
                    existing_ai["temperature"] = temp_val
                    cfg.ai.temperature = temp_val
                except Exception:
                    pass

            providers_payload = ai_payload.get("providers", {})
            if providers_payload and isinstance(providers_payload, dict):
                existing_providers = existing_ai.setdefault("providers", {})
                for prov_name, prov_data in providers_payload.items():
                    p_entry = existing_providers.setdefault(prov_name, {})
                    if "model" in prov_data and prov_data["model"]:
                        p_entry["model"] = prov_data["model"]
                    if "base_url" in prov_data:
                        p_entry["base_url"] = prov_data["base_url"]
                    if "api_key" in prov_data and prov_data["api_key"]:
                        p_entry["api_key"] = prov_data["api_key"]

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(existing_yaml, f, allow_unicode=True, sort_keys=False)
        except Exception as exc:
            self._send_error(f"Failed to write leai.yml: {exc}")
            return

        self._send_json(
            {
                "success": True,
                "message": "Configuration saved to leai.yml successfully!",
                "saved_file": str(config_path.resolve()),
            }
        )

    def _handle_api_get_glossary(self) -> None:
        """Retrieves global business glossary terms and compiled GLOSSARY.md."""
        from leai.docs import write_glossary_doc
        from leai.glossary import load_glossary

        cfg = self.server.config
        try:
            glossary = load_glossary(cfg.annotationsPath)
            compiled_md = ""
            glossary_file = cfg.docPath / "GLOSSARY.md"
            if not glossary.terms:
                if glossary_file.exists():
                    try:
                        glossary_file.unlink()
                    except Exception:
                        pass
                compiled_md = ""
            else:
                if not glossary_file.exists():
                    write_glossary_doc(cfg.annotationsPath, cfg.docPath)
                if glossary_file.exists():
                    compiled_md = glossary_file.read_text(encoding="utf-8")

            self._send_json(
                {
                    "success": True,
                    "terms": [term.model_dump() for term in glossary.terms],
                    "compiled_markdown": compiled_md,
                }
            )
        except Exception as exc:
            self._send_error(f"Failed to load glossary: {exc}")

    def _handle_api_save_glossary(self, payload: dict[str, Any]) -> None:
        """Adds or updates a global business glossary term and canonical SQL filter."""
        from leai.docs import write_glossary_doc
        from leai.glossary import add_or_update_term
        from leai.models import GlossaryTerm

        term_name = payload.get("term", "").strip()
        definition = payload.get("definition", "").strip()
        if not term_name or not definition:
            self._send_error("Fields 'term' and 'definition' are required.")
            return

        cfg = self.server.config
        try:
            term_obj = GlossaryTerm(
                term=term_name,
                definition=definition,
                primary_table=payload.get("primary_table"),
                canonical_filter=payload.get("canonical_filter"),
                related_tables=payload.get("related_tables", []),
                tags=payload.get("tags", []),
                examples=payload.get("examples", []),
            )
            add_or_update_term(cfg.annotationsPath, term_obj)
            write_glossary_doc(cfg.annotationsPath, cfg.docPath)
            self._send_json({"success": True, "term": term_obj.model_dump()})
        except Exception as exc:
            self._send_error(f"Failed to save glossary term: {exc}")

    def _handle_api_delete_glossary(self, query: str = "", payload: dict[str, Any] | None = None) -> None:
        """Deletes a business glossary term by name and updates compiled GLOSSARY.md."""
        from leai.docs import write_glossary_doc
        from leai.glossary import delete_term

        term_name = ""
        if payload and "term" in payload:
            term_name = str(payload["term"]).strip()
        elif query:
            qs = urllib.parse.parse_qs(query)
            term_name = qs.get("term", [""])[0].strip()

        if not term_name:
            self._send_error("Query parameter or body field 'term' is required for deletion.")
            return

        cfg = self.server.config
        try:
            deleted = delete_term(cfg.annotationsPath, term_name)
            if deleted:
                write_glossary_doc(cfg.annotationsPath, cfg.docPath)
                self._send_json({"success": True, "deleted": term_name})
            else:
                self._send_error(f"Term '{term_name}' not found.", status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(f"Failed to delete glossary term: {exc}")


class LEAIStudioServer(ThreadingHTTPServer):
    """Threaded HTTP Server for LEAI Web Documentation & Annotation Studio."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient | None = None,
        provider_name: str | None = None,
        config_path: Path | None = None,
    ):
        super().__init__(server_address, LEAIStudioHandler)
        self.schemas = schemas
        self.config = config
        self.client = client
        self.provider_name = provider_name
        self.config_path = config_path or Path("leai.yml")


def start_server(
    config: LeaiConfig,
    schemas: list[SchemaMetadata] | None = None,
    client: BaseLLMClient | None = None,
    provider_name: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
    in_background: bool = False,
    config_path: Path | None = None,
    initial_path: str = "/",
) -> tuple[LEAIStudioServer, str]:
    """Starts the LEAI Web Studio server, optionally in background thread."""
    if schemas is None:
        schemas = load_raw_schemas(config.rawPath)

    if client is None:
        try:
            client = get_llm_client(config, provider_override=provider_name)
        except Exception:
            client = None

    server = LEAIStudioServer(
        server_address=(host, port),
        schemas=schemas,
        config=config,
        client=client,
        provider_name=provider_name or (config.ai.default_provider if config.ai else None),
        config_path=config_path,
    )

    url = f"http://{host}:{port}"
    target_url = f"{url}{initial_path}" if initial_path and initial_path != "/" else url

    if in_background:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    else:
        if open_browser:
            threading.Timer(0.8, lambda: webbrowser.open(target_url)).start()
        try:
            server.serve_forever()
        except (KeyboardInterrupt, SystemExit):
            server.shutdown()

    if open_browser and in_background:
        threading.Timer(0.5, lambda: webbrowser.open(target_url)).start()

    return server, url
