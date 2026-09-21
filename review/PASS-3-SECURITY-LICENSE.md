# Pass 3 — Security, privacy, license, and supply chain

## Findings closed

- **R17 Critical — `local_only` only constrained model providers, not all egress.**  
  Fixed: central NetworkPolicy/NetworkGate covers models, OCR, fonts/CDNs, downloads, telemetry, ASR/TTS, and fetchers.

- **R18 Critical — custom provider base URL could become SSRF in remote server mode.**  
  Fixed: endpoint changes are trusted configuration/admin operations; untrusted jobs cannot provide arbitrary URLs; allowlist controls available.

- **R19 Critical — upload/parser boundary lacked byte/decompression/path rules.**  
  Fixed: pre-read limits, quotas, MIME/decoder checks, traversal/symlink/archive-bomb controls and storage outside webroot.

- **R20 Major — external binaries had no execution contract.**  
  Fixed: argv-only, no shell, timeout/cancel, controlled directories, bounded logs.

- **R21 Major — encryption-at-rest expectation was ambiguous.**  
  Fixed: no false claim; v1 relies on OS/disk encryption for sensitive deployments. App-level encrypted workspace needs ADR.

- **R22 Major — “production = commercial” license gate was too coarse.**  
  Fixed: deployment purpose (commercial/noncommercial/research) × distribution mode (bundled/user-supplied/remote service).

- **R23 Major — model downloads/remote code could happen implicitly.**  
  Fixed: explicit acquisition, pinned revision/hash/manifest, remote custom code disabled by default.

- **R24 Critical — network server auth model was unspecified.**  
  Fixed: v1 single-tenant workspace + scoped high-entropy API principals; loopback default; remote production behind TLS/auth.

- **R25 Major — third-party plugin loading could bypass policy.**  
  Fixed: no arbitrary plugin auto-discovery in v1; public plugin ABI deferred to security ADR.

## Evidence
Reviewed official OWASP file-upload/SSRF guidance and SQLite backup/WAL constraints; URLs are recorded in `research/source-register.md`.
