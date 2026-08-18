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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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

    def _handle_api_status(self) -> None:
        cfg = self.server.config
        client = self.server.client
        self._send_json({
            "status": "online",
            "schemas_count": len(self.server.schemas),
            "provider": self.server.provider_name or "offline",
            "model": client.model if client else "offline",
            "annotations_path": str(cfg.annotationsPath),
            "docs_path": str(cfg.docPath),
        })

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
            code_objects = [{"name": co.name, "type": co.object_type, "comment": co.comment or "", "is_annotated": _check_ann("packages" if co.object_type == "PACKAGE" else "procedures", co.name)} for co in s.code_objects]
            triggers = [{"name": tr.name, "is_annotated": _check_ann("triggers", tr.name)} for tr in s.triggers]
            synonyms = [{"name": sy.name, "is_annotated": _check_ann("synonyms", sy.name)} for sy in s.synonyms]
            sequences = [{"name": sq.name, "is_annotated": _check_ann("sequences", sq.name)} for sq in s.sequences]

            schemas_data.append({
                "schema_name": s_name,
                "tables": tables,
                "views": views,
                "code_objects": code_objects,
                "triggers": triggers,
                "synonyms": synonyms,
                "sequences": sequences,
            })

        self._send_json({"schemas": schemas_data})

    def _handle_api_get_object(self, query_str: str) -> None:
        params = urllib.parse.parse_qs(query_str)
        schema_name = params.get("schema", [""])[0].strip()
        obj_type = params.get("type", [""])[0].strip().upper()
        obj_name = params.get("name", [""])[0].strip()

        if not obj_name:
            self._send_error("Parameter 'name' is required.")
            return

        cfg = self.server.config
        matched_obj = None
        matched_schema = None

        for s in self.server.schemas:
            if schema_name and s.schema_name.upper() != schema_name.upper():
                continue
            for t in s.tables:
                if t.name.upper() == obj_name.upper():
                    matched_obj = t
                    matched_schema = s
                    obj_type = "TABLE"
                    break
            if matched_obj:
                break
            for v in s.views:
                if v.name.upper() == obj_name.upper():
                    matched_obj = v
                    matched_schema = s
                    obj_type = "VIEW"
                    break
            if matched_obj:
                break
            for co in s.code_objects:
                if co.name.upper() == obj_name.upper():
                    matched_obj = co
                    matched_schema = s
                    obj_type = co.object_type
                    break
            if matched_obj:
                break

        if not matched_obj:
            self._send_error(f"Object '{obj_name}' not found in catalog.")
            return

        s_name = matched_schema.schema_name or "DEFAULT"

        # Load YAML annotations if existing
        ann_folder = "tables" if obj_type == "TABLE" else ("views" if obj_type == "VIEW" else ("packages" if obj_type == "PACKAGE" else "procedures"))
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
        doc_folder = ann_folder
        doc_path = cfg.docPath / s_name / doc_folder / f"{obj_name}.md"
        if not doc_path.exists():
            doc_path = cfg.docPath / doc_folder / f"{obj_name}.md"

        doc_content = ""
        if doc_path.exists():
            try:
                doc_content = doc_path.read_text(encoding="utf-8")
            except Exception:
                pass

        # Generate Mermaid Lineage code
        trace_res = trace_raw_dependencies(self.server.schemas, obj_name, max_depth=1)
        raw_graph = generate_mermaid_graph(obj_name, trace_res.dependencies)
        mermaid_code = raw_graph.replace("```mermaid", "").replace("```", "").strip()

        # Build response object
        cols_data = []
        if hasattr(matched_obj, "columns"):
            for col in matched_obj.columns:
                cols_data.append({
                    "name": col.name,
                    "data_type": col.data_type,
                    "nullable": col.nullable,
                    "comment": col.comment or "",
                })

        pks = getattr(matched_obj, "primary_keys", []) or []
        fks = []
        if hasattr(matched_obj, "foreign_keys"):
            for fk in matched_obj.foreign_keys:
                fks.append({
                    "constraint_name": getattr(fk, "name", "") or getattr(fk, "constraint_name", ""),
                    "column": getattr(fk, "column", ""),
                    "referenced_table": getattr(fk, "referenced_table", ""),
                    "referenced_column": getattr(fk, "referenced_column", ""),
                })

        self._send_json({
            "schema": s_name,
            "object_name": obj_name,
            "object_type": obj_type,
            "comment": getattr(matched_obj, "comment", "") or "",
            "columns": cols_data,
            "primary_keys": pks,
            "foreign_keys": fks,
            "annotations": ann_data,
            "markdown_doc": doc_content,
            "lineage_mermaid": mermaid_code,
        })

    def _handle_api_save_annotations(self, payload: dict[str, Any]) -> None:
        schema_name = payload.get("schema", "").strip()
        obj_type = payload.get("object_type", "TABLE").strip().upper()
        obj_name = payload.get("object_name", "").strip().upper()

        if not obj_name:
            self._send_error("Parameter 'object_name' is required.")
            return

        cfg = self.server.config
        ann_folder = "tables" if obj_type == "TABLE" else ("views" if obj_type == "VIEW" else ("packages" if obj_type == "PACKAGE" else "procedures"))
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
                    multi_schema=multi_schema,
                    all_schemas=self.server.schemas,
                    target_object=obj_name,
                )
        except Exception as exc:
            self._send_error(f"Annotation saved, but failed to recompile Markdown: {exc}")
            return

        self._send_json({
            "success": True,
            "saved_file": str(target_file),
            "object_name": obj_name,
        })

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

            self._send_json({
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
            })
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
                p_cfg = (cfg.ai.providers.get(p_name) if cfg.ai else None)

                m = p_raw.get("model") or (getattr(p_cfg, "model", "") if p_cfg else "") or ""
                b = p_raw.get("base_url") or (getattr(p_cfg, "base_url", "") if p_cfg else "") or ""
                k = bool(p_raw.get("api_key") or (getattr(p_cfg, "api_key", None) if p_cfg else None))

                providers_data[str(p_name)] = {
                    "model": m,
                    "base_url": b,
                    "has_api_key": k,
                }

            self._send_json({
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
            })
        except Exception as exc:
            self._send_error(f"Erro ao obter configurações: {exc}")

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
            schemas_list = [s.strip().upper() for s in raw_schemas if s.strip()] if isinstance(raw_schemas, list) else [s.strip().upper() for s in str(raw_schemas).split(",") if s.strip()]
            existing_yaml["schemas"] = schemas_list
            cfg.schemas = schemas_list

        if "include" in payload:
            raw_inc = payload["include"]
            inc_list = [i.strip().upper() for i in raw_inc if i.strip()] if isinstance(raw_inc, list) else [i.strip().upper() for i in str(raw_inc).split(",") if i.strip()]
            existing_yaml["include"] = inc_list
            cfg.include = inc_list

        if "exclude" in payload:
            raw_exc = payload["exclude"]
            exc_list = [e.strip().upper() for e in raw_exc if e.strip()] if isinstance(raw_exc, list) else [e.strip().upper() for e in str(raw_exc).split(",") if e.strip()]
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

        self._send_json({
            "success": True,
            "message": "Configurações salvas no leai.yml com sucesso!",
            "saved_file": str(config_path.resolve()),
        })


class LEAIStudioServer(ThreadingHTTPServer):
    """Threaded HTTP Server for LEAI Web Documentation & Annotation Studio."""

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

    if in_background:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    else:
        if open_browser:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except (KeyboardInterrupt, SystemExit):
            server.shutdown()

    if open_browser and in_background:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    return server, url
