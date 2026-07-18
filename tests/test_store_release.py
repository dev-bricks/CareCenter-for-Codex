from __future__ import annotations

import json
from pathlib import Path

from codex_logdatenbank_wartung import store_release
from codex_logdatenbank_wartung.store_release import validate_store_materials


def _write_store_files(project_root: Path, payload: dict[str, object]) -> None:
    (project_root / "store_package.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for name in ("STORE_LISTING.md", "PRIVACY_POLICY.md", "SUPPORT.md"):
        (project_root / name).write_text(f"# {name}\n", encoding="utf-8")
    docs_dir = project_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for name in ("privacy.md", "support.md"):
        (docs_dir / name).write_text(f"# {name}\n", encoding="utf-8")
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "build_store_pages.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "",
                "def build_pages(project_root: Path, output_dir: Path) -> list[Path]:",
                "    output_dir.mkdir(parents=True, exist_ok=True)",
                "    (output_dir / '.carecenter-pages-build').write_text('test marker\\n', encoding='utf-8')",
                "    written = []",
                "    for slug in ('privacy', 'support'):",
                "        target = output_dir / slug / 'index.html'",
                "        target.parent.mkdir(parents=True, exist_ok=True)",
                "        target.write_text('<!doctype html><title>' + slug + '</title>', encoding='utf-8')",
                "        written.append(target)",
                "    index = output_dir / 'index.html'",
                "    index.write_text('<!doctype html><title>index</title>', encoding='utf-8')",
                "    written.append(index)",
                "    return written",
                "",
            ]
        ),
        encoding="utf-8",
    )
    workflow_dir = project_root / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "pages.yml").write_text(
        "\n".join(
            [
                "jobs:",
                "  build:",
                "    steps:",
                "      - uses: actions/configure-pages@v5",
                "      - uses: actions/upload-pages-artifact@v5",
                "  deploy:",
                "    permissions:",
                "      actions: read",
                "      pages: write",
                "      id-token: write",
                "    steps:",
                "      - uses: actions/deploy-pages@v5",
                "",
            ]
        ),
        encoding="utf-8",
    )
    screenshot = project_root / "README" / "screenshots"
    screenshot.mkdir(parents=True, exist_ok=True)
    (screenshot / "main.png").write_bytes(b"png")


def test_validate_store_materials_reports_ok_for_complete_materials(tmp_path: Path) -> None:
    exe_path = tmp_path / "CareCenterForCodex.exe"
    exe_path.write_bytes(b"exe")
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )

    report = validate_store_materials(project_root=tmp_path, exe_path=exe_path)

    assert report.status == "ok"
    pages_build_check = next(check for check in report.checks if check.name == "Store-Webseiten-Build")
    assert pages_build_check.status == "ok"


def test_validate_store_materials_checks_live_pages_on_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    requested_urls: list[str] = []

    def fake_urlopen(request, *, timeout: float):
        requested_urls.append(request.full_url)
        assert timeout == 10.0
        return FakeResponse()

    monkeypatch.setattr(store_release.urlrequest, "urlopen", fake_urlopen)
    exe_path = tmp_path / "CareCenterForCodex.exe"
    exe_path.write_bytes(b"exe")
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.8.0.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )

    report = validate_store_materials(
        project_root=tmp_path,
        exe_path=exe_path,
        check_live_pages=True,
    )

    live_check = next(check for check in report.checks if check.name == "Store-Webseiten-Live")
    assert live_check.status == "ok"
    assert requested_urls == [
        "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
        "https://dev-bricks.github.io/CareCenter-for-Codex/support",
    ]


def test_validate_store_materials_warns_when_live_page_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeResponse:
        def __init__(self, status: int) -> None:
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    def fake_urlopen(request, *, timeout: float):
        del timeout
        status = 404 if request.full_url.endswith("/support") else 200
        return FakeResponse(status)

    monkeypatch.setattr(store_release.urlrequest, "urlopen", fake_urlopen)
    exe_path = tmp_path / "CareCenterForCodex.exe"
    exe_path.write_bytes(b"exe")
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.8.0.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )

    report = validate_store_materials(
        project_root=tmp_path,
        exe_path=exe_path,
        check_live_pages=True,
    )

    live_check = next(check for check in report.checks if check.name == "Store-Webseiten-Live")
    assert live_check.status == "warning"
    assert "support_url: HTTP 404" in live_check.message


def test_validate_store_materials_auto_detects_built_exe_from_build_script(tmp_path: Path) -> None:
    dist_dir = tmp_path / "_local" / "bin"
    dist_dir.mkdir(parents=True)
    exe_path = dist_dir / "CareCenterForCodex.exe"
    exe_path.write_bytes(b"exe")
    (tmp_path / "build_exe.bat").write_text(
        '@echo off\nset "DIST_DIR=' + str(dist_dir) + '"\n',
        encoding="utf-8",
    )
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )

    report = validate_store_materials(project_root=tmp_path)

    assert report.status == "ok"
    executable_check = next(check for check in report.checks if check.name == "Executable")
    assert executable_check.status == "ok"
    assert str(exe_path.resolve()) in executable_check.message


def test_validate_store_materials_accepts_build_directory_for_exe_path(tmp_path: Path) -> None:
    dist_dir = tmp_path / "_local" / "bin"
    dist_dir.mkdir(parents=True)
    exe_path = dist_dir / "CareCenterForCodex.exe"
    exe_path.write_bytes(b"exe")
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )

    report = validate_store_materials(project_root=tmp_path, exe_path=dist_dir)

    assert report.status == "ok"
    executable_check = next(check for check in report.checks if check.name == "Executable")
    assert executable_check.status == "ok"
    assert executable_check.message == str(exe_path.resolve())


def test_validate_store_materials_fails_without_runfulltrust(tmp_path: Path) -> None:
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "internetClient",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )

    report = validate_store_materials(project_root=tmp_path)

    assert report.status == "failed"
    assert any(check.name == "Capabilities" and check.status == "failed" for check in report.checks)


def test_validate_store_materials_warns_for_placeholder_urls(tmp_path: Path) -> None:
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://example.invalid/privacy",
            "support_url": "https://example.com/support",
        },
    )

    report = validate_store_materials(project_root=tmp_path)

    assert report.status == "warning"
    assert any(check.name == "Store-URLs" and check.status == "warning" for check in report.checks)


def test_validate_store_materials_warns_without_published_store_docs(tmp_path: Path) -> None:
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )
    (tmp_path / "docs" / "support.md").unlink()

    report = validate_store_materials(project_root=tmp_path)

    assert report.status == "warning"
    assert any(check.name == "Store-Webseiten" and check.status == "warning" for check in report.checks)


def test_validate_store_materials_warns_without_pages_workflow(tmp_path: Path) -> None:
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )
    (tmp_path / ".github" / "workflows" / "pages.yml").unlink()

    report = validate_store_materials(project_root=tmp_path)

    assert report.status == "warning"
    assert any(
        check.name == "Store-Webseiten" and "Pages-Workflow fehlt" in check.message
        for check in report.checks
    )


def test_validate_store_materials_warns_when_pages_builder_fails(tmp_path: Path) -> None:
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://dev-bricks.github.io/CareCenter-for-Codex/privacy",
            "support_url": "https://dev-bricks.github.io/CareCenter-for-Codex/support",
        },
    )
    (tmp_path / "scripts" / "build_store_pages.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "",
                "def build_pages(project_root: Path, output_dir: Path) -> list[Path]:",
                "    raise RuntimeError('cannot build store pages')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    report = validate_store_materials(project_root=tmp_path)

    assert report.status == "warning"
    assert any(
        check.name == "Store-Webseiten-Build"
        and check.status == "warning"
        and "cannot build store pages" in check.message
        for check in report.checks
    )
