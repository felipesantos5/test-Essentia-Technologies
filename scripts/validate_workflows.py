#!/usr/bin/env python3
"""Static consistency checks for the n8n workflow exports in n8n/workflows.

Catches mistakes that n8n would only reveal at import or run time: broken connections,
node versions that the pinned n8n image does not ship, sub-workflow and credential
references that the bootstrap does not provision, and secrets committed by accident.
Standard library only, so it runs in CI without installing anything.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "n8n" / "workflows"

# typeVersions verified against n8nio/n8n:2.39.6 (`n8n export:nodes`).
SUPPORTED_NODES: dict[str, set[float]] = {
    "n8n-nodes-base.webhook": {2.1},
    "n8n-nodes-base.respondToWebhook": {1.5},
    "n8n-nodes-base.switch": {3.4},
    "n8n-nodes-base.if": {2.3},
    "n8n-nodes-base.set": {3.5},
    "n8n-nodes-base.httpRequest": {4.5},
    "n8n-nodes-base.httpRequestTool": {4.5},
    "n8n-nodes-base.executeWorkflowTrigger": {1.1},
    "n8n-nodes-base.extractFromFile": {1.1},
    "n8n-nodes-base.gmail": {2.2},
    "n8n-nodes-base.stickyNote": {1},
    "@n8n/n8n-nodes-langchain.agent": {3.1},
    "@n8n/n8n-nodes-langchain.lmChatOpenAi": {1.3},
    "@n8n/n8n-nodes-langchain.memoryBufferWindow": {1.3},
    "@n8n/n8n-nodes-langchain.openAi": {2.3},
    "@n8n/n8n-nodes-langchain.toolWorkflow": {2.2},
}

# Credentials created by n8n/bootstrap/render-credentials.mjs.
PROVISIONED_CREDENTIALS = {
    "httpHeaderAuth": "clinicApiKeyCred",
    "openAiApi": "clinicOpenAiCred",
    "gmailOAuth2": "clinicGmailCred1",
}

SECRET_PATTERNS = {
    "OpenAI key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "Google OAuth client secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),
    "Google access token": re.compile(r"ya29\.[A-Za-z0-9_-]{20,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
}

SUB_WORKFLOW_CALLERS = {
    "@n8n/n8n-nodes-langchain.toolWorkflow",
    "n8n-nodes-base.executeWorkflow",
}

# Calls to external services (Gmail, OpenAI transcription and TTS) must retry before failing.
RETRY_REQUIRED_NODES = {"n8n-nodes-base.gmail", "@n8n/n8n-nodes-langchain.openAi"}

# `$('Node name')` inside expressions; a renamed node would only break at run time.
NODE_REFERENCE = re.compile(r"\$\('([^']+)'\)")


def check_workflow(path: Path, workflow: dict, known_ids: set[str]) -> list[str]:
    errors: list[str] = []
    nodes = workflow.get("nodes", [])
    names = Counter(node["name"] for node in nodes)
    errors += [f"duplicate node name '{name}'" for name, count in names.items() if count > 1]

    for node in nodes:
        label = f"node '{node['name']}'"
        versions = SUPPORTED_NODES.get(node["type"])
        if versions is None:
            errors.append(f"{label}: type {node['type']} is not in the verified node list")
        elif node["typeVersion"] not in versions:
            errors.append(
                f"{label}: typeVersion {node['typeVersion']} not verified for {node['type']}"
            )

        for credential_type, reference in node.get("credentials", {}).items():
            expected = PROVISIONED_CREDENTIALS.get(credential_type)
            if reference.get("id") != expected:
                errors.append(
                    f"{label}: credential {credential_type} id {reference.get('id')!r} "
                    f"is not provisioned (expected {expected!r})"
                )

        if node["type"] in SUB_WORKFLOW_CALLERS:
            target = node["parameters"].get("workflowId", {}).get("value")
            if target not in known_ids:
                errors.append(f"{label}: calls unknown workflow id {target!r}")

        if node["type"] in RETRY_REQUIRED_NODES and not node.get("retryOnFail"):
            errors.append(f"{label}: external call must set retryOnFail")

        parameters = json.dumps(node.get("parameters", {}), ensure_ascii=False)
        for reference in sorted(set(NODE_REFERENCE.findall(parameters)) - set(names)):
            errors.append(f"{label}: expression references unknown node '{reference}'")

    connected: set[str] = set()
    for source, outputs in workflow.get("connections", {}).items():
        if source not in names:
            errors.append(f"connection from unknown node '{source}'")
        connected.add(source)
        for branches in outputs.values():
            for branch in branches:
                for link in branch or []:
                    if link["node"] not in names:
                        errors.append(
                            f"connection from '{source}' to unknown node '{link['node']}'"
                        )
                    connected.add(link["node"])

    orphans = [
        node["name"]
        for node in nodes
        if node["type"] != "n8n-nodes-base.stickyNote" and node["name"] not in connected
    ]
    errors += [f"node '{name}' is not connected" for name in orphans]

    is_sub_workflow = any(node["type"] == "n8n-nodes-base.executeWorkflowTrigger" for node in nodes)
    if is_sub_workflow and workflow.get("settings", {}).get("callerPolicy") is None:
        errors.append("sub-workflow must set settings.callerPolicy")

    raw = path.read_text(encoding="utf-8")
    errors += [
        f"possible {kind} committed"
        for kind, pattern in SECRET_PATTERNS.items()
        if pattern.search(raw)
    ]
    return errors


def main() -> int:
    paths = sorted(WORKFLOWS_DIR.glob("*.json"))
    if not paths:
        print(f"no workflows found in {WORKFLOWS_DIR}")
        return 1

    workflows = {path: json.loads(path.read_text(encoding="utf-8")) for path in paths}
    ids = Counter(workflow.get("id") for workflow in workflows.values())
    failed = False
    for workflow_id, count in ids.items():
        if not workflow_id or count > 1:
            print(f"workflow id {workflow_id!r} is missing or duplicated")
            failed = True

    webhook_paths = Counter(
        node["parameters"].get("path")
        for workflow in workflows.values()
        for node in workflow["nodes"]
        if node["type"] == "n8n-nodes-base.webhook"
    )
    for webhook_path, count in webhook_paths.items():
        if count > 1:
            print(f"webhook path '{webhook_path}' is used by {count} nodes")
            failed = True

    for path, workflow in workflows.items():
        errors = check_workflow(path, workflow, set(ids))
        status = "FAIL" if errors else "ok"
        print(f"[{status}] {path.name} ({workflow.get('name')}, {len(workflow['nodes'])} nodes)")
        for error in errors:
            print(f"       - {error}")
        failed = failed or bool(errors)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
