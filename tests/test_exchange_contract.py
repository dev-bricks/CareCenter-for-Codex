"""Contracts for the privacy-minimized CareCenter -> BACH/OCEAN snapshot."""

from __future__ import annotations

import ast
import copy
import json
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "contracts" / "carecenter-health-exchange-v1.schema.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "carecenter-health-exchange-v1.json"
CONTRACT_PATH = ROOT / "CARE_CENTER_EXCHANGE_CONTRACT.md"
HEALTH_PATH = ROOT / "src" / "codex_logdatenbank_wartung" / "health.py"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _property_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            names.update(properties)
        for child in value.values():
            names.update(_property_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(_property_names(child))
    return names


def _reference_consumer_accepts(schema: dict[str, object], payload: dict[str, object]) -> bool:
    """Apply consumer checks that complement JSON Schema, including strict time parsing."""
    properties = schema["properties"]
    if set(payload) != set(schema["required"]):
        return False
    for name in ("schema", "contract_version", "publisher_component"):
        if payload[name] != properties[name]["const"]:
            return False

    uuid_pattern = schema["$defs"]["uuid_v4"]["pattern"]
    for name in ("publisher_instance", "publisher_epoch"):
        if not isinstance(payload[name], str) or not re.fullmatch(uuid_pattern, payload[name]):
            return False

    generated_at = payload["generated_at"]
    if not isinstance(generated_at, str):
        return False
    if not re.fullmatch(properties["generated_at"]["pattern"], generated_at):
        return False
    try:
        parsed_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed_time.utcoffset() is None or parsed_time.utcoffset().total_seconds() != 0:
        return False

    checkpoint = payload["source_checkpoint"]
    if isinstance(checkpoint, bool) or not isinstance(checkpoint, int) or checkpoint < 0:
        return False
    if payload["overall_status"] not in properties["overall_status"]["enum"]:
        return False
    if not isinstance(payload["issues"], dict):
        return False

    issue_catalogue = schema["$defs"]["issues"]
    for code, issue in payload["issues"].items():
        issue_link = issue_catalogue["properties"].get(code)
        if issue_link is None or not isinstance(issue, dict):
            return False
        issue_schema = schema["$defs"][issue_link["$ref"].rsplit("/", 1)[-1]]
        if set(issue) != set(issue_schema["required"]):
            return False
        for field, field_schema in issue_schema["properties"].items():
            if "const" in field_schema and issue[field] != field_schema["const"]:
                return False

    branches = [
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["overall_status"]["const"] == payload["overall_status"]
    ]
    if len(branches) != 1:
        return False
    rules = branches[0]["properties"]["issues"]
    issue_names = set(payload["issues"])
    if len(issue_names) < rules.get("minProperties", 0):
        return False
    if len(issue_names) > rules.get("maxProperties", len(issue_names)):
        return False
    allowed_names = rules.get("propertyNames", {}).get("enum")
    if allowed_names is not None and not issue_names <= set(allowed_names):
        return False
    if not set(rules.get("required", [])) <= issue_names:
        return False
    alternatives = rules.get("anyOf")
    return not alternatives or any(
        set(item.get("required", [])) <= issue_names for item in alternatives
    )


def test_schema_is_closed_versioned_and_status_discriminated() -> None:
    schema = _load_json(SCHEMA_PATH)
    properties = schema["properties"]

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(properties)
    assert properties["schema"]["const"] == "carecenter-health-exchange-v1"
    assert properties["contract_version"]["const"] == "1.0.0"
    assert schema["$defs"]["issues"]["additionalProperties"] is False
    assert {
        branch["properties"]["overall_status"]["const"] for branch in schema["oneOf"]
    } == {"ok", "warn", "critical", "unknown"}
    assert schema["x-freshness-policy"] == {
        "max_age_seconds": 900,
        "max_future_skew_seconds": 300,
    }


def test_example_snapshot_conforms_to_the_published_constraints() -> None:
    schema = _load_json(SCHEMA_PATH)
    payload = _load_json(FIXTURE_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    Draft202012Validator.check_schema(schema)
    validator.validate(payload)
    assert _reference_consumer_accepts(schema, payload)


def test_schema_and_reference_consumer_reject_invalid_snapshots() -> None:
    schema = _load_json(SCHEMA_PATH)
    fixture = _load_json(FIXTURE_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    ok_with_issues = copy.deepcopy(fixture)
    ok_with_issues["overall_status"] = "ok"

    critical_without_critical_issue = copy.deepcopy(fixture)
    critical_without_critical_issue["overall_status"] = "critical"

    unknown_with_partial_findings = copy.deepcopy(fixture)
    unknown_with_partial_findings["overall_status"] = "unknown"
    unknown_with_partial_findings["issues"]["diagnostic_unavailable"] = {
        "severity": "critical",
        "fixable": False,
    }

    identifying_instance = copy.deepcopy(fixture)
    identifying_instance["publisher_instance"] = "lukas-asus-gei"

    invalid_calendar_time = copy.deepcopy(fixture)
    invalid_calendar_time["generated_at"] = "2026-99-99T99:99:99Z"

    invalid_calendar_day = copy.deepcopy(fixture)
    invalid_calendar_day["generated_at"] = "2026-02-31T08:45:00Z"

    invalid_leap_day = copy.deepcopy(fixture)
    invalid_leap_day["generated_at"] = "2025-02-29T08:45:00Z"

    for invalid in (
        ok_with_issues,
        critical_without_critical_issue,
        unknown_with_partial_findings,
        identifying_instance,
        invalid_calendar_time,
        invalid_calendar_day,
        invalid_leap_day,
    ):
        assert not validator.is_valid(invalid)
        assert not _reference_consumer_accepts(schema, invalid)

    critical = copy.deepcopy(fixture)
    critical["overall_status"] = "critical"
    critical["issues"]["codex_start_blocked"] = {
        "severity": "critical",
        "fixable": True,
    }
    assert validator.is_valid(critical)
    assert _reference_consumer_accepts(schema, critical)

    unavailable = copy.deepcopy(fixture)
    unavailable["overall_status"] = "unknown"
    unavailable["issues"] = {
        "diagnostic_unavailable": {"severity": "critical", "fixable": False}
    }
    assert validator.is_valid(unavailable)
    assert _reference_consumer_accepts(schema, unavailable)


def test_source_issue_mapping_covers_code_severity_and_fixability_without_drift() -> None:
    schema = _load_json(SCHEMA_PATH)
    tree = ast.parse(HEALTH_PATH.read_text(encoding="utf-8"))
    diagnose = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "diagnose"
    )
    add_calls = [
        node
        for node in ast.walk(diagnose)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "report"
        and node.func.attr == "add"
    ]
    source_contract: dict[str, tuple[str, bool]] = {}
    for call in add_calls:
        assert len(call.args) >= 2
        assert isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)
        assert isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, str)
        fixable_keyword = next((item for item in call.keywords if item.arg == "fixable"), None)
        if fixable_keyword is None:
            fixable = False
        else:
            assert isinstance(fixable_keyword.value, ast.Constant)
            assert isinstance(fixable_keyword.value.value, bool)
            fixable = fixable_keyword.value.value
        source_contract[call.args[0].value] = (call.args[1].value, fixable)

    source_map = schema["x-source-code-map"]
    issue_catalogue = schema["$defs"]["issues"]["properties"]
    public_codes = set(issue_catalogue)

    assert len(source_contract) == len(add_calls)
    assert set(source_map) == set(source_contract)
    for source_code, (severity, fixable) in source_contract.items():
        mapping = source_map[source_code]
        assert mapping["severity"] == severity
        assert mapping["fixable"] is fixable
        assert mapping["public_code"] in public_codes
        public_issue_ref = issue_catalogue[mapping["public_code"]]["$ref"]
        public_issue = schema["$defs"][public_issue_ref.rsplit("/", 1)[-1]]
        assert public_issue["properties"]["severity"]["const"] == severity
        assert public_issue["properties"]["fixable"]["const"] is fixable
    assert "diagnostic_unavailable" in public_codes
    assert "diagnostic_unavailable" not in {
        mapping["public_code"] for mapping in source_map.values()
    }

    all_report_add_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "report"
        and node.func.attr == "add"
    ]
    assert {id(node) for node in all_report_add_calls} == {id(node) for node in add_calls}

    issue_constructors = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "HealthIssue"
    ]
    assert len(issue_constructors) == 1


def test_schema_excludes_sensitive_diagnostic_properties() -> None:
    schema = _load_json(SCHEMA_PATH)
    forbidden = {
        "hostname",
        "host_id",
        "username",
        "user_id",
        "device_id",
        "path",
        "filename",
        "pid",
        "commandline",
        "message",
        "raw_message",
        "thread",
        "session",
        "prompt",
        "response",
        "log",
        "backup",
        "automation_id",
        "database_size",
        "disk_free",
        "secret",
        "token",
        "credential",
        "config",
    }

    assert not (_property_names(schema) & forbidden)


def test_contract_keeps_exchange_one_way_fresh_and_non_authoritative() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")

    for marker in (
        "CareCenter for Codex -> BACH/OCEAN",
        "no inbound command",
        "complete replacement snapshot",
        "rejects a checkpoint less than",
        "or equal to that value",
        "unknown or rotated pair by default",
        "older than 900 seconds",
        "more than 300 seconds in the future",
        "mutually authenticate both publisher and recipient",
        "Schema validation establishes payload shape, not authenticity",
        "does not transfer maintenance authority",
    ):
        assert marker in contract


def test_german_contract_text_uses_real_umlauts_and_readmes_stay_in_sync() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    readme_dot = (ROOT / "README.de.md").read_bytes()
    readme_underscore = (ROOT / "README_de.md").read_bytes()

    assert "überträgt" in contract
    assert "vollständig" in contract
    assert "Größenangaben" in contract
    assert "Zufällige" in contract
    assert "\ufffd" not in contract
    assert readme_dot == readme_underscore
