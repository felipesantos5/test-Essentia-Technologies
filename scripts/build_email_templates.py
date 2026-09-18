#!/usr/bin/env python3
"""Build the HTML e-mails of the n8n sub-workflows from n8n/email-templates.

Each template is a content partial rendered inside layout.html and inlined into the Gmail
node of its workflow. Templates hold no logic: they only use `{{ $json.<field> }}`
placeholders, and every field must be assigned by the workflow's "Preparar e-mail" node,
which formats the API data. Standard library only, so it runs in CI without installing anything.

Usage:
    build_email_templates.py            write the rendered HTML into n8n/workflows
    build_email_templates.py --check    exit 1 if a workflow is out of date with its template
    build_email_templates.py --preview  also render with sample data into tmp/email-preview
"""

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "n8n" / "email-templates"
WORKFLOWS_DIR = ROOT / "n8n" / "workflows"
PREVIEW_DIR = ROOT / "tmp" / "email-preview"

# Mail clients only load images from a public URL, so the assets are served from GitHub.
ASSETS_URL = (
    "https://raw.githubusercontent.com/felipesantos5/test-Essentia-Technologies"
    "/main/n8n/email-templates/assets"
)
ASSETS_MARKER = "%ASSETS_URL%"
CONTENT_SLOT = "<!-- slot:content -->"
PREPARE_NODE = "Preparar e-mail"
PLACEHOLDER = re.compile(r"\{\{ \$json\.([a-z_]+) \}\}")

SAMPLE_CLINIC = {
    "clinic_name": "Clínica Essentia Saúde",
    "clinic_address": "Av. Paulista, 1000, conjunto 101 - Bela Vista, São Paulo - SP",
    "clinic_phone": "(11) 4000-1234",
    "clinic_phone_href": "tel:+551140001234",
    "clinic_email": "contato@clinica-essentia.example",
}
SAMPLE_APPOINTMENT = {
    "patient_name": "João Pereira",
    "patient_first_name": "João",
    "specialty": "Cardiologia",
    "doctor_name": "Dr. Carlos Eduardo Lima",
    "protocol": "#1",
    "date_long": "Quinta-feira, 17 de setembro de 2026",
    "time_range": "08:40 às 09:20",
    "day": "17",
    "month_short": "SET",
    "weekday_short": "QUI",
}


@dataclass(frozen=True)
class Email:
    template: str
    workflow: str
    send_node: str
    sample: dict[str, str]


EMAILS = (
    Email(
        template="appointment-booked.html",
        workflow="clinic-book-appointment.json",
        send_node="Enviar e-mail de confirmação",
        sample={
            **SAMPLE_CLINIC,
            **SAMPLE_APPOINTMENT,
            "subject": "Consulta confirmada: Cardiologia em 17/09/2026 às 08:40",
            "preheader": "Cardiologia com Dr. Carlos Eduardo Lima, quinta-feira, 17 de setembro "
            "às 08:40. Chegue com 15 minutos de antecedência.",
            "price": "R$ 380,00",
            "calendar_url": "https://calendar.google.com/calendar/render?action=TEMPLATE",
            "maps_url": "https://www.google.com/maps/search/?api=1&query=Av.%20Paulista%2C%201000",
        },
    ),
    Email(
        template="appointment-cancelled.html",
        workflow="clinic-cancel-appointment.json",
        send_node="Enviar e-mail de cancelamento",
        sample={
            **SAMPLE_CLINIC,
            **SAMPLE_APPOINTMENT,
            "subject": "Consulta cancelada: Cardiologia em 17/09/2026 às 08:40",
            "preheader": "Sua consulta de Cardiologia com Dr. Carlos Eduardo Lima, quinta-feira, "
            "17 de setembro às 08:40, foi cancelada.",
            "cancelled_at": "16/09/2026 às 14:32",
        },
    ),
)


def render(email: Email, assets_url: str) -> str:
    layout = (TEMPLATES_DIR / "layout.html").read_text(encoding="utf-8")
    content = (TEMPLATES_DIR / email.template).read_text(encoding="utf-8")
    return layout.replace(CONTENT_SLOT, content.rstrip("\n")).replace(ASSETS_MARKER, assets_url)


def lint(email: Email, html: str, workflow: dict) -> list[str]:
    nodes = {node["name"]: node for node in workflow["nodes"]}
    if PREPARE_NODE not in nodes or email.send_node not in nodes:
        return [f"workflow must have the nodes '{PREPARE_NODE}' and '{email.send_node}'"]

    errors: list[str] = []
    links = workflow["connections"].get(PREPARE_NODE, {}).get("main", [[]])[0]
    if not any(link["node"] == email.send_node for link in links):
        errors.append(f"'{PREPARE_NODE}' must connect directly to '{email.send_node}'")

    leftover = PLACEHOLDER.sub("", html)
    if "{{" in leftover or "}}" in leftover:
        errors.append("templates only accept `{{ $json.<field> }}` placeholders")

    assignments = nodes[PREPARE_NODE]["parameters"]["assignments"]["assignments"]
    fields = {assignment["name"] for assignment in assignments}
    used = set(PLACEHOLDER.findall(html))
    errors += [
        f"field '{name}' is not assigned by '{PREPARE_NODE}'" for name in sorted(used - fields)
    ]
    errors += [f"field '{name}' has no preview sample" for name in sorted(used - set(email.sample))]
    return errors


def write_preview(email: Email) -> Path:
    html = PLACEHOLDER.sub(lambda match: email.sample[match[1]], render(email, "assets"))
    shutil.copytree(TEMPLATES_DIR / "assets", PREVIEW_DIR / "assets", dirs_exist_ok=True)
    path = PREVIEW_DIR / email.template
    path.write_text(html, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if a workflow is out of date")
    mode.add_argument("--preview", action="store_true", help="also render with sample data")
    args = parser.parse_args()

    if args.preview:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    failed = False
    for email in EMAILS:
        path = WORKFLOWS_DIR / email.workflow
        workflow = json.loads(path.read_text(encoding="utf-8"))
        html = render(email, ASSETS_URL)
        errors = lint(email, html, workflow)
        if errors:
            failed = True
            print(f"[FAIL] {email.template} -> {email.workflow}")
            for error in errors:
                print(f"       - {error}")
            continue

        send_node = next(node for node in workflow["nodes"] if node["name"] == email.send_node)
        message = f"={html}"
        if send_node["parameters"]["message"] == message:
            status = "ok"
        elif args.check:
            failed = True
            status = "OUTDATED (run `make email-templates`)"
        else:
            send_node["parameters"]["message"] = message
            content = json.dumps(workflow, indent=2, ensure_ascii=False)
            path.write_text(f"{content}\n", encoding="utf-8")
            status = "updated"
        print(f"[{status}] {email.template} -> {email.workflow}")

        if args.preview:
            print(f"       preview: {write_preview(email).relative_to(ROOT)}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
