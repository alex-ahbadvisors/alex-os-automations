#!/usr/bin/env python3
"""
n8n Workflow Pre-Import Validator

Reads an n8n workflow JSON export and checks it against known failure patterns
documented in n8n-failure-patterns.md. Run before importing into n8n to catch
issues that would otherwise require multiple debug cycles.

Usage:
    python3 validate-n8n.py <workflow.json>
    python3 validate-n8n.py ../n8n-workflows/8-daily-brief.json

Output: Pass/fail checklist with specific node names and fix suggestions.
"""

import json
import sys
import os
import re
from collections import defaultdict


def load_workflow(path):
    with open(path, 'r') as f:
        data = json.load(f)
    # Handle both full export (with "nodes" at top) and wrapped (nodes inside workflow object)
    if "nodes" in data:
        return data
    if "workflow" in data and "nodes" in data["workflow"]:
        return data["workflow"]
    # n8n export format sometimes nests under first key
    for key in data:
        if isinstance(data[key], dict) and "nodes" in data[key]:
            return data[key]
    return data


# n8n langchain agent nodes: Chat Model, Tool, Output Parser, and Memory sub-nodes
# wire into Agent nodes as multiple inputs by design. Not a convergence bug.
AGENT_NODE_TYPES = {
    "@n8n/n8n-nodes-langchain.agent",
    "@n8n/n8n-nodes-langchain.chainLlm",
    "@n8n/n8n-nodes-langchain.chainSummarization",
    "@n8n/n8n-nodes-langchain.chainRetrievalQa",
}

AGENT_SUB_NODE_TYPES = {
    "@n8n/n8n-nodes-langchain.lmChatOpenAi",
    "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
    "@n8n/n8n-nodes-langchain.outputParserStructured",
    "@n8n/n8n-nodes-langchain.outputParserAutofixing",
    "@n8n/n8n-nodes-langchain.toolWorkflow",
    "@n8n/n8n-nodes-langchain.toolCode",
    "@n8n/n8n-nodes-langchain.memoryBufferWindow",
}


def is_agent_wiring(target_node, source_nodes, nodes):
    """Return True if this multi-input is a langchain agent pattern (not a real convergence issue)."""
    target = get_node_by_name(nodes, target_node)
    if not target:
        return False
    target_type = target.get("type", "")
    if target_type in AGENT_NODE_TYPES:
        return True
    # Also skip if all sources are agent sub-node types feeding the same parent
    source_types = set()
    for s in source_nodes:
        sn = get_node_by_name(nodes, s)
        if sn:
            source_types.add(sn.get("type", ""))
    if source_types.issubset(AGENT_SUB_NODE_TYPES):
        return True
    return False


def get_connections(workflow):
    """Parse connections into a map: source_node -> [(target_node, target_input_index)]"""
    conns = workflow.get("connections", {})
    forward = defaultdict(list)  # source -> [target]
    reverse = defaultdict(list)  # target -> [source]
    for source_name, outputs in conns.items():
        if isinstance(outputs, dict):
            # Format: {"main": [[{"node": "target", "type": "main", "index": 0}]]}
            for output_type, output_indices in outputs.items():
                for output_index_conns in output_indices:
                    if isinstance(output_index_conns, list):
                        for conn in output_index_conns:
                            target = conn.get("node", "")
                            target_index = conn.get("index", 0)
                            forward[source_name].append((target, target_index))
                            reverse[target].append((source_name, target_index))
    return forward, reverse


def get_node_by_name(nodes, name):
    for n in nodes:
        if n.get("name") == name:
            return n
    return None


def check_p001_missing_always_output_data(workflow, nodes, forward, reverse):
    """P001: Missing alwaysOutputData on branch nodes feeding convergence points."""
    issues = []
    # Find convergence points: nodes with 2+ distinct source nodes
    for target, sources in reverse.items():
        unique_sources = set(s[0] for s in sources)
        if len(unique_sources) >= 2:
            # Skip langchain agent wiring — multiple inputs by design
            if is_agent_wiring(target, unique_sources, nodes):
                continue
            # Trace upstream from each source — check all nodes in those branches
            for source_name, _ in sources:
                node = get_node_by_name(nodes, source_name)
                if node:
                    has_aod = (
                        node.get("alwaysOutputData", False) or
                        node.get("options", {}).get("alwaysOutputData", False) or
                        node.get("executeOnce", False)
                    )
                    if not has_aod:
                        issues.append({
                            "pattern": "P001",
                            "severity": "HIGH",
                            "node": source_name,
                            "message": f"Node '{source_name}' feeds convergence point '{target}' but lacks alwaysOutputData: true. If this branch produces no output, downstream $() references will crash.",
                            "fix": f"Add alwaysOutputData: true to node '{source_name}' options."
                        })
    return issues


def check_p002_clickup_create_default(workflow, nodes, forward, reverse):
    """P002: ClickUp node defaults to 'create' when update was likely intended."""
    issues = []
    for node in nodes:
        node_type = node.get("type", "")
        if "clickup" not in node_type.lower():
            continue
        params = node.get("parameters", {})
        operation = params.get("operation", "create")
        name_lower = node.get("name", "").lower()
        update_signals = ["update", "edit", "modify", "change", "set status", "mark"]
        if operation == "create" and any(s in name_lower for s in update_signals):
            issues.append({
                "pattern": "P002",
                "severity": "MEDIUM",
                "node": node.get("name", "unknown"),
                "message": f"Node '{node.get('name')}' name suggests an update, but operation is 'create'. ClickUp node defaults to create.",
                "fix": "Set operation to 'update' explicitly in node parameters."
            })
    return issues


def check_p003_parallel_convergence(workflow, nodes, forward, reverse):
    """P003: Multiple nodes wired into the same downstream node input."""
    issues = []
    # Group by (target, input_index)
    target_inputs = defaultdict(list)
    for target, sources in reverse.items():
        for source_name, input_index in sources:
            target_inputs[(target, input_index)].append(source_name)

    for (target, input_index), sources in target_inputs.items():
        if len(sources) >= 2:
            target_node = get_node_by_name(nodes, target)
            target_type = target_node.get("type", "") if target_node else ""
            # Merge nodes are designed for this — skip them
            if "merge" in target_type.lower():
                continue
            # Langchain agent nodes expect multiple inputs — skip them
            if is_agent_wiring(target, sources, nodes):
                continue
            issues.append({
                "pattern": "P003",
                "severity": "HIGH",
                "node": target,
                "message": f"Node '{target}' receives parallel input from {len(sources)} nodes on input {input_index}: {', '.join(sources)}. n8n fires once per arriving input, not after all arrive.",
                "fix": f"Wire sequentially, or add a Merge node (mode: 'Wait for All') before '{target}'."
            })
    return issues


def check_p004_paired_item_reference(workflow, nodes, forward, reverse):
    """P004: Using .item.json on nodes that could return empty (DataTables, filters)."""
    issues = []
    for node in nodes:
        if node.get("type", "") not in ("n8n-nodes-base.code", "n8n-nodes-base.function", "n8n-nodes-base.functionItem"):
            continue
        code = node.get("parameters", {}).get("jsCode", "") or node.get("parameters", {}).get("functionCode", "")
        # Find $('NodeName').item.json patterns
        item_refs = re.findall(r"\$\(['\"]([^'\"]+)['\"]\)\.item\.json", code)
        for ref_name in item_refs:
            ref_node = get_node_by_name(nodes, ref_name)
            if ref_node:
                ref_type = ref_node.get("type", "")
                risky_types = ["datatable", "filter", "if", "switch", "removeDuplicates"]
                if any(t in ref_type.lower() for t in risky_types):
                    issues.append({
                        "pattern": "P004",
                        "severity": "MEDIUM",
                        "node": node.get("name", "unknown"),
                        "message": f"Node '{node.get('name')}' uses $('{ ref_name}').item.json, but '{ref_name}' is a {ref_type} that could return empty results. This will crash on synthetic empty items.",
                        "fix": f"Replace .item.json with .first()?.json ?? {{}} or use .all() with index handling."
                    })
    return issues


def check_p006_missive_api(workflow, nodes, forward, reverse):
    """P006: Missive API field gotchas."""
    issues = []
    for node in nodes:
        node_type = node.get("type", "")
        params = node.get("parameters", {})

        # Check HTTP Request nodes targeting Missive
        if "httpRequest" in node_type.lower() or "http" in node_type.lower():
            url = str(params.get("url", ""))
            if "missiveapp" not in url.lower():
                continue

            # Check for POST to /posts without required fields
            method = params.get("method", "GET")
            if method == "POST" and "/posts" in url:
                body = json.dumps(params.get("body", params.get("bodyParametersJson", "")))
                has_notification = "notification" in body
                has_text = "text" in body or "markdown" in body
                if not (has_notification and has_text):
                    missing = []
                    if not has_notification:
                        missing.append("notification: {title, body}")
                    if not has_text:
                        missing.append("text or markdown content")
                    issues.append({
                        "pattern": "P006",
                        "severity": "MEDIUM",
                        "node": node.get("name", "unknown"),
                        "message": f"POST to Missive /posts missing: {', '.join(missing)}. Both notification AND text/markdown are required.",
                        "fix": "Add both notification: {{title, body}} and text/markdown to the request body."
                    })

        # Check Code nodes for .subject without latest_message_subject
        if node_type in ("n8n-nodes-base.code", "n8n-nodes-base.function"):
            code = params.get("jsCode", "") or params.get("functionCode", "")
            if ".subject" in code and "latest_message_subject" not in code and "missive" in node.get("name", "").lower():
                issues.append({
                    "pattern": "P006",
                    "severity": "MEDIUM",
                    "node": node.get("name", "unknown"),
                    "message": f"Node '{node.get('name')}' references .subject — Missive's subject field is always null. Use latest_message_subject instead.",
                    "fix": "Replace .subject with .latest_message_subject"
                })
    return issues


def check_p007_clickup_date_filter(workflow, nodes, forward, reverse):
    """P007: ClickUp date filter excludes tasks with no due date."""
    issues = []
    for node in nodes:
        node_type = node.get("type", "")
        params = node.get("parameters", {})
        params_str = json.dumps(params)

        if "clickup" in node_type.lower() and ("due_date_lt" in params_str or "due_date_gt" in params_str):
            issues.append({
                "pattern": "P007",
                "severity": "MEDIUM",
                "node": node.get("name", "unknown"),
                "message": f"Node '{node.get('name')}' uses a due_date filter. ClickUp excludes tasks with NO due date — they won't appear in results.",
                "fix": "Remove date filter from API call. Do date bucketing in a downstream Code node instead."
            })
    return issues


def check_p009_convergence_no_try_catch(workflow, nodes, forward, reverse):
    """P009: Missing try-catch on $() references in convergence Code nodes."""
    issues = []
    for target, sources in reverse.items():
        unique_sources = set(s[0] for s in sources)
        if len(unique_sources) < 2:
            continue
        node = get_node_by_name(nodes, target)
        if not node:
            continue
        if node.get("type", "") not in ("n8n-nodes-base.code", "n8n-nodes-base.function"):
            continue
        code = node.get("parameters", {}).get("jsCode", "") or node.get("parameters", {}).get("functionCode", "")
        dollar_refs = re.findall(r"\$\(['\"][^'\"]+['\"]\)", code)
        if dollar_refs and "try" not in code:
            issues.append({
                "pattern": "P009",
                "severity": "HIGH",
                "node": node.get("name", "unknown"),
                "message": f"Convergence Code node '{node.get('name')}' has {len(dollar_refs)} $() references but no try-catch wrappers. If any upstream branch fails, this node crashes.",
                "fix": "Wrap $() calls in try-catch: function safeFirst(name) { try { return $(name).first().json; } catch { return {}; } }"
            })
    return issues


def check_code_nodes_for_dollar_refs(workflow, nodes, forward, reverse):
    """General scan: report all $() references in Code nodes for awareness."""
    info = []
    for node in nodes:
        if node.get("type", "") not in ("n8n-nodes-base.code", "n8n-nodes-base.function"):
            continue
        code = node.get("parameters", {}).get("jsCode", "") or node.get("parameters", {}).get("functionCode", "")
        refs = re.findall(r"\$\(['\"]([^'\"]+)['\"]\)", code)
        if refs:
            # Verify referenced nodes exist
            for ref in refs:
                if not get_node_by_name(nodes, ref):
                    info.append({
                        "pattern": "GENERAL",
                        "severity": "HIGH",
                        "node": node.get("name", "unknown"),
                        "message": f"Node '{node.get('name')}' references $('{ ref}') but no node named '{ref}' exists in the workflow. Typo or missing node.",
                        "fix": f"Check node name spelling. Available nodes: {', '.join(n.get('name','') for n in nodes[:20])}"
                    })
    return info


def run_all_checks(workflow):
    nodes = workflow.get("nodes", [])
    forward, reverse = get_connections(workflow)

    all_issues = []
    all_issues += check_p001_missing_always_output_data(workflow, nodes, forward, reverse)
    all_issues += check_p002_clickup_create_default(workflow, nodes, forward, reverse)
    all_issues += check_p003_parallel_convergence(workflow, nodes, forward, reverse)
    all_issues += check_p004_paired_item_reference(workflow, nodes, forward, reverse)
    all_issues += check_p006_missive_api(workflow, nodes, forward, reverse)
    all_issues += check_p007_clickup_date_filter(workflow, nodes, forward, reverse)
    all_issues += check_p009_convergence_no_try_catch(workflow, nodes, forward, reverse)
    all_issues += check_code_nodes_for_dollar_refs(workflow, nodes, forward, reverse)

    return all_issues, nodes


def print_report(filepath, issues, nodes):
    workflow_name = os.path.basename(filepath)
    node_count = len(nodes)
    code_nodes = [n for n in nodes if n.get("type", "") in ("n8n-nodes-base.code", "n8n-nodes-base.function")]

    print(f"\n{'='*60}")
    print(f"  n8n Pre-Import Validation Report")
    print(f"  Workflow: {workflow_name}")
    print(f"  Nodes: {node_count} total, {len(code_nodes)} Code nodes")
    print(f"  Patterns checked: 9 (P001-P009 + general)")
    print(f"{'='*60}\n")

    if not issues:
        print("  PASS — No known failure patterns detected.\n")
        print("  This doesn't mean it's bug-free — just that the known")
        print("  patterns aren't present. Log any new issues found during")
        print("  import testing to n8n-failure-patterns.md.\n")
        return

    # Group by severity
    high = [i for i in issues if i["severity"] == "HIGH"]
    medium = [i for i in issues if i["severity"] == "MEDIUM"]

    if high:
        print(f"  HIGH SEVERITY ({len(high)} issues) — Fix before import\n")
        for i, issue in enumerate(high, 1):
            print(f"  {i}. [{issue['pattern']}] {issue['message']}")
            print(f"     Fix: {issue['fix']}\n")

    if medium:
        print(f"  MEDIUM SEVERITY ({len(medium)} issues) — Review before import\n")
        for i, issue in enumerate(medium, 1):
            print(f"  {i}. [{issue['pattern']}] {issue['message']}")
            print(f"     Fix: {issue['fix']}\n")

    print(f"  {'='*58}")
    print(f"  Total: {len(high)} high, {len(medium)} medium")
    print(f"  Fix high-severity issues before importing.")
    print(f"  After import: log results in import-log.md\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate-n8n.py <workflow.json>")
        print("       python3 validate-n8n.py ../n8n-workflows/8-daily-brief.json")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    workflow = load_workflow(filepath)
    issues, nodes = run_all_checks(workflow)
    print_report(filepath, issues, nodes)

    # Exit code: 1 if high-severity issues, 0 otherwise
    high = [i for i in issues if i["severity"] == "HIGH"]
    sys.exit(1 if high else 0)


if __name__ == "__main__":
    main()
