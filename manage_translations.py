#!/usr/bin/env python3
"""manage_translations.py - Tool for i18n management, scanning and CI check gate.

Implements CCC-I18N-03 for CareCenter for Codex (Tier-2 Mehrsprachigkeit nach Policy P-006).

Commands:
    python manage_translations.py --check
    python manage_translations.py --scan
    python manage_translations.py --export-json
    python manage_translations.py --sync
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
LOCALES_FILE = ROOT_DIR / "locales" / "translations.json"
I18N_MODULE_FILE = SRC_DIR / "codex_logdatenbank_wartung" / "i18n.py"

# Add src to path to import i18n
sys.path.insert(0, str(SRC_DIR))
from codex_logdatenbank_wartung.i18n import (  # noqa: E402
    _CATALOG,
    export_translations_json,
    load_translations_file,
)

T_CALL_PATTERN = re.compile(r'\bt\(\s*["\']([a-zA-Z0-9_]+)["\']')
PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)")


def scan_source_code_keys(src_dir: Path | None = None) -> set[str]:
    """Scan all Python files under src/ for t('key') or t(\"key\") calls."""
    if src_dir is None:
        src_dir = SRC_DIR
    found_keys: set[str] = set()
    for py_file in src_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[WARN] Could not read {py_file}: {e}", file=sys.stderr)
            continue
        for match in T_CALL_PATTERN.finditer(content):
            found_keys.add(match.group(1))
    return found_keys


def validate_translations(
    catalog: dict[str, dict[str, str]],
    required_languages: tuple[str, ...] = ("de", "en", "es"),
) -> list[str]:
    """Validate that every key in catalog has all required languages and matching placeholders."""
    errors: list[str] = []
    for key, trans in sorted(catalog.items()):
        # Check required languages
        for lang in required_languages:
            if lang not in trans or not isinstance(trans[lang], str) or not trans[lang].strip():
                errors.append(f"Key '{key}': missing or empty translation for '{lang}'")

        # Check placeholder consistency
        base_lang = "de" if "de" in trans else ("en" if "en" in trans else None)
        if base_lang:
            base_placeholders = set(PLACEHOLDER_PATTERN.findall(trans[base_lang]))
            for other_lang in required_languages:
                if other_lang in trans and trans[other_lang]:
                    other_placeholders = set(PLACEHOLDER_PATTERN.findall(trans[other_lang]))
                    if other_placeholders != base_placeholders:
                        errors.append(
                            f"Key '{key}': placeholder mismatch between '{base_lang}' {base_placeholders} "
                            f"and '{other_lang}' {other_placeholders}"
                        )
    return errors


def check_gate(verbose: bool = True) -> int:
    """CI Check Gate: Validates source code keys, catalog coverage and translations.json parity.

    Returns 0 on success, 1 on errors.
    """
    errors: list[str] = []

    # 1. Check catalog itself
    catalog_errors = validate_translations(_CATALOG, required_languages=("de", "en", "es"))
    if catalog_errors:
        errors.extend(catalog_errors)

    # 2. Check source code keys vs catalog
    source_keys = scan_source_code_keys(SRC_DIR)
    missing_in_catalog = source_keys - set(_CATALOG.keys())
    if missing_in_catalog:
        for k in sorted(missing_in_catalog):
            errors.append(f"Source code uses key '{k}' which is missing in _CATALOG")

    # 3. Check translations.json existence and parity
    if not LOCALES_FILE.is_file():
        errors.append(f"Translations file missing: {LOCALES_FILE}")
    else:
        try:
            with open(LOCALES_FILE, encoding="utf-8") as f:
                json_data = json.load(f)
            if not isinstance(json_data, dict):
                errors.append("translations.json is not a JSON object")
            else:
                json_errors = validate_translations(json_data, required_languages=("de", "en", "es"))
                if json_errors:
                    errors.extend([f"locales/translations.json: {e}" for e in json_errors])

                # Check parity between _CATALOG and JSON file
                cat_keys = set(_CATALOG.keys())
                json_keys = set(json_data.keys())
                if cat_keys != json_keys:
                    diff_missing = cat_keys - json_keys
                    diff_extra = json_keys - cat_keys
                    if diff_missing:
                        errors.append(f"translations.json is missing keys present in _CATALOG: {sorted(diff_missing)}")
                    if diff_extra:
                        errors.append(f"translations.json has extra keys not in _CATALOG: {sorted(diff_extra)}")
        except Exception as e:
            errors.append(f"Failed to read or parse {LOCALES_FILE}: {e}")

    if errors:
        print(f"[FAIL] i18n Check Gate detected {len(errors)} error(s):", file=sys.stderr)
        for err in errors[:50]:
            print(f"  - {err}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more errors.", file=sys.stderr)
        return 1

    if verbose:
        print(f"[OK] i18n Check Gate PASSED: {len(_CATALOG)} keys checked across ('de', 'en', 'es').")
        print(f"     Source scan verified {len(source_keys)} keys called in src/.")
        print(f"     JSON parity verified with {LOCALES_FILE.name}.")
    return 0


def sync_translations(verbose: bool = True) -> int:
    """Sync between in-code _CATALOG and locales/translations.json."""
    if not LOCALES_FILE.is_file():
        export_translations_json(LOCALES_FILE)
        if verbose:
            print(f"[+] Exported {len(_CATALOG)} keys to {LOCALES_FILE}")
        return 0

    # Load file and merge
    loaded_count = load_translations_file(LOCALES_FILE)
    export_translations_json(LOCALES_FILE)
    if verbose:
        print(f"[OK] Synced {len(_CATALOG)} keys with {LOCALES_FILE} (merged {loaded_count} keys).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CareCenter for Codex i18n management and validation CLI."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate translation parity and exit with 0 (clean) or 1 (errors).",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan src/ for translation keys and report statistics.",
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Export in-code _CATALOG to locales/translations.json.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Bidirectionally synchronize _CATALOG and locales/translations.json.",
    )

    args = parser.parse_args()

    if args.check:
        return check_gate(verbose=True)
    elif args.scan:
        keys = scan_source_code_keys(SRC_DIR)
        print(f"[i] Scanned {SRC_DIR}: found {len(keys)} unique translation keys in code.")
        for k in sorted(keys):
            print(f"    - {k}")
        return 0
    elif args.export_json:
        out = export_translations_json(LOCALES_FILE)
        print(f"[+] Exported {len(_CATALOG)} keys to {out}")
        return 0
    elif args.sync:
        return sync_translations(verbose=True)
    else:
        # Default action: check
        return check_gate(verbose=True)


if __name__ == "__main__":
    sys.exit(main())
