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


class DraftReviewedByKendra(unittest.TestCase):
    KENDRA = "2bb2e9c3-4618-4a70-8d41-b7b5b50cd489"

    def test_draft_body_assigns_kendra(self):
        body = node(load("5-draft-follow-up-email.json"), "Draft in Missive")["parameters"]["jsonBody"]
        rendered = body[1:]
        for expr, value in {
            "{{ $json.output.subject.toJsonString() }}": '"Subject"',
            "{{ $json.html.toJsonString() }}": '"<p>Body</p>"',
            "{{$json.missive.from_field.toJsonString() }}": '{"address": "alex@ahbadvisors.com"}',
            "{{$json.missive.to_fields.toJsonString() }}": "[]",
            "{{$json.missive.cc_fields.toJsonString() }}": "[]",
        }.items():
            self.assertIn(expr, rendered)
            rendered = rendered.replace(expr, value)
        draft = json.loads(rendered)["drafts"]
        self.assertEqual(draft["add_users"], [self.KENDRA])
        self.assertEqual(draft["add_assignees"], [self.KENDRA])
        self.assertTrue(draft["organization"])


class DraftVoiceCheck(unittest.TestCase):
    """The shipped Draft Check node enforces the template's HARD RULES (2026-11-02)."""

    TEMPLATE = (
        "## HARD RULES\n* Three to five sentences. No headers.\n"
        "* Scrub before send. No em-dashes, no semicolons. Banned: \"I hope this finds you well,\" "
        "\"wanted to reach out,\" \"circle back,\" \"it was great connecting.\"\n"
    )
    BAD = (
        "Jordan,\n\nYour line about trying to keep your network live in ad tech while you lean into the CTV/FAST "
        "and ad robot experiments stuck with me. If it is useful, I am glad to be a sounding board on strategy and "
        "finance angles with CTV clients or investors as you keep pressure-testing those ideas. I really like the way "
        "your measurement work lines up with my more strategy and capital-markets view of where CTV and the pipes are "
        "heading, and it feels like a good basis for future collaboration. No real ask now. I am glad we left it that "
        "we will keep a light recurring check in on the calendar and try for a coffee when you are in New York.\n\nAlex"
    )
    GOOD = (
        "Priya,\n\nThanks for making the time. The way you described the first ninety days at Acme, rebuilding "
        "measurement ahead of the agency review, explains why the sequencing matters more than the selection.\n\n"
        "You asked how other retail media teams staffed that. I put the question to two people who have done it and "
        "will come back if either has something useful.\n\nNo ask here. Glad we connected.\n\nAlex"
    )

    def run_check(self, content, node_name="Draft Check"):
        code = node(load("5-draft-follow-up-email.json"), node_name)["parameters"]["jsCode"]
        js = (f"const $json = {{ output: {{ content: {json.dumps(content)} }} }};\n"
              f"const $ = () => ({{ item: {{ json: {{ markdown_description: {json.dumps(self.TEMPLATE)} }} }} }});\n"
              f"const out = (function() {{\n{code}\n}})();\nprocess.stdout.write(JSON.stringify(out.json.check));")
        res = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
        return json.loads(res.stdout)

    def test_bad_draft_fails(self):
        check = self.run_check(self.BAD)
        joined = " | ".join(check["violations"])
        self.assertIn("keep it under 90", joined)
        self.assertIn('"sounding board"', joined)
        self.assertIn('"feels like"', joined)
        self.assertEqual(check["attempt"], 1)

    def test_template_example_passes(self):
        self.assertEqual(self.run_check(self.GOOD)["violations"], [])
        self.assertEqual(self.run_check(self.GOOD, "Draft Check 2")["attempt"], 2)

    def test_dash_semicolon_placeholder(self):
        check = self.run_check("Sam,\n\nGood to meet — truly; [Alex: add the line].\n\nAlex")
        self.assertIn("uses a dash (— or –)", check["violations"])
        self.assertIn("uses a semicolon", check["violations"])
        self.assertTrue(check["needs_input"])

    def test_wiring_and_prompt(self):
        wf = load("5-draft-follow-up-email.json")
        c = wf["connections"]
        self.assertEqual(c["Follow Email Draft Agent"]["main"][0][0]["node"], "Draft Check")
        self.assertEqual(c["Redraft?"]["main"][0][0]["node"], "Redraft Agent")
        self.assertEqual(c["Redraft?"]["main"][1][0]["node"], "Split Internal & External Recipients")
        self.assertEqual(c["Draft Check 2"]["main"][0][0]["node"], "Split Internal & External Recipients")
        for name in ("Follow Email Draft Agent", "Redraft Agent"):
            sm = node(wf, name)["parameters"]["options"]["systemMessage"]
            self.assertIn("HARD RULES are limits", sm)
            self.assertNotIn("3cventures", sm)
            self.assertNotIn("professional, and warm", sm)
        self.assertIn("<VIOLATIONS>", node(wf, "Redraft Agent")["parameters"]["text"])
        conf = node(wf, "Missive Confirmation")["parameters"]["assignments"]["assignments"][0]["value"]
        self.assertIn("Needs a human pass", conf)


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
