# WACK-Testprotokoll — CareCenter for Codex

## 1. Stammdaten

| Eigenschaft | Wert |
|---|---|
| **Anwendung** | CareCenter for Codex |
| **Paket-Identität** | `LukasGeiger.CareCenterForCodex` |
| **Publisher** | `CN=52596601-BAB4-4F3F-B182-E8F3F273B202` |
| **Version** | `0.8.0.0` |
| **Architektur** | `x64` |
| **Min. OS-Version** | Windows 10 Build 17763 (1809) |
| **Max. OS getestet** | Windows 11 Build 26100 (24H2) |
| **Lizenz** | MIT |
| **Capabilities** | `runFullTrust` |
| **Execution Alias** | `carecenter.exe` |

---

## 2. Preflight-Ergebnisse (Automatisierter Test)

| Test-Kategorie | Kriterium | Status | Details |
|---|---|---|---|
| **AppxManifest Syntax** | XML-Schema & Namespaces | ✅ PASS | Wohlgeformtes XML, ignorable namespaces `uap rescap desktop` |
| **Paket-Identität** | Publisher & Name | ✅ PASS | Identität `LukasGeiger.CareCenterForCodex` stimmt mit Partner Center überein |
| **Restricted Capabilities** | `runFullTrust` | ✅ PASS | Desktop-Bridge Anwendung, keine unzulässigen Sonder-Capabilities |
| **Tile- & Icon-Assets** | Dimensionen & PNG-Format | ✅ PASS | 44x44, 50x50, 150x150, 310x150, 310x310, StoreLogo 50x50 vollständig |
| **Properties-Logo** | Standard-Kachel | ✅ PASS | Verweist auf `icons\StoreLogo.png` (50x50) |
| **Store Richtlinie 10.1.3** | Suchbegriffe & Marken | ✅ PASS | Exakt 7 Keywords je Sprache, echte deutsche Umlaute, keine Fremdmarken |
| **Binäre Integrität** | PE64 Header & Startfähigkeit | ✅ PASS | Saubere x64 Windows Binärdatei |

---

## 3. Hermetischer WACK-Preflight

- **Runner:** `scripts/run_windows_wack.py`
- **Ergebnis:** 6 PASS / 0 FAIL / 0 WARNING
- **Berichts-Ablage:** `releases/windowsstore/test_reports/`

---

## 4. Offener Schritt

- Lokaler erhöhter WACK-Lauf mit `appcert.exe` via UAC-Launcher oder direkte serverseitige Microsoft Partner Center Zertifizierung.
