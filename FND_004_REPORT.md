# Work Package FND-004: Configuration System — Completion Report

## 1. Overview
- **Package ID:** FND-004
- **Title:** Configuration system
- **Status:** COMPLETED
- **Branch:** `feat/fnd-004-configuration-system`
- **Dependencies Verified:** FND-002 (DONE)
- **Architecture References:** `ARCHITECTURE_ZERO.md` §23 (Configuration and secret contract), §19 (Locked decisions D16, D19, D21), §42 (Hash domains).

---

## 2. Architecture & Design Principles

Following the **codebase-design** skill principles, the configuration engine is designed as a **deep module**:
- **Small, Ergonomic Interface:** Callers use `load_config(...)` or `ConfigLoader(workspace_root=...).load(cli_args=...)`, accessing strongly-typed attributes on `TarjomanConfig`. The module hides all multi-tier precedence resolution, environment variable coercion, TOML parsing/serialization, secret detection and masking, unknown-key fail-closed validation, and reproducibility snapshot hashing behind this concise interface.
- **Dependency Inversion & Testability:** `ConfigLoader` accepts explicit inputs (`workspace_root`, `project_config_path`, `user_config_path`, `env`, `cli_args`, `allow_unknown`) rather than binding to global process state or hidden disk lookups. Tests can exercise any combination of tiers in complete isolation without polluting system environment variables or file systems.
- **Layer Law Compliance (D19):** `tarjoman.core.config` sits strictly in the Core domain. It contains no concrete LLM provider, networking, server, or UI dependencies. It relies exclusively on Python standard library modules (`hashlib`, `json`, `os`, `re`, `sys`, `unicodedata`, `pathlib`, `tomllib`) and `pydantic`.
- **Precedence Law (D21):** Configuration precedence strictly adheres to Architecture Zero §23.1 and Decision D21: `CLI > Environment > Project TOML > User Config > Packaged Defaults`.
- **Secret Contract (D16, §23.2):** Secrets (`api_key`, `token`, `password`, `secret`) are prohibited from project TOML, masked in exports/re-serialization by default, redacted in `repr()` and string logs, and excluded from reproducibility snapshot hashes.

---

## 3. Deliverables Implemented

### 3.1 Strongly-Typed Configuration Model (`TarjomanConfig`)
Implemented in `src/tarjoman/core/config.py`:
- Pydantic v2 `BaseModel` with strict field constraints (`extra="forbid"`, `validate_assignment=True`):
  - `workspace_root: Optional[Path] = None`
  - `project_name: str = "default"`
  - `source_language: str = "en"`
  - `target_language: str = "fa"`
  - `domain_profile: str = "literary"`
  - `style_profile: Optional[str] = None`
  - `workflow_profile: Optional[str] = None`
  - `provider: str = "echo"` (default provider is test-only echo)
  - `model: Optional[str] = None`
  - `api_base_url: Optional[str] = None`
  - `api_key: Optional[str] = None` (secret, environment/CLI-only)
  - `timeout_seconds: float = Field(default=60.0, gt=0)`
  - `max_retries: int = Field(default=3, ge=0)`
  - `temperature: float = Field(default=0.3, ge=0.0)`
  - `local_only: bool = False`
  - `typography: Dict[str, Any] = Field(default_factory=dict)` (accepts `TypographicRules` or dict)
  - `extra_settings: Dict[str, Any] = Field(default_factory=dict)`

#### Key Methods on `TarjomanConfig`:
- `to_dict(redacted: bool = True) -> Dict[str, Any]`: Recursively masks `api_key` and any sensitive key matching `_SECRET_KEY_REGEX` to `"[REDACTED]"` when `redacted=True`. Returns raw plaintext secrets only when `redacted=False` is explicitly passed.
- `compute_hash(prefix: bool = True) -> str`: Produces a deterministic SHA-256 digest of the redacted resolved configuration formatted as `sha256:<64 hex chars>` (or raw hex when `prefix=False`). Uses sorted JSON keys and Unicode NFC normalization.
- `to_toml(redacted: bool = True) -> str`: Serializes the configuration to valid, deterministic TOML with tables (`[typography]`, `[extra_settings]`) rendered after top-level scalar values.
- `from_toml(cls, toml_str: str, allow_unknown: bool = False) -> TarjomanConfig`: Classmethod factory to parse and validate a TOML string into `TarjomanConfig`.
- `__repr__()` and `__str__()`: Always display credentials as `[REDACTED]` to eliminate accidental log leakage (§23.2).

### 3.2 Hierarchical Precedence Engine (`ConfigLoader`)

Implements exact 5-tier resolution per Architecture Zero §23.1:
1. **Tier 1 (Highest): Explicit CLI / API Arguments (`cli_args`)**: Non-None CLI flags override all lower layers. Keys with `None` values (representing unset CLI options) do not overwrite lower layers.
2. **Tier 2: Environment Variables (`TARJOMAN_*`)**:
   - Variables prefixed with `TARJOMAN_` are extracted and coerced to appropriate Python types (`float`, `int`, `bool`, `Path`, `str`).
   - Nested tables are supported via double-underscore syntax (e.g. `TARJOMAN_TYPOGRAPHY__STRICT_ZWNJ="false"`) or JSON strings (e.g. `TARJOMAN_TYPOGRAPHY='{"strict_zwnj": false}'`).
   - Unrecognized `TARJOMAN_<KEY>` variables are safely routed to `extra_settings`.
3. **Tier 3: Project Configuration (`tarjoman.toml`)**:
   - Explicitly resolved via `project_config_path` or `workspace_root / "tarjoman.toml"`.
   - **No Hidden CWD Lookup (§23.1):** If neither `project_config_path` nor `workspace_root` is provided, no implicit search in current working directory or parent folders is performed.
   - **Secret Protection (§23.2):** Secrets in project TOML raise `ConfigurationError`.
   - **Fail-Closed Unknown Keys (§23):** Unrecognized keys raise `ConfigurationError` by default.
4. **Tier 4: User Configuration (`~/.config/tarjoman/config.toml` or OS app-data)**:
   - Evaluates `$XDG_CONFIG_HOME/tarjoman/config.toml` (Linux/macOS) or `%APPDATA%/tarjoman/config.toml` (Windows).
   - If user config does not exist on disk, it is silently skipped without error.
5. **Tier 5 (Lowest): Built-in Packaged Defaults**:
   - Sensible baseline defaults matching Architecture Zero specifications.

#### Deep Merging:
Nested dictionary fields (`typography` and `extra_settings`) are recursively merged across tiers so partial overrides at higher tiers do not discard unrelated settings established at lower tiers.

### 3.3 Unknown Config Key Policy (Fail-Closed by Default)
- **Policy Statement:** Any unrecognized top-level configuration key found in a project `tarjoman.toml` file immediately fails closed by raising `ConfigurationError` listing all unknown keys in the error message and details dictionary. This prevents silent misconfigurations caused by typos (e.g. `temperatue = 0.5` or `domian = "legal"`).
- **Extensibility Override:** When `allow_unknown=True` is explicitly supplied to `load_config()`, `ConfigLoader()`, or `TarjomanConfig.from_toml()`, unrecognized keys are captured and placed into `extra_settings`.

### 3.4 Secret Handling & Sanitization Contract (§23.2, D21)
- **Zero Secrets in Project TOML:** Scans all top-level keys and nested sub-tables for keys matching `_SECRET_KEY_REGEX` (e.g. `api_key`, `token`, `password`, `secret`, `credential`). If any secret key is detected in project TOML, `ConfigurationError` is raised immediately.
- **Redacted Export by Default:** `to_dict()` and `to_toml()` redact secret fields to `"[REDACTED]"` by default.
- **Hash Immunity:** `compute_hash()` always hashes the redacted configuration dictionary. Two configurations that differ only by their secret API key yield identical snapshot hashes, guaranteeing that secrets are never leaked into run provenance metadata or hashes.

### 3.5 Module Re-Exports
Exposed and re-exported from `src/tarjoman/core/__init__.py`:
- `TarjomanConfig`
- `ConfigLoader`
- `load_config`
- `dump_toml`
- `parse_env_vars`
- `find_secrets_in_dict`
- `get_default_user_config_path`
- `KNOWN_CONFIG_FIELDS`

---

## 4. Verification & Test Evidence

### 4.1 New Configuration Test Suite (`tests/test_config_system.py`)
A comprehensive suite of 36 unit tests was implemented, covering:
1. **Precedence Matrix Tests (6 tests):**
   - Defaults apply when no overrides exist.
   - User config overrides defaults.
   - Project TOML overrides user config and defaults.
   - Env vars override project TOML, user config, and defaults.
   - CLI args override all other tiers.
   - CLI args with `None` values do not clobber lower-layer values.
2. **Secret Redaction Tests (8 tests):**
   - `to_dict()` masks `api_key` to `"[REDACTED]"` by default.
   - `to_dict(redacted=False)` retains raw secret.
   - Nested secrets in `extra_settings` are masked.
   - Secrets in project `tarjoman.toml` raise `ConfigurationError`.
   - Nested secrets in project TOML subtables raise `ConfigurationError`.
   - `repr()` and `str()` mask credentials.
   - `to_toml()` masks credentials by default.
   - Secrets do not affect `compute_hash()`.
3. **Unknown Config Key Policy Tests (4 tests):**
   - Unknown keys in project TOML fail closed by default with `ConfigurationError`.
   - Unknown keys are preserved in `extra_settings` when `allow_unknown=True`.
   - CLI arguments with unknown keys fail by default and route to `extra_settings` with `allow_unknown=True`.
   - `TarjomanConfig.from_toml()` respects `allow_unknown`.
4. **Reproducibility Snapshot Tests (4 tests):**
   - `compute_hash()` is deterministic across identical configurations.
   - `compute_hash(prefix=False)` returns raw 64-character hex digest.
   - Non-secret field changes produce distinct hashes.
   - Unicode NFC normalization ensures identical hashes for composed/decomposed characters.
5. **No Hidden CWD Lookup Tests (3 tests):**
   - No CWD lookup when `workspace_root=None`.
   - Explicit `workspace_root` resolves `workspace_root / "tarjoman.toml"`.
   - Non-existent explicit `project_config_path` raises `ConfigurationError`.
6. **Environment Variable Parsing Tests (5 tests):**
   - Primitive type coercion (`float`, `int`, `bool`, `Path`, `str`).
   - Invalid numeric strings raise `ConfigurationError`.
   - Nested typography fields (`TARJOMAN_TYPOGRAPHY__<KEY>`).
   - JSON string table parsing (`TARJOMAN_TYPOGRAPHY` and `TARJOMAN_EXTRA_SETTINGS`).
   - Custom keys routed to `extra_settings`.
7. **TOML Serialization & Roundtrip Tests (2 tests):**
   - Roundtrip preservation through `to_toml()` and `from_toml()`.
   - Special character escaping (quotes, newlines, backslashes).
8. **Validation & Field Constraints Tests (4 tests):**
   - `timeout_seconds <= 0` raises `ConfigurationError`.
   - `temperature < 0` raises `ConfigurationError`.
   - `max_retries < 0` raises `ConfigurationError`.
   - `typography` accepts `TypographicRules` contract model or dict.

### 4.2 Full Regression Test Suite
Executed full pytest suite:
```
======================= 266 passed, 9 warnings in 1.42s ========================
```
- 230 existing tests passed with zero regressions.
- 36 new configuration system tests passed.

### 4.3 10-Domain Benchmark Suite
Executed `benchmarks/run_benchmarks.py`:
```
[SUCCESS] All 10 Domain Verification Benchmarks PASSED (10/10) in 0.45s!
```

---

## 5. Acceptance Criteria Checklist

| Acceptance Criterion | Status | Evidence |
|---|:---:|---|
| **Precedence matrix tests** | PASSED | `TestPrecedenceMatrix` (6 tests) asserts CLI > Env > Project TOML > User Config > Defaults. |
| **Secret redaction tests** | PASSED | `TestSecretHandlingAndRedaction` (8 tests) verifies `api_key` redaction in `to_dict`, `to_toml`, `repr`, `compute_hash`, and rejection of secrets in project TOML. |
| **Unknown config key policy documented** | PASSED | Documented in docstrings and this report; verified by `TestUnknownConfigKeyPolicy` (4 tests) fail-closed by default, `allow_unknown=True` support. |
| **Reproducibility snapshot hash** | PASSED | `TestReproducibilitySnapshotHash` (4 tests) asserts SHA-256 determinism, NFC normalization, and format. |
| **All 230 existing tests pass** | PASSED | All 266 tests (230 baseline + 36 new) pass cleanly. |
| **All 10 domain benchmarks pass** | PASSED | 10/10 domain benchmarks passed with 100% MQM audit scores. |

---

## 6. Files Changed
- `src/tarjoman/core/config.py` (New: 789 lines — configuration models, TOML serialization, env parsing, loader engine)
- `src/tarjoman/core/__init__.py` (Modified: added re-exports for config models and utilities)
- `tests/test_config_system.py` (New: 512 lines — 36 comprehensive test cases)
- `WORKPACKAGES.json` (Modified: marked FND-004 DONE, promoted FND-005 to READY)
- `FND_004_REPORT.md` (New: complete verification and architecture report)
