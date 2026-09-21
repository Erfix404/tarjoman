"""
Hierarchical configuration engine and secret contract.

Architecture Zero §23 and §19 (Locked Decisions D16, D19, D21):
- Exact 5-tier precedence: CLI > Environment > Project TOML > User Config > Defaults.
- Secret handling & redaction: secrets (api_key, token, password, secret)
  must never be in project TOML or normal logs/exports.
- Unknown config key policy: project configuration fails closed by default
  on unknown keys unless allow_unknown=True is explicitly set.
- Reproducibility snapshot hash: deterministic SHA-256 digest of the
  redacted resolved configuration.
- No hidden current-working-directory config lookup beyond explicit project file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Union

try:
    import tomllib
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tarjoman.core.errors import ConfigurationError

# ---------------------------------------------------------------------------
# Constants & Regex Patterns
# ---------------------------------------------------------------------------

_SECRET_KEY_REGEX = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|auth(?:orization)?|access[_-]?token|private[_-]?key|credential)"
)

# Known fields on the TarjomanConfig model
KNOWN_CONFIG_FIELDS: Set[str] = {
    "workspace_root",
    "project_name",
    "source_language",
    "target_language",
    "domain_profile",
    "style_profile",
    "workflow_profile",
    "provider",
    "model",
    "api_base_url",
    "api_key",
    "timeout_seconds",
    "max_retries",
    "temperature",
    "local_only",
    "typography",
    "extra_settings",
}

_KNOWN_ENV_FIELDS: Dict[str, type] = {
    "workspace_root": Path,
    "project_name": str,
    "source_language": str,
    "target_language": str,
    "domain_profile": str,
    "style_profile": str,
    "workflow_profile": str,
    "provider": str,
    "model": str,
    "api_base_url": str,
    "api_key": str,
    "timeout_seconds": float,
    "max_retries": int,
    "temperature": float,
    "local_only": bool,
}


# ---------------------------------------------------------------------------
# TOML Serialization & Redaction Helpers
# ---------------------------------------------------------------------------

def _escape_toml_string(s: str) -> str:
    """Escape control characters and quotes for a TOML basic string."""
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _format_toml_value(val: Any) -> str:
    """Format a Python value as a valid TOML literal value."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        s = str(val)
        return s if ("." in s or "e" in s.lower()) else f"{s}.0"
    if isinstance(val, (str, Path)):
        return _escape_toml_string(str(val))
    if isinstance(val, (list, tuple)):
        items = [_format_toml_value(x) for x in val]
        return f"[{', '.join(items)}]"
    raise TypeError(f"Unsupported TOML value type: {type(val)!r} for {val!r}")


def dump_toml(data: Dict[str, Any]) -> str:
    """Serialize a dictionary to a standard-compliant, deterministic TOML string.

    Top-level scalar keys are written first in sorted order, followed by
    tables in sorted order. Nested sub-tables are properly prefixed.
    Keys with `None` values are omitted.
    """
    lines: List[str] = []
    tables: Dict[str, Dict[str, Any]] = {}

    for key, val in sorted(data.items()):
        if val is None:
            continue
        if isinstance(val, dict):
            if val:  # Only render non-empty tables
                tables[key] = val
        else:
            lines.append(f"{key} = {_format_toml_value(val)}")

    def _render_table(name: str, table_data: Dict[str, Any]) -> None:
        sub_tables: Dict[str, Dict[str, Any]] = {}
        table_lines: List[str] = []
        for k, v in sorted(table_data.items()):
            if v is None:
                continue
            if isinstance(v, dict):
                sub_tables[f"{name}.{k}"] = v
            else:
                table_lines.append(f"{k} = {_format_toml_value(v)}")

        if table_lines or not sub_tables:
            lines.append("")
            lines.append(f"[{name}]")
            lines.extend(table_lines)

        for sub_name, sub_dict in sorted(sub_tables.items()):
            _render_table(sub_name, sub_dict)

    for table_name, table_dict in sorted(tables.items()):
        _render_table(table_name, table_dict)

    return "\n".join(lines).strip() + "\n"


def _redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact secrets in a dictionary."""
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if _SECRET_KEY_REGEX.search(k):
            out[k] = "[REDACTED]" if v is not None else None
        elif isinstance(v, dict):
            out[k] = _redact_dict(v)
        elif isinstance(v, list):
            out[k] = [
                _redact_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            out[k] = v
    return out


def find_secrets_in_dict(data: Dict[str, Any], path_prefix: str = "") -> List[str]:
    """Recursively search a dictionary for keys that match sensitive secret patterns."""
    found: List[str] = []
    for k, v in data.items():
        full_key = f"{path_prefix}.{k}" if path_prefix else k
        if _SECRET_KEY_REGEX.search(k):
            found.append(full_key)
        elif isinstance(v, dict):
            found.extend(find_secrets_in_dict(v, full_key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    found.extend(find_secrets_in_dict(item, f"{full_key}[{i}]"))
    return found


def _deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge source into target.

    Values that are None in source are ignored so higher layers do not
    unintentionally unset previously configured values.
    """
    for key, val in source.items():
        if val is None:
            continue
        if isinstance(val, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], val)
        else:
            target[key] = val
    return target


def _parse_primitive(raw_val: str) -> Any:
    """Parse primitive values from strings (used in environment parsing)."""
    val = raw_val.strip()
    lower = val.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in ("null", "none"):
        return None

    try:
        return int(val)
    except ValueError:
        pass

    try:
        return float(val)
    except ValueError:
        pass

    if (val.startswith("{") and val.endswith("}")) or (
        val.startswith("[") and val.endswith("]")
    ):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            pass

    return raw_val


def get_default_user_config_path() -> Path:
    """Return the default path to the user configuration file per OS standards."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "tarjoman" / "config.toml"

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "tarjoman" / "config.toml"
    return Path.home() / ".config" / "tarjoman" / "config.toml"


# ---------------------------------------------------------------------------
# TarjomanConfig Model
# ---------------------------------------------------------------------------

class TarjomanConfig(BaseModel):
    """Immutable resolved configuration contract for Tarjoman runs.

    Encapsulates all runtime configuration parameters specified in
    Architecture Zero §23 and §19.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    workspace_root: Optional[Path] = None
    project_name: str = "default"
    source_language: str = "en"
    target_language: str = "fa"
    domain_profile: str = "literary"
    style_profile: Optional[str] = None
    workflow_profile: Optional[str] = None
    provider: str = "echo"  # default provider is test-only echo
    model: Optional[str] = None
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None  # secret, env-only
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    temperature: float = Field(default=0.3, ge=0.0)
    local_only: bool = False
    typography: Dict[str, Any] = Field(default_factory=dict)
    extra_settings: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("typography", mode="before")
    @classmethod
    def _validate_typography(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, dict):
            return dict(v)
        raise ValueError(f"typography must be a dict or BaseModel, got {type(v)}")

    def to_dict(self, redacted: bool = True) -> Dict[str, Any]:
        """Convert configuration to dictionary, with optional secret redaction.

        Args:
            redacted: If True (default), mask secret fields like `api_key` and
                      any sensitive keys in nested structures (§23.2).

        Returns:
            Dictionary of configuration values.
        """
        raw = self.model_dump()
        if not redacted:
            return raw
        return _redact_dict(raw)

    def compute_hash(self, prefix: bool = True) -> str:
        """Compute deterministic SHA-256 snapshot hash for run provenance.

        Architecture Zero §23.3:
          "Each run stores a redacted resolved-config snapshot hash"

        The hash uses canonical NFC-normalized JSON with sorted keys of the
        redacted configuration, ensuring reproducibility without leaking secrets.

        Args:
            prefix: If True (default), prepend 'sha256:' per Architecture
                    Zero canonical hash convention (§42).

        Returns:
            Canonical hash string (e.g. 'sha256:<64 hex chars>').
        """
        redacted = self.to_dict(redacted=True)
        serialized = json.dumps(
            redacted,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            ensure_ascii=False,
        )
        normalized = unicodedata.normalize("NFC", serialized)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"sha256:{digest}" if prefix else digest

    def to_toml(self, redacted: bool = True) -> str:
        """Serialize configuration to a TOML string.

        Args:
            redacted: If True (default), redact secret fields (§23.2).

        Returns:
            TOML-formatted string.
        """
        data = self.to_dict(redacted=redacted)
        return dump_toml(data)

    @classmethod
    def from_toml(cls, toml_str: str, allow_unknown: bool = False) -> TarjomanConfig:
        """Parse configuration from a raw TOML string."""
        if tomllib is None:  # pragma: no cover
            raise ConfigurationError(
                "TOML parser unavailable. Ensure tomllib (Python 3.11+) or tomli is installed."
            )
        try:
            raw_data = tomllib.loads(toml_str)
        except Exception as e:
            raise ConfigurationError(f"Failed to parse TOML configuration: {e}") from e

        secrets = find_secrets_in_dict(raw_data)
        if secrets:
            raise ConfigurationError(
                f"Secret key(s) {secrets} detected in configuration TOML. "
                "Secrets must never be stored in TOML; use environment variables instead (§23.2).",
                details={"forbidden_keys": sorted(secrets)},
            )

        unknown_keys = set(raw_data.keys()) - KNOWN_CONFIG_FIELDS
        if unknown_keys:
            if not allow_unknown:
                raise ConfigurationError(
                    f"Unknown configuration key(s): {sorted(unknown_keys)}. "
                    "Fail-closed policy requires known keys or allow_unknown=True.",
                    details={"unknown_keys": sorted(unknown_keys)},
                )
            if "extra_settings" not in raw_data:
                raw_data["extra_settings"] = {}
            for k in unknown_keys:
                raw_data["extra_settings"][k] = raw_data.pop(k)

        try:
            return cls(**raw_data)
        except ValidationError as e:
            raise ConfigurationError(
                f"Configuration validation failed: {e}",
                details={"validation_errors": e.errors()},
            ) from e

    def __repr__(self) -> str:
        """Masked representation to prevent leaking credentials into logs (§23.2)."""
        redacted = self.to_dict(redacted=True)
        pairs = ", ".join(f"{k}={v!r}" for k, v in redacted.items())
        return f"TarjomanConfig({pairs})"

    def __str__(self) -> str:
        return self.__repr__()


# ---------------------------------------------------------------------------
# Environment Variable Parsing
# ---------------------------------------------------------------------------

def parse_env_vars(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Parse environment variables prefixed with `TARJOMAN_`.

    Supports primitive typing, nested fields via `__` separator
    (e.g. `TARJOMAN_TYPOGRAPHY__STRICT_ZWNJ=false`), and JSON strings for
    table values.
    """
    if env is None:
        env = os.environ

    result: Dict[str, Any] = {}
    prefix = "TARJOMAN_"

    for raw_key, raw_val in env.items():
        if not raw_key.startswith(prefix):
            continue

        remainder = raw_key[len(prefix):]
        if not remainder:
            continue

        # Handle nested sections, e.g., TARJOMAN_TYPOGRAPHY__STRICT_ZWNJ
        if "__" in remainder:
            section, sub_key = remainder.split("__", 1)
            section = section.lower()
            sub_key = sub_key.lower()
            val = _parse_primitive(raw_val)
            if section not in result:
                result[section] = {}
            if isinstance(result[section], dict):
                result[section][sub_key] = val
            continue

        field_name = remainder.lower()
        if field_name in _KNOWN_ENV_FIELDS:
            target_type = _KNOWN_ENV_FIELDS[field_name]
            try:
                if target_type is bool:
                    result[field_name] = raw_val.strip().lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )
                elif target_type is float:
                    result[field_name] = float(raw_val)
                elif target_type is int:
                    result[field_name] = int(raw_val)
                elif target_type is Path:
                    result[field_name] = Path(raw_val)
                else:
                    result[field_name] = str(raw_val)
            except (ValueError, TypeError) as e:
                raise ConfigurationError(
                    f"Invalid value for environment variable {raw_key}: '{raw_val}' could not be parsed as {target_type.__name__}.",
                    details={
                        "env_var": raw_key,
                        "value": raw_val,
                        "expected_type": target_type.__name__,
                    },
                ) from e
        elif field_name in ("typography", "extra_settings"):
            val = raw_val.strip()
            if val.startswith("{"):
                try:
                    parsed_json = json.loads(val)
                    if isinstance(parsed_json, dict):
                        result[field_name] = parsed_json
                    else:
                        raise ValueError("Must be a JSON object")
                except Exception as e:
                    raise ConfigurationError(
                        f"Environment variable {raw_key} must be valid JSON object: {e}",
                        details={"env_var": raw_key, "value": raw_val},
                    ) from e
            else:
                raise ConfigurationError(
                    f"Environment variable {raw_key} for table '{field_name}' must be a JSON string starting with '{{'.",
                    details={"env_var": raw_key},
                )
        else:
            # Unrecognized TARJOMAN_<KEY> -> place in extra_settings
            if "extra_settings" not in result:
                result["extra_settings"] = {}
            result["extra_settings"][field_name] = _parse_primitive(raw_val)

    return result


# ---------------------------------------------------------------------------
# Hierarchical Config Loader
# ---------------------------------------------------------------------------

class ConfigLoader:
    """Multi-tier configuration loader implementing Architecture Zero §23 and §19 (D21).

    Precedence (highest to lowest):
      1. Explicit CLI / API arguments (`cli_args`)
      2. Environment variables (`TARJOMAN_*`)
      3. Project configuration (`tarjoman.toml` in workspace/project directory)
      4. User configuration (`~/.config/tarjoman/config.toml` or OS app-data)
      5. Packaged defaults

    Security & Validation policies:
      - Secrets (`api_key`, `token`, `password`, `secret`) MUST NOT be present in
        project `tarjoman.toml`. If found, a `ConfigurationError` is raised (§23.2).
      - Unknown keys in project `tarjoman.toml` fail by default (fail-closed, §23).
        Pass `allow_unknown=True` to permit extra keys into `extra_settings`.
      - No hidden current-working-directory config lookup beyond explicit project
        directory or file (§23.1).
    """

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        project_config_path: Optional[Union[str, Path]] = None,
        user_config_path: Optional[Union[str, Path]] = None,
        env: Optional[Mapping[str, str]] = None,
        allow_unknown: bool = False,
    ) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.project_config_path = (
            Path(project_config_path) if project_config_path else None
        )
        self.user_config_path = (
            Path(user_config_path) if user_config_path else None
        )
        self.env = env
        self.allow_unknown = allow_unknown

    def _get_defaults(self) -> Dict[str, Any]:
        """Tier 5: Built-in packaged defaults."""
        return {
            "workspace_root": self.workspace_root,
            "project_name": "default",
            "source_language": "en",
            "target_language": "fa",
            "domain_profile": "literary",
            "style_profile": None,
            "workflow_profile": None,
            "provider": "echo",
            "model": None,
            "api_base_url": None,
            "api_key": None,
            "timeout_seconds": 60.0,
            "max_retries": 3,
            "temperature": 0.3,
            "local_only": False,
            "typography": {},
            "extra_settings": {},
        }

    def _load_user_config(self) -> Dict[str, Any]:
        """Tier 4: User configuration under OS application directory."""
        if self.user_config_path is not None:
            path = self.user_config_path
        else:
            path = get_default_user_config_path()

        if not path.exists():
            return {}

        if tomllib is None:  # pragma: no cover
            raise ConfigurationError(
                "TOML parser unavailable. Ensure tomllib (Python 3.11+) or tomli is installed."
            )

        try:
            raw_text = path.read_text(encoding="utf-8")
            data = tomllib.loads(raw_text)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to parse user configuration file {path}: {e}",
                details={"path": str(path)},
            ) from e

        # Unknown keys in user config are routed into extra_settings
        unknown_keys = set(data.keys()) - KNOWN_CONFIG_FIELDS
        if unknown_keys:
            if "extra_settings" not in data:
                data["extra_settings"] = {}
            for k in unknown_keys:
                data["extra_settings"][k] = data.pop(k)

        return data

    def _resolve_project_config_path(self) -> Optional[Path]:
        """Determine explicit project configuration file path.

        Enforces Architecture Zero §23.1:
          "No hidden current-working-directory config lookup beyond the explicit project file."
        """
        if self.project_config_path is not None:
            if not self.project_config_path.exists():
                raise ConfigurationError(
                    f"Specified project configuration file not found: {self.project_config_path}",
                    details={"path": str(self.project_config_path)},
                )
            return self.project_config_path

        if self.workspace_root is not None:
            candidate = self.workspace_root / "tarjoman.toml"
            if candidate.is_file():
                return candidate
            return None

        # Neither project_config_path nor workspace_root was provided:
        # Do not perform implicit cwd lookup!
        return None

    def _load_project_config(self, allow_unknown: bool) -> Dict[str, Any]:
        """Tier 3: Project `tarjoman.toml` in workspace/project directory."""
        path = self._resolve_project_config_path()
        if path is None:
            return {}

        if tomllib is None:  # pragma: no cover
            raise ConfigurationError(
                "TOML parser unavailable. Ensure tomllib (Python 3.11+) or tomli is installed."
            )

        try:
            raw_text = path.read_text(encoding="utf-8")
            data = tomllib.loads(raw_text)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to parse project configuration file {path}: {e}",
                details={"path": str(path)},
            ) from e

        # Architecture Zero §23.2: Secrets MUST NOT be present in project TOML
        secrets = find_secrets_in_dict(data)
        if secrets:
            raise ConfigurationError(
                f"Secret key(s) {sorted(secrets)} found in project configuration file {path}. "
                "Secrets must be provided via environment variables (e.g. TARJOMAN_API_KEY) "
                "or an external secret store, never in project TOML (Architecture Zero §23.2, D21).",
                details={"forbidden_keys": sorted(secrets), "path": str(path)},
            )

        # Architecture Zero §23: Unknown config keys fail closed by default
        unknown_keys = set(data.keys()) - KNOWN_CONFIG_FIELDS
        if unknown_keys:
            if not allow_unknown:
                raise ConfigurationError(
                    f"Unknown configuration key(s) in project config file '{path}': {sorted(unknown_keys)}. "
                    "By default, project configuration fails closed on unrecognized keys to prevent typos. "
                    "Set allow_unknown=True or use the [extra_settings] table for custom extensions.",
                    details={"unknown_keys": sorted(unknown_keys), "path": str(path)},
                )
            if "extra_settings" not in data:
                data["extra_settings"] = {}
            for k in unknown_keys:
                data["extra_settings"][k] = data.pop(k)

        return data

    def load(
        self,
        cli_args: Optional[Dict[str, Any]] = None,
        allow_unknown: Optional[bool] = None,
    ) -> TarjomanConfig:
        """Resolve and return configuration applying strict 5-tier precedence.

        Precedence:
          1. cli_args (highest)
          2. env_vars
          3. project_toml
          4. user_config
          5. defaults (lowest)

        Args:
            cli_args: Optional explicit dictionary of CLI flags/arguments.
            allow_unknown: Override default unknown keys policy.

        Returns:
            Validated TarjomanConfig instance.
        """
        effective_allow_unknown = (
            self.allow_unknown if allow_unknown is None else allow_unknown
        )

        # Tier 5: Defaults
        merged = self._get_defaults()

        # Tier 4: User Config
        user_data = self._load_user_config()
        if user_data:
            _deep_merge(merged, user_data)

        # Tier 3: Project TOML
        project_data = self._load_project_config(allow_unknown=effective_allow_unknown)
        if project_data:
            _deep_merge(merged, project_data)

        # Tier 2: Environment Variables
        env_data = parse_env_vars(self.env)
        if env_data:
            _deep_merge(merged, env_data)

        # Tier 1: CLI Arguments
        if cli_args:
            cli_clean = {}
            for k, v in cli_args.items():
                if v is not None:
                    cli_clean[k] = v

            # Check unknown keys in CLI args
            unknown_cli = set(cli_clean.keys()) - KNOWN_CONFIG_FIELDS
            if unknown_cli:
                if not effective_allow_unknown:
                    raise ConfigurationError(
                        f"Unknown CLI argument(s): {sorted(unknown_cli)}.",
                        details={"unknown_keys": sorted(unknown_cli)},
                    )
                if "extra_settings" not in cli_clean:
                    cli_clean["extra_settings"] = {}
                for k in unknown_cli:
                    cli_clean["extra_settings"][k] = cli_clean.pop(k)

            _deep_merge(merged, cli_clean)

        try:
            return TarjomanConfig(**merged)
        except ValidationError as e:
            raise ConfigurationError(
                f"Configuration validation failed: {e}",
                details={"validation_errors": e.errors()},
            ) from e


# ---------------------------------------------------------------------------
# Module-level Convenience Helper
# ---------------------------------------------------------------------------

def load_config(
    workspace_root: Optional[Union[str, Path]] = None,
    project_config_path: Optional[Union[str, Path]] = None,
    user_config_path: Optional[Union[str, Path]] = None,
    cli_args: Optional[Dict[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
    allow_unknown: bool = False,
) -> TarjomanConfig:
    """Convenience function to load and resolve hierarchical Tarjoman configuration.

    Args:
        workspace_root: Directory containing project `tarjoman.toml` (and project files).
        project_config_path: Explicit path to project configuration TOML file.
        user_config_path: Explicit path to user configuration file.
        cli_args: Dictionary of command-line invocation arguments.
        env: Environment variable mapping (defaults to `os.environ`).
        allow_unknown: Whether to permit unrecognized keys in project configuration.

    Returns:
        Resolved and validated TarjomanConfig.
    """
    loader = ConfigLoader(
        workspace_root=workspace_root,
        project_config_path=project_config_path,
        user_config_path=user_config_path,
        env=env,
        allow_unknown=allow_unknown,
    )
    return loader.load(cli_args=cli_args)


__all__ = [
    "KNOWN_CONFIG_FIELDS",
    "TarjomanConfig",
    "ConfigLoader",
    "load_config",
    "dump_toml",
    "parse_env_vars",
    "find_secrets_in_dict",
    "get_default_user_config_path",
]
