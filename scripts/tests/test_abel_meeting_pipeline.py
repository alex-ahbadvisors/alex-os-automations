#!/usr/bin/env python3
"""
test_abel_meeting_pipeline.py -- hermetic tests for the Abel meeting-pipeline
fixes (ClickUp 868kwvxfy, 2026-10-26).

Covers:
  A  Get Template (5-draft-follow-up-email): the SHIPPED expression, extracted
     from the workflow JSON and run under the system `node`, returns the task
     id for a bare URL, a URL with the workspace segment, a markdown link, a
     code-span link, and returns '' for null or a non-ClickUp string.
  B  Decider (5-draft-follow-up-email): the prompt, the output parser and
     If HITL? all treat hitl_needed as a boolean; no "yes"/"no" left.
  E  Client List (1-capture-transcript): the shipped Code node groups BD Pipeline
     rows by Category with Stage, drops rows with no Category, never emits
     descriptions, and falls back cleanly on an empty or failed fetch.
  C  validate-n8n.py P001/P003 branch topology: exclusive IF/Switch branches,
     separate triggers, an IF node feeding on one output, and a loop-back edge
     are not flagged; a real two-branch Merge still is.
  D  The three Abel workflows validate with zero high-severity findings.

No network, no live n8n. Run: python3 scripts/tests/test_abel_meeting_pipeline.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WF_DIR = os.path.join(REPO, "n8n-workflows")

spec = importlib.util.spec_from_file_location("validate_n8n", os.path.join(REPO, "scripts", "validate-n8n.py"))
validate_n8n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_n8n)


def load(name):
    with open(os.path.join(WF_DIR, name)) as f:
        return json.load(f)


def node(wf, name):
    return next(n for n in wf["nodes"] if n["name"] == name)


class GetTemplateExtract(unittest.TestCase):
    LINK_REF = "$('Draft Context').item.json.output.email_template_clickup_link"

    def run_expression(self, link):
        expr = node(load("5-draft-follow-up-email.json"), "Get Template")["parameters"]["id"]
        self.assertTrue(expr.startswith("={{") and expr.endswith("}}"), expr)
        body = expr[3:-2].strip()
        self.assertIn(self.LINK_REF, body)
        body = body.replace(self.LINK_REF, "LINK")
        js = f"const LINK = {json.dumps(link)};\nprocess.stdout.write(JSON.stringify({body}));"
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_link_formats(self):
        cases = [
            ("https://app.clickup.com/t/868kwth55", "868kwth55"),
            ("https://app.clickup.com/t/9011763462/868kwth55", "868kwth55"),
            ("[https://app.clickup.com/t/868kwth55](https://app.clickup.com/t/868kwth55)", "868kwth55"),
            ("`https://app.clickup.com/t/868fkypqb`", "868fkypqb"),
            ("https://app.clickup.com/t/868fkypqb?comment=1", "868fkypqb"),
            (None, ""),
            ("not a clickup link", ""),
        ]
        for link, want in cases:
            with self.subTest(link=link):
                self.assertEqual(self.run_expression(link), want)

    def test_old_split_was_broken(self):
        # Documents the bug: the old expression kept the workspace segment.
        self.assertEqual(
            "https://app.clickup.com/t/9011763462/868kwth55".split("/t/")[-1], "9011763462/868kwth55"
        )


class ClientListInjection(unittest.TestCase):
    CAT = "5a623c67-06b5-499a-b35b-a03ff52ed326"
    STAGE = "797e8072-df53-457f-aa22-1f9802da933d"
    CAT_OPTS = [{"id": "c-client", "label": "Client", "orderindex": 0},
                {"id": "c-prospect", "label": "Prospect", "orderindex": 1},
                {"id": "c-former", "label": "Former", "orderindex": 6}]
    STAGE_OPTS = [{"id": "s-ident", "name": "Identified", "orderindex": 0},
                  {"id": "s-won", "name": "Won", "orderindex": 3}]

    def task(self, name, cats=None, stage=None, closed=False):
        cf = [{"id": self.CAT, "type": "labels", "type_config": {"options": self.CAT_OPTS}}]
        if cats:
            cf[0]["value"] = cats
        sf = {"id": self.STAGE, "type": "drop_down", "type_config": {"options": self.STAGE_OPTS}}
        if stage is not None:
            sf["value"] = stage
        cf.append(sf)
        return {"json": {"name": name, "description": "CONFIDENTIAL fee terms", "custom_fields": cf,
                         "status": {"status": "closed" if closed else "open", "type": "closed" if closed else "open"}}}

    def run_node(self, items):
        code = node(load("1-capture-transcript.json"), "Client List")["parameters"]["jsCode"]
        js = (f"const ITEMS = {json.dumps(items)};\nconst $input = {{ all: () => ITEMS }};\n"
              "const $ = () => ({ first: () => ({ json: { markdown_description: 'TYPES' } }) });\n"
              f"const out = (function() {{\n{code}\n}})();\nprocess.stdout.write(JSON.stringify(out));")
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_groups_names_and_stages_only(self):
        out = self.run_node([
            self.task("Acme", ["c-client"], 3),
            self.task("Beta (Jane Doe)", ["c-prospect"], 0),
            self.task("Gamma", ["c-former"], None, closed=True),
            self.task("Schedule coffee with someone"),  # no Category: dropped
            {"json": {"error": "ClickUp 500"}},  # errored fetch item: skipped
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["pairedItem"], {"item": 0})
        self.assertEqual(out[0]["json"]["markdown_description"], "TYPES")
        block = out[0]["json"]["client_list"]
        self.assertEqual(block, "Client:\n- Acme — Won\n\nProspect:\n- Beta (Jane Doe) — Identified\n\nFormer:\n- Gamma — record closed")
        self.assertNotIn("CONFIDENTIAL", block)
        self.assertNotIn("Schedule", block)

    def test_empty_fetch_falls_back(self):
        out = self.run_node([{"json": {}}])
        self.assertIn("Client list unavailable", out[0]["json"]["client_list"])

    def test_wiring_and_prompt(self):
        wf = load("1-capture-transcript.json")
        c = wf["connections"]
        self.assertEqual(c["Meeting Types"]["main"][0][0]["node"], "BD Pipeline")
        self.assertEqual(c["BD Pipeline"]["main"][0][0]["node"], "Client List")
        self.assertEqual(c["Client List"]["main"][0][0]["node"], "Categorization Agent")
        bd = node(wf, "BD Pipeline")
        self.assertEqual(bd["parameters"]["list"], "901113925326")
        self.assertTrue(bd["parameters"]["returnAll"])
        self.assertTrue(bd["parameters"]["filters"]["includeClosed"])
        self.assertEqual(bd["onError"], "continueRegularOutput")
        text = node(wf, "Categorization Agent")["parameters"]["text"]
        self.assertIn("{{ $json.client_list }}", text)
        self.assertNotIn("From clients data table", text)


class DeciderBoolean(unittest.TestCase):
    def test_one_source_of_truth(self):
        wf = load("5-draft-follow-up-email.json")
        prompt = node(wf, "Decider")["parameters"]["options"]["systemMessage"]
        self.assertNotIn('"yes"', prompt)
        self.assertNotIn('"no"', prompt)
        self.assertIn('"hitl_needed": true|false', prompt)
        schema = json.loads(node(wf, "Structured Output Parser")["parameters"]["inputSchema"])
        self.assertEqual(schema["properties"]["hitl_needed"]["type"], "boolean")
        self.assertNotIn("'yes'", json.dumps(schema))
        cond = node(wf, "If HITL?")["parameters"]["conditions"]["conditions"][0]
        self.assertEqual(cond["operator"]["type"], "boolean")


def wf_of(nodes, edges):
    """nodes: {name: type}; edges: [(src, out_idx, tgt, in_idx)]"""
    conns = {}
    for s, o, t, i in edges:
        outs = conns.setdefault(s, {"main": []})["main"]
        while len(outs) <= o:
            outs.append([])
        outs[o].append({"node": t, "type": "main", "index": i})
    return {
        "nodes": [{"name": n, "type": f"n8n-nodes-base.{t}", "parameters": {}} for n, t in nodes.items()],
        "connections": conns,
    }


def high(wf, pattern):
    issues, _ = validate_n8n.run_all_checks(wf)
    return sorted(i["node"] for i in issues if i["pattern"] == pattern and i["severity"] == "HIGH")


class BranchTopology(unittest.TestCase):
    def test_if_branches_into_one_node_not_flagged(self):
        wf = wf_of(
            {"T": "manualTrigger", "If": "if", "A": "set", "B": "set", "Sink": "set"},
            [("T", 0, "If", 0), ("If", 0, "A", 0), ("If", 1, "B", 0), ("A", 0, "Sink", 0), ("B", 0, "Sink", 0)],
        )
        self.assertEqual(high(wf, "P001"), [])
        self.assertEqual(high(wf, "P003"), [])

    def test_separate_triggers_not_flagged(self):
        wf = wf_of(
            {"T1": "manualTrigger", "T2": "scheduleTrigger", "S": "set", "Sink": "set"},
            [("T1", 0, "Sink", 0), ("T2", 0, "S", 0), ("S", 0, "Sink", 0)],
        )
        self.assertEqual(high(wf, "P001"), [])
        self.assertEqual(high(wf, "P003"), [])

    def test_if_node_as_direct_source_not_flagged(self):
        # If.out1 -> Sink and If.out0 -> X -> Sink: exclusive. aod on If would fire out0.
        wf = wf_of(
            {"T": "manualTrigger", "If": "if", "X": "set", "Sink": "set"},
            [("T", 0, "If", 0), ("If", 0, "X", 0), ("If", 1, "Sink", 0), ("X", 0, "Sink", 0)],
        )
        self.assertEqual(high(wf, "P001"), [])
        self.assertEqual(high(wf, "P003"), [])

    def test_loop_back_not_flagged(self):
        wf = wf_of(
            {"T": "manualTrigger", "Get": "set", "If": "if", "Wait": "wait", "Done": "set"},
            [("T", 0, "Get", 0), ("Get", 0, "If", 0), ("If", 0, "Wait", 0), ("Wait", 0, "Get", 0), ("If", 1, "Done", 0)],
        )
        self.assertEqual(high(wf, "P001"), [])
        self.assertEqual(high(wf, "P003"), [])

    def test_real_parallel_merge_still_flagged(self):
        wf = wf_of(
            {"T": "manualTrigger", "A": "set", "B": "set", "M": "merge"},
            [("T", 0, "A", 0), ("T", 0, "B", 0), ("A", 0, "M", 0), ("B", 0, "M", 1)],
        )
        self.assertEqual(high(wf, "P001"), ["A", "B"])

    def test_real_parallel_fan_in_still_flagged(self):
        wf = wf_of(
            {"T": "manualTrigger", "A": "set", "B": "set", "Sink": "set"},
            [("T", 0, "A", 0), ("T", 0, "B", 0), ("A", 0, "Sink", 0), ("B", 0, "Sink", 0)],
        )
        self.assertEqual(high(wf, "P003"), ["Sink"])

    def test_if_branches_into_aggregate_still_flagged(self):
        # A batch split by an IF runs both branches in one execution; Aggregate
        # then runs once per branch. Seen live in 3-create-crm-insights.
        wf = wf_of(
            {"T": "manualTrigger", "If": "if", "A": "set", "B": "set", "Agg": "aggregate"},
            [("T", 0, "If", 0), ("If", 0, "A", 0), ("If", 1, "B", 0), ("A", 0, "Agg", 0), ("B", 0, "Agg", 0)],
        )
        self.assertEqual(high(wf, "P003"), ["Agg"])

    def test_upstream_source_exempt_downstream_still_flagged(self):
        # Merge(original, enriched): Orig dominates Enriched, so only Enriched needs aod.
        wf = wf_of(
            {"T": "manualTrigger", "Orig": "set", "Enriched": "set", "M": "merge"},
            [("T", 0, "Orig", 0), ("Orig", 0, "Enriched", 0), ("Orig", 0, "M", 0), ("Enriched", 0, "M", 1)],
        )
        self.assertEqual(high(wf, "P001"), ["Enriched"])


class AbelWorkflowsClean(unittest.TestCase):
    def test_no_high_findings(self):
        for name in ("1-capture-transcript.json", "2-notify-of-meeting-tasks.json", "5-draft-follow-up-email.json"):
            with self.subTest(workflow=name):
                issues, _ = validate_n8n.run_all_checks(load(name))
                self.assertEqual([i for i in issues if i["severity"] == "HIGH"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
