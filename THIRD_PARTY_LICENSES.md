# Third-Party License Audit & Governance Invariants

> **Project:** CareCenter for Codex (`dev-bricks/CareCenter-for-Codex`)  
> **Package:** `carecenter-for-codex` (CLI: `codex-logwartung`)  
> **Repository:** [https://github.com/dev-bricks/CareCenter-for-Codex](https://github.com/dev-bricks/CareCenter-for-Codex)  
> **Audit Date:** 2026-09-20
> **Scope:** Direct runtime dependencies, build/packaging tooling, system API boundaries, and runtime safety invariants.

---

## 1. Project License

CareCenter for Codex is open-source software licensed under the **MIT License**.

```text
MIT License

Copyright (c) 2026 Lukas Geiger / dev-bricks / open-bricks

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 2. Direct Runtime Dependencies

| Package | Version Constraint | Audited Version | License Metadata | SPDX Identifier | Source / Upstream | Purpose in CareCenter |
|---|---|---|---|---|---|---|
| **PySide6** | `>=6.7` | `6.11.1` | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | `LGPL-3.0-only` | [PyPI](https://pypi.org/project/PySide6/) | Desktop System Tray UI, QThread async workers, settings dialog, notifications |
| **tomlkit** | `>=0.13` | `0.15.0` | MIT License | `MIT` | [PyPI](https://pypi.org/project/tomlkit/) | Style-preserving TOML parsing and serialization for configuration files |

### LGPL-3.0 Compliance Details for PySide6
- **Dynamic Linking:** PySide6 and the underlying Qt6 shared libraries (`.dll`) are loaded dynamically as unmodified binary wheels or shared libraries.
- **No Derivative Modifications:** No source files of the Qt Project or PySide6 are modified, recompiled, or sublicensed in this repository.
- **Reverse Engineering & Relinking:** In compliance with Section 4 of LGPLv3, users retain the freedom to replace the installed PySide6 wheels with their own compatible versions without violating the application license.

---

## 3. Integration & Build Dependencies

| Package | Declared Usage | Constraint / Pin | License | SPDX Identifier | Source / Upstream |
|---|---|---|---|---|---|
| **safe-start-for-codex** | Process startup gating & burst mitigation | commit `dcb369a64f403f6551bcb3bac16565c56ec79474` (v1.1.3) | MIT License | `MIT` | [GitHub](https://github.com/dev-bricks/safe-start-for-codex) |
| **PyInstaller** | Optional standalone Windows EXE compilation | `>=6.0` | GPL-2.0-or-later with PyInstaller Exception | `GPL-2.0-or-later WITH PyInstaller-exception` | [PyPI](https://pypi.org/project/pyinstaller/) |
| **hatchling** | PEP 517 build backend & wheel creation | `>=1.25` | MIT License | `MIT` | [PyPI](https://pypi.org/project/hatchling/) |

*Note on PyInstaller Exception:* The PyInstaller special exception explicitly permits distributing the output binary under the application's native MIT license.

---

## 4. Development & Verification Dependencies

| Tool | Constraint | Audited Version | License | SPDX Identifier | Source / Upstream | Purpose |
|---|---|---|---|---|---|---|
| **pytest** | `>=8.0` | `9.1.1` | MIT License | `MIT` | [PyPI](https://pypi.org/project/pytest/) | Automated test execution and contract verification (409+ tests) |
| **Ruff** | `>=0.5` | `0.15.21` | MIT / Apache-2.0 | `MIT OR Apache-2.0` | [PyPI](https://pypi.org/project/ruff/) | Static analysis, code formatting, and linting |
| **mypy** | `>=1.10` | `2.3.0` | MIT License | `MIT` | [PyPI](https://pypi.org/project/mypy/) | Strict static type checking |
| **jsonschema[format]** | `>=4.23` | `4.26.0` | MIT License | `MIT` | [PyPI](https://pypi.org/project/jsonschema/) | Draft 2020-12 schema validation with RFC 3339 format assertions for exchange-contract tests |
| **rfc3339-validator** | `>=0.1.4` | `0.1.4` | MIT License | `MIT` | [PyPI](https://pypi.org/project/rfc3339-validator/) | RFC 3339 date-time format assertion for JSON Schema Draft 2020-12 validation |
| **isoduration** | `>=20.11.0` | `20.11.0` | ISC License | `ISC` | [PyPI](https://pypi.org/project/isoduration/) | ISO 8601 duration parsing and validation for JSON Schema |

---

## 5. Python Standard Library & OS Subsystem Integration

The application relies on core Python 3.12/3.13 standard library modules governed by the **Python Software Foundation (PSF) License Agreement 2.0**:

- `sqlite3`: Transactional database management, WAL checkpointing, and `PRAGMA integrity_check`.
- `pathlib`, `os`, `sys`, `shutil`: File system navigation, path resolution, and atomic directory backups.
- `subprocess`: Non-elevated process query (`tasklist`, `powershell`, Win32 API calls).
- `json`, `dataclasses`, `typing`: Data structures, configuration management, and type contracts.
- `argparse`: Command-line interface routing for `codex-logwartung`.
- `logging`: Local rotating audit log files (`app.log`).

### Windows OS & API Boundaries
- **Unprivileged Execution:** All default commands operate strictly in Windows User Space under `RunAsInvoker` mode. No UAC elevation or kernel-level drivers are deployed.
- **Data Location:** Local user state resides in `%LOCALAPPDATA%\CareCenterForCodex` (or legacy `C:\_Local_DEV\codex-maintenance`).

---

## 6. Table of 10 Governance & Runtime Safety Invariants

CareCenter enforces 10 strict runtime invariants across all CLI and Tray workflows:

| Invariant Code | Category | Name & Guarantee | Verification & Enforcement Mechanism |
|---|---|---|---|
| **INV-LOCAL-01** | Privacy & Egress | **100% Local-First & Zero-Egress** | Fully offline runtime loop; zero background network traffic, zero analytics, zero external API queries. The isolated `--live-pages` flag is an explicit manual release preflight. |
| **INV-NOELEV-02** | Security & Privileges | **Unprivileged User-Mode (RunAsInvoker)** | All watcher, tray, and database maintenance tasks execute strictly within standard user permissions. No UAC elevation is required for routine maintenance. |
| **INV-ISOLAT-03** | Process Safety | **Fail-Closed Process Protection & Singleton Isolation** | Ghost process reaping targets only inactive desktop leftovers. Multi-point CPU delta sampling and parent-PID tree inspection prevent accidental termination of active processes. |
| **INV-SESSIM-04** | Agent Protection | **CLI Session & Agent Workstation Immunity** | Node-based Codex CLI runs and detached `codex exec` background jobs are shielded from termination. Any active CLI execution acts as a global mutation lock for thread stores. |
| **INV-ATOMIC-05** | Database Safety | **Pre-Mutation SQLite Snapshot & WAL Integrity** | The `state_5.sqlite` database is never altered in-place without a complete verified snapshot copy including WAL and SHM journal files. Any backup failure aborts maintenance immediately. |
| **INV-CRYPTO-06** | Data Integrity | **Cryptographic & Structural Integrity Gate** | `PRAGMA integrity_check` is executed on the backup copy prior to checkpointing or VACUUM. Any corrupt page or schema mismatch blocks all downstream operations. |
| **INV-GRACE-07** | Stability Timing | **Mandatory Safety Grace Windows** | Hard 30-minute grace window for runtime orphans and 300-second floor for empty threads ensure initialization spikes are never mistaken for dead leftovers. |
| **INV-STAGGER-08** | Load Balancing | **Staggered Automation Unpausing** | Recovery avoids flooding the OpenAI Codex host by unpausing automations in configurable intervals (default: 60s windows) via the Safe Start coordinator. |
| **INV-NONDEST-09** | OS Repair | **Non-Destructive AppX Resolution** | Microsoft Store package troubleshooting applies bounded escalation: no-admin cleanup -> admin suggestion -> Store reinstall PDP link. Destructive resets are strictly forbidden. |
| **INV-SLA-10** | Quality Assurance | **Strict Verification Parity & Security SLA** | 100% green test suite (409+ tests), clean linters, 48-hour response SLA, and 5-business-day triage commitment for security disclosures. |

---

## 7. Trademarks & Disclaimers

- "OpenAI" and "Codex" are registered trademarks or trademarks of OpenAI, Inc.
- CareCenter for Codex is an independent, community-developed open-source project and is **not** affiliated with, sponsored by, or endorsed by OpenAI.
- Trademarks are used solely for descriptive and compatibility identification purposes under fair use.
