from __future__ import annotations

import re
from dataclasses import dataclass, field

from leai.ai.base import BaseLLMClient
from leai.config import LeaiConfig
from leai.models import SchemaMetadata


@dataclass
class PromptTokens:
    """Extracted tokens from user prompt."""

    objects: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    directives: list[str] = field(default_factory=list)


@dataclass
class ProcessedDirectives:
    """Result of inline directives parsing and deterministic precomputation."""

    clean_prompt: str
    raw_prompt: str
    detected_objects: list[str]
    detected_rules: list[str]
    detected_directives: list[str]
    precomputed_context: str = ""
    system_overlay: str = ""
    action_badges: list[str] = field(default_factory=list)


def parse_prompt_tokens(text: str) -> PromptTokens:
    """Parses @objects, #rules, and /directives anywhere within the prompt string."""
    # Matches @OBJECT or @SCHEMA.OBJECT
    raw_objs = re.findall(r"@([A-Za-z0-9_$.]+)", text)
    # Matches #RULE_NAME
    raw_rules = re.findall(r"#([A-Za-z0-9_$.]+)", text)
    # Matches /directive anywhere preceded by whitespace or beginning of string
    raw_dirs = re.findall(r"(?:^|\s)/([a-zA-Z0-9_\-]+)", text)

    # Normalize objects (uppercase, strip trailing dots/punctuation)
    clean_objs = []
    for o in raw_objs:
        clean = o.rstrip(".,;!?").upper()
        if clean and clean not in clean_objs:
            clean_objs.append(clean)

    # Normalize rules
    clean_rules = []
    for r in raw_rules:
        clean = r.rstrip(".,;!?")
        if clean and clean not in clean_rules:
            clean_rules.append(clean)

    # Normalize directives (lowercase)
    clean_dirs = []
    for d in raw_dirs:
        clean = d.rstrip(".,;!?").lower()
        if clean and clean not in clean_dirs:
            clean_dirs.append(clean)

    return PromptTokens(objects=clean_objs, rules=clean_rules, directives=clean_dirs)


def process_inline_directives(
    prompt: str,
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    client: BaseLLMClient | None = None,
) -> ProcessedDirectives:
    """Processes inline directives embedded in user prompt, executes deterministic tools,

    and generates context dossier + specialist system prompt overlay.
    """
    tokens = parse_prompt_tokens(prompt)
    clean_prompt = prompt

    # Clean prompt for RAG and LLM by stripping directives or keeping natural phrasing
    for d in tokens.directives:
        clean_prompt = re.sub(rf"(?:^|\s)/{re.escape(d)}\b", "", clean_prompt)
    clean_prompt = re.sub(r"\s+", " ", clean_prompt).strip()
    if not clean_prompt:
        clean_prompt = prompt

    precomputed_parts: list[str] = []
    overlay_parts: list[str] = []
    badges: list[str] = []

    # 1. Handle Lineage / Trace Directives (/trace, /lineage, /deps, /dependencies)
    trace_dirs = {"trace", "lineage", "deps", "dependencies"}
    active_trace_dirs = set(tokens.directives).intersection(trace_dirs)
    if active_trace_dirs:
        from leai.docs import _calculate_risk_level
        from leai.raw import trace_raw_dependencies

        target_objects = list(tokens.objects)
        # If no @object specified, attempt to infer from query words matching schema objects
        if not target_objects and schemas:
            for s in schemas:
                for obj in s.tables + s.views + s.code_objects:
                    if re.search(rf"\b{re.escape(obj.name)}\b", prompt, re.IGNORECASE):
                        if obj.name.upper() not in target_objects:
                            target_objects.append(obj.name.upper())

        if target_objects:
            for obj_name in target_objects:
                target_schema = None
                target_name = obj_name
                if "." in obj_name:
                    parts = obj_name.split(".", 1)
                    target_schema, target_name = parts[0].strip(), parts[1].strip()

                trace_res = trace_raw_dependencies(schemas, target_name, max_depth=1, schema_name=target_schema)
                total_conns = len(trace_res.dependencies)
                risk_level = _calculate_risk_level(total_conns)

                parents = [
                    d.target_name
                    for d in trace_res.dependencies
                    if d.target_name != target_name
                    and d.relation_type in ("FK_REFERENCES", "DEPENDS_ON", "READS/SELECTS", "EXECUTES/CALLS", "SYNONYM_FOR")
                ]
                children = [
                    d.source_name
                    for d in trace_res.dependencies
                    if d.source_name != target_name and d.relation_type in ("FK_REFERENCED_BY",)
                ]
                consumers = [
                    d.source_name
                    for d in trace_res.dependencies
                    if d.source_name != target_name
                    and d.relation_type in ("PLSQL_DEPENDENCY", "TRIGGER_ON", "REFERENCED_BY", "CALLS_SUBPROGRAM")
                ]

                trace_dossier = (
                    f"### [DETERMINISTIC LINEAGE TRACE FOR @{obj_name}]\n"
                    f"- **Focal Object:** {trace_res.focal_name or target_name} ({trace_res.focal_type})\n"
                    f"- **Change Risk Level:** {risk_level} ({total_conns} direct connections)\n"
                    f"- **Upstream Dependencies (Parents / Read Tables):** {', '.join(sorted(set(parents))) if parents else 'None'}\n"
                    f"- **Downstream Foreign Key References (Children):** {', '.join(sorted(set(children))) if children else 'None'}\n"
                    f"- **Active Consumers (Packages / Triggers / Views):** {', '.join(sorted(set(consumers))) if consumers else 'None'}\n"
                )
                if trace_res.dependencies:
                    trace_dossier += "- **Connections Breakdown:**\n"
                    for d in trace_res.dependencies[:20]:
                        trace_dossier += f"  • `{d.source_name}` ({d.source_type}) ➔ [{d.relation_type}] ➔ `{d.target_name}` ({d.target_type})"
                        if d.details:
                            trace_dossier += f" ({d.details})"
                        trace_dossier += "\n"

                precomputed_parts.append(trace_dossier)
                badges.append(f"⚡ [/trace] Linhagem e risco calculados para @{obj_name} (Risco: {risk_level})")

            overlay_parts.append(
                "### [DIRECTIVE OVERLAY: LINEAGE & TRACE]\n"
                "The user requested a full lineage and dependency analysis. In your conversational response:\n"
                "1. Provide a comprehensive explanation of how data flows in and out of the focal object(s).\n"
                "2. Generate a clear, valid Mermaid diagram (```mermaid\nflowchart TD\n...```) representing the dependency hierarchy.\n"
                "3. Highlight the Change Risk Level and explain which downstream objects could break upon schema changes.\n"
                "4. Deliver this entire analysis directly in the chat response (do not merely refer to external files)."
            )
        else:
            overlay_parts.append(
                "### [DIRECTIVE OVERLAY: LINEAGE & TRACE]\n"
                "The /trace directive is active. Use `trace_object_lineage` to inspect dependencies and generate a Mermaid diagram in your answer."
            )
            badges.append("⚡ [/trace] Modo de auditoria de linhagem ativado")

    # 2. Handle SQL Tuning Directives (/tune, /sql-tune, /explain, /optimize)
    tune_dirs = {"tune", "sql-tune", "explain", "optimize"}
    active_tune_dirs = set(tokens.directives).intersection(tune_dirs)
    if active_tune_dirs:
        from leai.ai.tools import explain_and_tune_sql

        # Extract SQL query from prompt if possible
        sql_match = re.search(r"(SELECT|INSERT|UPDATE|DELETE|WITH)\s+.+", prompt, re.IGNORECASE | re.DOTALL)
        if sql_match:
            sql_text = sql_match.group(0).strip()
            tune_res = explain_and_tune_sql(schemas, query=sql_text, client=client)
            anti_p = tune_res.get("anti_patterns_detected", [])
            fts = tune_res.get("full_table_scan_warnings", [])

            tune_dossier = (
                f"### [DETERMINISTIC SQL TUNING DIAGNOSTIC]\n"
                f"- **Anti-patterns Detected:** {len(anti_p)}\n"
            )
            for a in anti_p:
                tune_dossier += f"  • [{a.get('type')}] on `{a.get('target')}`: {a.get('impact')} -> Rec: {a.get('recommendation')}\n"
            if fts:
                tune_dossier += f"- **Full Table Scan Warnings:** {len(fts)}\n"
                for f in fts:
                    tune_dossier += f"  • {f.get('warning')}\n"

            precomputed_parts.append(tune_dossier)
            badges.append("⚡ [/tune] Diagnóstico de sargabilidade e índices executado")

        overlay_parts.append(
            "### [DIRECTIVE OVERLAY: SQL TUNING & PERFORMANCE]\n"
            "The user requested SQL performance optimization. In your response:\n"
            "1. Pinpoint all non-sargable expressions, FTS risks, and missing indexes.\n"
            "2. Provide an optimized, rewritten SQL query with clear explanatory comments.\n"
            "3. Suggest exact DDL index definitions (`CREATE INDEX ...`) if composite indexes are needed."
        )
        if not sql_match:
            badges.append("⚡ [/tune] Otimizador de SQL ativado")

    # 3. Handle Validation Directives (/validate, /check-sql, /lint)
    val_dirs = {"validate", "check-sql", "lint"}
    active_val_dirs = set(tokens.directives).intersection(val_dirs)
    if active_val_dirs:
        from leai.ai.tools import validate_oracle_sql

        sql_match = re.search(r"(SELECT|INSERT|UPDATE|DELETE|WITH|MERGE)\s+.+", prompt, re.IGNORECASE | re.DOTALL)
        if sql_match:
            sql_text = sql_match.group(0).strip()
            val_res = validate_oracle_sql(schemas, sql=sql_text)
            val_dossier = (
                f"### [DETERMINISTIC SQL VALIDATION]\n"
                f"- **Valid Oracle Dialect:** {val_res.get('valid')}\n"
                f"- **Issues Detected:** {len(val_res.get('dialect_issues', []))}\n"
                f"- **Summary:** {val_res.get('summary', '')}\n"
            )
            precomputed_parts.append(val_dossier)
            badges.append("⚡ [/validate] Validação de sintaxe e catálogo executada")

        overlay_parts.append(
            "### [DIRECTIVE OVERLAY: SQL VALIDATION]\n"
            "Validate Oracle SQL syntax, ensure columns and tables exist in catalog, and flag incompatible syntax (e.g. LIMIT vs FETCH FIRST, backticks, ILIKE)."
        )
        if not sql_match:
            badges.append("⚡ [/validate] Validador de SQL Oracle ativado")

    # 4. Handle Business Rules / Glossary Directives (/rule, /rules, /glossary, or #RULE tokens)
    rule_dirs = {"rule", "rules", "glossary"}
    active_rule_dirs = set(tokens.directives).intersection(rule_dirs)
    if active_rule_dirs or tokens.rules:
        from leai.glossary import load_glossary, search_glossary

        glossary = load_glossary(config.annotationsPath)
        matched_terms = []
        if tokens.rules:
            for r_tag in tokens.rules:
                matches = search_glossary(glossary, r_tag)
                for term, _score in matches:
                    if term not in matched_terms:
                        matched_terms.append(term)
        elif active_rule_dirs:
            # Search terms matching keywords in prompt
            words = [w for w in re.split(r"\W+", prompt) if len(w) > 3]
            for w in words:
                matches = search_glossary(glossary, w)
                for term, score in matches:
                    if score > 50 and term not in matched_terms:
                        matched_terms.append(term)

        if matched_terms:
            rule_dossier = "### [CANONICAL BUSINESS RULES & GLOSSARY]\n"
            for t_item in matched_terms[:5]:
                rule_dossier += (
                    f"- **{t_item.term}:** {t_item.definition}\n"
                    f"  • Primary Table: `{t_item.primary_table or 'N/A'}`\n"
                    f"  • Canonical Filter: `{t_item.canonical_filter or 'N/A'}`\n"
                )
            precomputed_parts.append(rule_dossier)
            badges.append(f"⚡ [/rule] Regras de negócio recuperadas ({len(matched_terms)} termos)")

        overlay_parts.append(
            "### [DIRECTIVE OVERLAY: BUSINESS RULES]\n"
            "Apply the official canonical filters and business definitions. Ensure generated queries strictly adhere to these organizational rules."
        )
        if not matched_terms:
            badges.append("⚡ [/rule] Consulta de regras de negócio ativada")

    # 5. Handle Specialist Persona Overlays
    # PL/SQL Specialist
    if any(d in tokens.directives for d in ("plsql", "analyst", "reverse")):
        from leai.ai.subagents import PLSQL_ANALYST_PROMPT

        overlay_parts.append(f"### [SPECIALIST PERSONA: PL/SQL ANALYST]\n{PLSQL_ANALYST_PROMPT}")
        badges.append("⚡ [/plsql] Especialista em Análise e Engenharia Reversa PL/SQL ativado")

    # Catalog Specialist
    if any(d in tokens.directives for d in ("catalog", "schema", "tables")):
        from leai.ai.subagents import CATALOG_RESEARCHER_PROMPT

        overlay_parts.append(f"### [SPECIALIST PERSONA: CATALOG RESEARCHER]\n{CATALOG_RESEARCHER_PROMPT}")
        badges.append("⚡ [/catalog] Especialista em Dicionário e Catálogo ativado")

    # Patch / CodeGen Specialist
    if any(d in tokens.directives for d in ("patch", "codegen", "refactor")):
        from leai.ai.subagents import PATCH_GENERATOR_PROMPT

        overlay_parts.append(f"### [SPECIALIST PERSONA: SAFE PATCH GENERATOR]\n{PATCH_GENERATOR_PROMPT}")
        badges.append("⚡ [/patch] Especialista em Geração Segura de Código PL/SQL ativado")

    # Documentation Specialist
    if any(d in tokens.directives for d in ("doc", "docs", "annotation")):
        from leai.ai.subagents import DOC_ANNOTATOR_PROMPT

        overlay_parts.append(f"### [SPECIALIST PERSONA: DOCUMENTATION ANNOTATOR]\n{DOC_ANNOTATOR_PROMPT}")
        badges.append("⚡ [/doc] Especialista em Documentação Semântica ativado")

    # Impact Specialist
    if any(d in tokens.directives for d in ("impact", "lineage_auditor")):
        from leai.ai.subagents import LINEAGE_AUDITOR_PROMPT

        overlay_parts.append(f"### [SPECIALIST PERSONA: IMPACT AUDITOR]\n{LINEAGE_AUDITOR_PROMPT}")
        badges.append("⚡ [/impact] Especialista em Avaliação de Impacto e Risco ativado")

    return ProcessedDirectives(
        clean_prompt=clean_prompt,
        raw_prompt=prompt,
        detected_objects=tokens.objects,
        detected_rules=tokens.rules,
        detected_directives=tokens.directives,
        precomputed_context="\n\n".join(precomputed_parts),
        system_overlay="\n\n".join(overlay_parts),
        action_badges=badges,
    )
