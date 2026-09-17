# Branding- und README-Asset-Vertrag

Stand: 2026-09-17
Scope: lokaler kanonischer Clone von `CareCenter-for-Codex`

## Entscheidung

Die bestehende Struktur bleibt erhalten. Es gibt keinen autorisierten Move oder
Rename:

- `CareCenterForCodex.ico` im Projekt-Root bleibt die autoritative Build- und
  Tray-Quelle. `build_exe.bat` und `src/codex_logdatenbank_wartung/tray.py`
  referenzieren diesen Pfad.
- `CareCenterForCodex.png` im Projekt-Root bleibt als getracktes öffentliches
  Branding-/Kompatibilitätsasset erhalten.
- `store_assets/` bleibt die kanonische Quelle der vier Windows-Store-Logos;
  `AppxManifest.xml`, `store_package.json`, `store_release.py` und die
  Store-Tests bilden den Paketvertrag.
- `README/screenshots/main.png` bleibt der einzige autoritative README-/Store-
  Screenshot. `store_screenshot.py`, `README.md`, `README.de.md` und die
  Screenshot-Tests nutzen genau diesen Pfad.
- `docs/` bleibt für ergänzende Dokumentation reserviert. Der Screenshot wird
  nicht nach `docs/` verschoben.

Damit sind TW-CC-10 (Task 2074) und TW-CC-11 (Task 2075) als Retain-/Pfad-
Entscheidung erledigt. Ein späterer Umbau darf nur nach benannter
Eigentümerfreigabe in einem sauberen lokalen Clone erfolgen.

## Kanonischer Git-Bestand

`git status --short --branch` war sauber: `main...origin/main`, keine lokalen
Änderungen und keine ungetrackten Dateien. Die folgenden Dateien sind getrackt:

| Pfad | SHA-256 | Herkunft/Verbraucher | Scope |
|---|---|---|---|
| `CareCenterForCodex.ico` | `d4722bdd95777afa1d229a64cc3bc58c3b73b13447d345fe5b180a4d7d972f43` | Git-Asset-Update; `build_exe.bat`, Tray | öffentliches Build-/Runtime-Asset |
| `CareCenterForCodex.png` | `bf43d700f8a8b2be8e8d0bbc0c60c83af842ed039ce11594ecf5fde20c853832` | Git-Asset-Update; Root-Branding | öffentliches Branding-Asset |
| `README/screenshots/main.png` | `23d72b26cc43b3c589997484f956dec794edbe5f86d0552b96c3f5b64179a043` | reproduzierbarer Screenshot; `store_screenshot.py`, README-Paar, Tests | öffentlicher README-/Store-Visual |
| `store_assets/Square150x150Logo.png` | `5d267bf4dc89f715a3e4e5a77d6cff5bc7ca76b933ac42ffbec221389e5f45d` | `AppxManifest.xml`/Store-Staging | Store-Paketquelle |
| `store_assets/Square310x310Logo.png` | `e919abc67d77e690cdac34343f94800497be612afb34764e72391bb862cd3062` | `AppxManifest.xml`/Store-Staging | Store-Paketquelle |
| `store_assets/Square44x44Logo.png` | `749b86be7a6a7062dcaa5e59dc3ca0dbec87f814cd97af7cf2a7579e0546fe09` | `AppxManifest.xml`/Store-Staging | Store-Paketquelle |
| `store_assets/Wide310x150Logo.png` | `bf1e16cc6809d11317d200a094b232446cc1d42fc29fe52927755679074e6e79` | `AppxManifest.xml`/Store-Staging | Store-Paketquelle |

Im lokalen Clone existiert kein `assets/icon.png`, kein lokales
`BEFUNDE.md`-Fundstück und keine ungetrackte Branding-Variante. Das ignorierte
`BEFUNDE.md`-Muster ist keine Übernahmeanweisung.

## OneDrive-Projektion — nur Beobachtung

Die separat geprüfte OneDrive-DEV-Projektion ist kein kanonischer Git-Clone.
Der Cloud-Filter `cldflt.sys` meldet hohes Rename-Risiko; ein Projekt-Lock war
nicht vorhanden. Diese Dateien wurden nicht übernommen, verschoben,
überschrieben oder gelöscht:

| Beobachteter Pfad relativ zur Projektion | SHA-256 | Einordnung |
|---|---|---|
| `CareCenterForCodex.ico` | `d4722bdd95777afa1d229a64cc3bc58c3b73b13447d345fe5b180a4d7d972f43` | Hashgleich zum kanonischen Root-ICO, dennoch Projektion |
| `CareCenterForCodex.png` | `bf43d700f8a8b2be8e8d0bbc0c60c83af842ed039ce11594ecf5fde20c853832` | Hashgleich zum kanonischen Root-PNG, dennoch Projektion |
| `DEV_CareCenterforCodex.ico` | `321e7d57301d50c52d36a02e176e0e3b03ef5337cd6009d1b250bdbadc50c615` | abweichende Host-/Namensvariante, nicht autorisiert |
| `REL-PUB_CareCenterforCodex.ico` | `321e7d57301d50c52d36a02e176e0e3b03ef5337cd6009d1b250bdbadc50c615` | abweichende Host-/Namensvariante, nicht autorisiert |
| `DEV_CareCenterforCodex.png`, `REL-PUB_CareCenterforCodex.png` | `bf43d700f8a8b2be8e8d0bbc0c60c83af842ed039ce11594ecf5fde20c853832` | Namensvarianten ohne geklärte Eigentümerschaft |
| `assets/icon.png`, `mobile_icons/icon.png` | `bf43d700f8a8b2be8e8d0bbc0c60c83af842ed039ce11594ecf5fde20c853832` | Projektion-/Mobile-Kopien, nicht kanonischer Build-Verbraucher |
| `README/screenshots/main.png` | `23d72b26cc43b3c589997484f956dec794edbe5f86d0552b96c3f5b64179a043` | Hashgleich zum kanonischen Screenshot, dennoch Projektion |

Der Suchtreffer `CODING/REL-PUB_CareCenterforCodex` ließ sich als Datei nicht
auflösen und wird als stale Such-/Projektionseintrag behandelt. Er ist keine
Quelle.

## Kontrollierter Rückfallplan

Ein späterer Move ist nur nach benannter Freigabe zulässig: zuerst Hash,
ICO-/PNG-Format und Zielpfad in einem sauberen lokalen Clone festschreiben,
dann alle Verbraucher mit `rg` aktualisieren und abschließend
Build-Provenienz, Store-Manifest, Screenshot-Test, README-Link- und Secret-/NUL-
Checks sowie `git status` unabhängig verifizieren. Die OneDrive-Projektion wird
erst nach separater Provenienz- und Lockklärung synchronisiert; sie ist kein
Commit- oder Löschziel.
