# CareCenter Health Exchange Contract v1

Status: normative contract; no transport or publisher runtime is implemented by
this change.

Schema:
[`docs/contracts/carecenter-health-exchange-v1.schema.json`](docs/contracts/carecenter-health-exchange-v1.schema.json)

## Purpose and direction

The contract exposes a privacy-minimized health snapshot in exactly one
direction:

```text
CareCenter for Codex -> BACH/OCEAN
```

CareCenter remains the authority for the local diagnostic observation. BACH or
OCEAN may display, route, or schedule follow-up work from an accepted snapshot,
but the snapshot does not transfer maintenance authority. Version 1 has no
inbound command, acknowledgement, repair, process-control, configuration, or
thread-mutation message.

The schema defines a data boundary only. It does not enable networking, cloud
sync, telemetry, or a second data canon. A later adapter and transport require
their own implementation, threat review, authentication, and deployment gate.

## Snapshot fields

| Field | Meaning |
| --- | --- |
| `schema` | Fixed routing discriminator `carecenter-health-exchange-v1`. |
| `contract_version` | Fixed semantic contract version `1.0.0`. |
| `publisher_component` | Fixed source component `carecenter-for-codex`. |
| `publisher_instance` | Persistent random UUIDv4 generated with the OS CSPRNG; never derived from host, user, path, or device data. |
| `publisher_epoch` | Random UUIDv4 bound to the durable checkpoint state. |
| `generated_at` | Strict RFC 3339 UTC time when the adapter closed the complete snapshot. |
| `source_checkpoint` | Monotonic integer scoped to the publisher-instance/epoch pair. |
| `overall_status` | `ok`, `warn`, `critical`, or `unknown`. |
| `issues` | Object keyed by unique neutral finding code; each value contains only severity and fixability. |

The schema binds each source code to its fixed severity/fixability and derives a
consistent status shape: `ok` has no issues, `warn` has warning issues only,
`critical` contains at least one critical issue, and `unknown` contains exactly
`diagnostic_unavailable`. That issue is adapter-generated when a complete
diagnostic snapshot cannot be produced; a partially populated health report
must not be published as complete.

## Source-to-public issue mapping

The source mapping is duplicated in the schema as `x-source-code-map` so a
contract test can detect drift in `health.py`.

| CareCenter source code | Public exchange code |
| --- | --- |
| `zombie-prozess` | `codex_start_blocked` |
| `verwaistes-lockfile` | `codex_start_blocked` |
| `db-fehlt` | `database_missing` |
| `wal-aufblaehung` | `database_wal_large` |
| `db-aufblaehung` | `database_large` |
| `wenig-speicher` | `disk_space_low` |
| `badstate` | `database_badstate_present` |
| `codex-exe-fehlt` | `codex_install_missing` |
| `update-reste` | `update_leftovers_present` |
| `verschachtelte-automation` | `automation_nesting_detected` |
| `automation-id-duplikat` | `automation_id_duplicate` |

The issue object key makes duplicate public codes impossible. If multiple source
findings map to one public code, the adapter uses the highest severity and marks
`fixable` true only when every contributing finding is fixable. It emits no
source message or source code.

## Replacement, ordering, and freshness

Each accepted payload is a complete replacement snapshot, not a patch or event
history. An issue omitted from a newer accepted snapshot is cleared; version 1
therefore has no tombstones.

A consumer keeps the highest accepted `source_checkpoint` per registered
`publisher_instance`/`publisher_epoch` pair and rejects a checkpoint less than
or equal to that value. `publisher_instance` is generated once with the
operating-system CSPRNG and persisted independently of names or device data.
`publisher_epoch` is generated with checkpoint zero and remains bound to that
durable counter state. Loss or reset of either identity or checkpoint state
requires a separately authenticated and authorized re-enrollment; a consumer
rejects an unknown or rotated pair by default. Rotation never silently bypasses
the prior ordering state.

Consumers must perform strict RFC 3339 parsing, including calendar validity,
instead of relying on the JSON Schema `format` annotation alone. They reject a
snapshot older than 900 seconds or more than 300 seconds in the future relative
to their authenticated receive time. Clock failure therefore yields stale or
unknown state, never a healthy inference. A publisher advances the checkpoint
only after a complete snapshot has been closed for publication.

## Privacy boundary

The exchange deliberately excludes all raw or identifying diagnostic data,
including:

- file-system paths, file names, host names, and user names;
- process IDs, command lines, automation IDs, and configuration values;
- database, WAL, or disk sizes and threshold values;
- raw messages, logs, backups, prompts, responses, thread, session, or message
  content;
- credentials, tokens, secrets, and environment values.

Consumers receive only coarse health state. `publisher_instance` and
`publisher_epoch` are random protocol identifiers, not labels; adapters must
never derive them from or display them as a machine or person identity.

## Trust boundary

JSON Schema validation establishes payload shape, not authenticity,
authorization, confidentiality, freshness, or delivery. A future transport must
mutually authenticate both publisher and recipient, authorize the recipient for
this exact schema, use an explicit endpoint allowlist, protect integrity and
confidentiality, prevent replay in addition to the checkpoint rule, and fail
closed when peer identity, authorization, time, or ordering cannot be
established.

## Deutsche Zusammenfassung

Der Vertrag überträgt ausschließlich einen datensparsamen, vollständigen
Gesundheits-Schnappschuss von CareCenter an BACH/OCEAN. Er überträgt keine
Reparatur-, Prozess-, Konfigurations- oder Löschbefugnis. Pfade, Prozess-IDs,
Host- und Benutzernamen, Rohmeldungen, Größenangaben, Inhalte und Zugangsdaten
bleiben lokal. Jeder neue akzeptierte Schnappschuss ersetzt den vorherigen
vollständig; dadurch sind keine Löschmarker nötig. Schema-Validierung ersetzt
weder Transportverschlüsselung noch gegenseitige Authentisierung oder Schutz
vor Wiederholung. Zufällige Instanz- und Epochen-UUIDs binden den fortlaufenden
Checkpoint; unbekannte oder zurückgesetzte Identitäten werden nicht automatisch
angenommen. Schnappschüsse veralten nach 900 Sekunden und dürfen höchstens 300
Sekunden in der Zukunft liegen.

## Acceptance boundary

Version 1 is accepted only when:

1. the payload validates against the canonical schema;
2. every current `HealthReport` issue code has an explicit neutral mapping;
3. the privacy exclusions remain absent from schema properties;
4. ordering, epoch registration, strict time parsing, finite freshness, and
   complete-replacement behavior are enforced by the consumer;
5. no inbound command or automatic repair path is introduced under this
   contract.
