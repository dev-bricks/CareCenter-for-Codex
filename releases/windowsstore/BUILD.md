# CareCenter for Codex — Windows Store Packaging & Build Anleitung

## 1. Voraussetzungen

- **Python 3.12+** gemäß `pyproject.toml`; Build-Abhängigkeiten aus `.[build]`
- **Windows 10/11 x64**
- **Windows SDK** (Build 17763 oder neuer) für `MakeAppx.exe` und `SignTool.exe`
- **Zertifikat (PFX):** Zum lokalen Testen reicht ein selbstsigniertes Zertifikat; für die Einreichung im Partner Center signiert Microsoft das Paket automatisch.

---

## 2. Schritt 1: Python-Executable (EXE) bauen

Alle Befehle werden im Repository-Root ausgeführt. `build_exe.bat` ist derzeit
an die Build-Umgebung der Maintainer gebunden: Es verlangt einen externen
`build_exclude_scanner.py`, der nicht mit diesem Repository ausgeliefert wird.
Fehlt dieser Scanner, bricht das Skript ab. Ein frischer Checkout allein reicht
für diesen Buildweg daher noch nicht aus.

In der eingerichteten Build-Umgebung kann das Ausgabeziel explizit gesetzt werden:

```cmd
set "CARECENTER_DIST_DIR=%CD%\dist"
call build_exe.bat
```

Das Skript erzeugt `dist\CareCenterForCodex.exe` mit Tray-Unterstützung und Assets
und schreibt Build-Provenienz. Ohne `CARECENTER_DIST_DIR` verwendet es sein eigenes
voreingestelltes Ausgabeziel. Es führt weder einen Starttest noch eine
Authenticode-Signaturprüfung durch; diese Prüfungen müssen separat erfolgen.

---

## 3. Schritt 2: Store-Materialien & Preflight validieren

Führe den hermetischen Preflight-Auditor aus:

```powershell
python scripts\check_store_readiness.py
```

Erwartetes Ergebnis: **AUDIT PASSED (6/6 Checks OK - Vorbereitung vollständig)**.

---

## 4. Schritt 3: MSIX-Paket erstellen

Das Windows SDK stellt `MakeAppx.exe` bereit. Voraussetzung ist ein vollständig
vorbereitetes Staging-Verzeichnis `store_package\CareCenter for Codex` mit der
geprüften EXE, dem passenden `AppxManifest.xml` und allen referenzierten Assets.
Der EXE-Build kopiert seine Ausgabe nicht automatisch dorthin. Vor dem Packen
Staging und Manifest auf Übereinstimmung mit dem gewünschten Build prüfen.

```powershell
MakeAppx.exe pack /d "store_package\CareCenter for Codex" /p "releases\windowsstore\CareCenterForCodex.msix"
```

---

## 5. Schritt 4: Statischer Preflight und echte WACK-Prüfung

```powershell
python scripts\run_windows_wack.py --preflight-only
```

Erzeugt strukturierte Berichte unter `releases\windowsstore\test_reports\`:
- `wack_preflight_YYYYMMDD.xml`
- `wack_preflight_YYYYMMDD.json`

Dieses Skript prüft statische Store-Materialien. Es startet das Windows App
Certification Kit nicht, auch nicht bei Übergabe von `--msix`. Ein erfolgreicher
Preflight ist daher kein bestandener WACK-Test und keine Store-Zertifizierung.
Das fertige Paket muss separat mit dem installierten Windows App Certification
Kit geprüft werden. Einen dabei erzeugten XML-Bericht kann das Skript mit
`--review-wack-report <Bericht.xml>` auswerten; es führt den Test dabei nicht aus.

---

## 6. Schritt 5: Microsoft Partner Center Einreichung

1. Im Partner Center unter **Apps & Spiele** das Produkt **CareCenter for Codex** wählen.
2. Neues Paket `CareCenterForCodex.msix` hochladen.
3. Die 4 Full-HD Screenshots aus `releases\windowsstore\screenshots\` hochladen.
4. Listings DE/EN aus `releases\windowsstore\store_listing_*.md` kopieren.
5. Altersfreigabe (IARC) bestätigen.
6. Einreichen zur Zertifizierung.
