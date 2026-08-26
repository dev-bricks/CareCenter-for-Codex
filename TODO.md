# TODO

- [x] T-20260826-623771387: Empty-Thread-Autofix gegen frische Initialisierung,
  aktive npm-Codex-CLI und den Prozess-TOCTOU vor Backup/Move härten; mit einem
  promptfreien, source-attribuierten `startup-receipt` regressionssichern.
- [x] Den verifizierten Commit über den getrennten lokalen Deploymentweg in die
  laufende CareCenter-Installation übernehmen und erst nach eigenem Live-Readback
  aktivieren. Erledigt am 2026-08-26: Projektion mit Vorher-Sicherung aktualisiert,
  Tray kontrolliert neu gestartet und drei Start/Resume-Zyklen über mehrere
  Watcher-Takte mit `archived=0` zurückgelesen. Das vollständige Receipt liegt im
  eigenen `.SYNC/laptop`-Slot unter `T-20260826-623771387-thread-store-provenance`.
