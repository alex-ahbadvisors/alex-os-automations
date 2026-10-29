#!/usr/bin/env python3
"""
test_abel_task_titles.py -- Slack-approved task titles reach ClickUp verbatim
([3] Create Tasks from Slack Email To-Do, [4] Create Tasks from Slack), 2026-10-29.

Regression: "Waiting on Pete Crofut: ..." was created as
"Follow up with Pete ... (Kendra Fidlin)" (ClickUp 868mpmaaz). Athena's
waiting-on pass keys on the "Waiting on " prefix. The owner belongs in
assignees only.

Covers the shipped Create Task name expression (run under `node`) and the
Task Generator Agent's title rule. Hermetic. Run:
python3 scripts/tests/test_abel_task_titles.py
"""
import json
import os
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOWS = ("3-create-tasks-from-slack-email-to-do.json", "4-create-tasks-from-slack.json")


def load(name):
    with open(os.path.join(REPO, "n8n-workflows", name)) as f:
        return json.load(f)


class VerbatimTitles(unittest.TestCase):
    def name_expression(self, wf):
        exprs = [n["parameters"]["name"] for n in wf["nodes"]
                 if n["type"] == "n8n-nodes-base.clickUp" and "$json.task" in str(n["parameters"].get("name", ""))]
        self.assertEqual(len(exprs), 1)
        return exprs[0]

    def run_expression(self, expr, task):
        body = expr[3:-2].strip()
        js = f"const $json = {{ task: {json.dumps(task)} }};\nprocess.stdout.write(JSON.stringify({body}));"
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_name_is_verbatim_without_owner(self):
        for wf_name in WORKFLOWS:
            expr = self.name_expression(load(wf_name))
            with self.subTest(workflow=wf_name):
                title = "Waiting on Pete Crofut: signed SOW back"
                got = self.run_expression(expr, {"name": f"  {title} ", "assignee": "Kendra Fidlin"})
                self.assertEqual(got, title)
                self.assertEqual(self.run_expression(expr, {"name": None, "assignee": None}), "")

    def test_generator_rule_keeps_title(self):
        for wf_name in WORKFLOWS:
            prompts = [n["parameters"]["options"]["systemMessage"] for n in load(wf_name)["nodes"]
                       if "task-extraction agent" in n["parameters"].get("options", {}).get("systemMessage", "")]
            with self.subTest(workflow=wf_name):
                self.assertEqual(len(prompts), 1)
                self.assertIn("copied **verbatim**", prompts[0])
                self.assertIn("Waiting on Pete Crofut", prompts[0])
                self.assertIn("never add the owner's name", prompts[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
