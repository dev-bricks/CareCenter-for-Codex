# CareCenter for Codex — Windows Store Packaging & Build Anleitung

## 1. Voraussetzungen

- **Python 3.11+** mit installierten Dependencies aus `requirements.txt`
- **Windows 10/11 x64**
- **Windows SDK** (Build 17763 oder neuer) für `MakeAppx.exe` und `SignTool.exe`
- **Zertifikat (PFX):** Zum lokalen Testen reicht ein selbstsigniertes Zertifikat; für die Einreichung im Partner Center signiert Microsoft das Paket automatisch.

---

## 2. Schritt 1: Python-Executable (EXE) bauen

Der Build erfolgt reproduzierbar über das Projekt-Skript `build_exe.bat`:

```cmd
build_exe.bat
```

Dies erzeugt:
- `dist\CareCenterForCodex.exe` (Stand-alone PyInstaller Executable mit Tray-Unterstützung und Assets)
- Verifiziert den Start und die Signatur

---

## 3. Schritt 2: Store-Materialien & Preflight validieren

Führe den hermetischen Preflight-Auditor aus:

```powershell
python scripts\check_store_readiness.py
```

Erwartetes Ergebnis: **AUDIT PASSED (6/6 Checks OK - Vorbereitung vollständig)**.

---

## 4. Schritt 3: MSIX-Paket erstellen

Das MSIX-Paket wird über das zentrale Pipeline-Werkzeug `_STORE/msstore_build_msix.ps1` oder MakeAppx gebaut:

```powershell
# Variante A: Über zentrales Pipeline-Skript
powershell -ExecutionPolicy Bypass -File "C:\Users\lukas\OneDrive\.TOPICS\.SOFTWARE\_STORE\msstore_build_msix.ps1" `
    -ProjectRoot "C:\_Local_DEV\repos\CareCenter-for-Codex" `
    -ExePath "C:\_Local_DEV\repos\CareCenter-for-Codex\dist\CareCenterForCodex.exe"

# Variante B: MakeAppx direkt
MakeAppx.exe pack /d "C:\_Local_DEV\repos\CareCenter-for-Codex\store_package\CareCenter for Codex" /p "releases\windowsstore\CareCenterForCodex.msix" /nv
```

---

## 5. Schritt 4: WACK-Preflight & Zertifizierungstest

```powershell
python scripts\run_windows_wack.py
```

Erzeugt strukturierte Berichte unter `releases\windowsstore\test_reports\`:
- `wack_preflight_YYYYMMDD.xml`
- `wack_preflight_YYYYMMDD.json`

---

## 6. Schritt 5: Microsoft Partner Center Einreichung

1. Im Partner Center unter **Apps & Spiele** das Produkt **CareCenter for Codex** wählen.
2. Neues Paket `CareCenterForCodex.msix` hochladen.
3. Die 4 Full-HD Screenshots aus `releases\windowsstore\screenshots\` hochladen.
4. Listings DE/EN aus `releases\windowsstore\store_listing_*.md` kopieren.
5. Altersfreigabe (IARC) bestätigen.
6. Einreichen zur Zertifizierung.
