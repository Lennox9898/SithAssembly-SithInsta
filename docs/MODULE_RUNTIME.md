# SithAssembly Module Runtime

Die Projekt-Runtime bleibt `app.py` mit dem lokalen HTTP-Server. `src/assembly_manifest.py` ist die zentrale, maschinenlesbare Registry der vorhandenen Module und Profile.

Die aus der beigefuegten Runtime-Idee uebernommenen Namen werden auf vorhandene Komponenten abgebildet:

- `VantaIndex` entspricht dem lokalen Evidenzregister und `EvidenceIntegrity`.
- `BlackSignal` entspricht der textbasierten Heuristik und `SignalForge` dem separaten Kommentar-Ausreisser-Review.
- `GhostCluster`, `ShadowGraph`, `Traceborne` und `SpectreReport` entsprechen Graph-, Timeline- und Report-Komponenten.
- `SpectreNet.Identity` bleibt ein manuelles Hypothesen- und Review-Modul, keine automatische Personenidentifikation.
- `EvidenceVault` ist aktiv: signierte und verschluesselte lokale Exportpakete mit Manifest.

Nicht implementiert oder aktiviert sind automatische Plattform-Capture, Account-Erstellung, Posting, Direktnachrichten, externe Benachrichtigungen, Gesichts-/Personenidentifikation und pauschale Bot-Feststellungen.

Jede ausgefuehrte Komponente muss Belege, Warnungen und einen Review-Status liefern oder die Verarbeitung auslassen. Ein Score oder eine Modellantwort ist keine Tatsachenbehauptung.
