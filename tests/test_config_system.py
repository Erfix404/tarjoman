"""
Comprehensive tests for Tarjoman Configuration System (FND-004).

Covers Architecture Zero §23 and §19 (D16, D19, D21):
1. Precedence Matrix Tests (CLI > Env > Project TOML > User Config > Defaults)
2. Secret Redaction Tests (api_key, nested secrets, project TOML rejection)
3. Unknown Config Key Policy Tests (fail closed by default for project config)
4. Reproducibility Snapshot Hash Tests (SHA-256 deterministic snapshot)
5. No Hidden CWD Config Lookup Tests (§23.1)
6. Environment Variable Parsing & Type Coercion Tests
7. Serialization & TOML Roundtrip Tests
8. Validation & Error Handling Tests
"""
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from tarjoman.core.config import (
    KNOWN_CONFIG_FIELDS,
    ConfigLoader,
    TarjomanConfig,
    dump_toml,
    find_secrets_in_dict,
    get_default_user_config_path,
    load_config,
    parse_env_vars,
)
from tarjoman.core.contracts import TypographicRules
from tarjoman.core.errors import ConfigurationError


class TestPrecedenceMatrix(unittest.TestCase):
    """Verify strict 5-tier precedence: CLI > Env > Project TOML > User Config > Defaults."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

        # Create user config file
        self.user_cfg_path = self.workspace / "user_config.toml"
        self.user_cfg_path.write_text(
            """
project_name = "user_project"
domain_profile = "scientific"
timeout_seconds = 45.0
provider = "user_provider"
[typography]
strict_zwnj = false
[extra_settings]
tier = "user"
shared_key = "user_val"
""",
            encoding="utf-8",
        )

        # Create project config file
        self.project_cfg_path = self.workspace / "tarjoman.toml"
        self.project_cfg_path.write_text(
            """
project_name = "project_toml"
domain_profile = "legal"
timeout_seconds = 30.0
[typography]
western_digits = true
[extra_settings]
tier = "project"
shared_key = "project_val"
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_precedence_defaults_apply_when_no_overrides(self) -> None:
        """Tier 5: When no overrides exist, packaged defaults are returned."""
        empty_dir = self.workspace / "empty_dir"
        empty_dir.mkdir()
        non_existent_user = self.workspace / "non_existent_user.toml"

        cfg = load_config(
            workspace_root=empty_dir,
            user_config_path=non_existent_user,
            env={},
            cli_args={},
        )

        self.assertEqual(cfg.project_name, "default")
        self.assertEqual(cfg.source_language, "en")
        self.assertEqual(cfg.target_language, "fa")
        self.assertEqual(cfg.domain_profile, "literary")
        self.assertEqual(cfg.provider, "echo")
        self.assertIsNone(cfg.model)
        self.assertIsNone(cfg.api_key)
        self.assertEqual(cfg.timeout_seconds, 60.0)
        self.assertEqual(cfg.max_retries, 3)
        self.assertEqual(cfg.temperature, 0.3)
        self.assertFalse(cfg.local_only)
        self.assertEqual(cfg.typography, {})
        self.assertEqual(cfg.extra_settings, {})

    def test_precedence_user_config_overrides_defaults(self) -> None:
        """Tier 4: User config overrides defaults when no project/env/cli specified."""
        empty_project_dir = self.workspace / "empty_proj"
        empty_project_dir.mkdir()

        cfg = load_config(
            workspace_root=empty_project_dir,
            user_config_path=self.user_cfg_path,
            env={},
            cli_args={},
        )

        # Overridden by user config
        self.assertEqual(cfg.project_name, "user_project")
        self.assertEqual(cfg.domain_profile, "scientific")
        self.assertEqual(cfg.timeout_seconds, 45.0)
        self.assertEqual(cfg.provider, "user_provider")
        self.assertEqual(cfg.typography.get("strict_zwnj"), False)
        self.assertEqual(cfg.extra_settings.get("tier"), "user")

        # Fallback to defaults
        self.assertEqual(cfg.source_language, "en")
        self.assertEqual(cfg.temperature, 0.3)

    def test_precedence_project_toml_overrides_user_and_defaults(self) -> None:
        """Tier 3: Project TOML overrides user config and defaults."""
        cfg = load_config(
            workspace_root=self.workspace,
            user_config_path=self.user_cfg_path,
            env={},
            cli_args={},
        )

        # Overridden by project TOML
        self.assertEqual(cfg.project_name, "project_toml")
        self.assertEqual(cfg.domain_profile, "legal")
        self.assertEqual(cfg.timeout_seconds, 30.0)
        self.assertEqual(cfg.extra_settings.get("shared_key"), "project_val")
        self.assertEqual(cfg.extra_settings.get("tier"), "project")

        # Inherited from user config (project TOML didn't specify provider)
        self.assertEqual(cfg.provider, "user_provider")

        # Deep merged typography: user specified strict_zwnj, project specified western_digits
        self.assertEqual(cfg.typography.get("strict_zwnj"), False)
        self.assertEqual(cfg.typography.get("western_digits"), True)

        # Inherited from defaults
        self.assertEqual(cfg.source_language, "en")

    def test_precedence_env_overrides_project_user_and_defaults(self) -> None:
        """Tier 2: Environment variables override project TOML, user config, and defaults."""
        env = {
            "TARJOMAN_TIMEOUT_SECONDS": "20.0",
            "TARJOMAN_DOMAIN_PROFILE": "philosophical",
            "TARJOMAN_MODEL": "gpt-4o",
            "TARJOMAN_TYPOGRAPHY__STRICT_ZWNJ": "true",
            "TARJOMAN_EXTRA_SETTINGS__SHARED_KEY": "env_val",
        }

        cfg = load_config(
            workspace_root=self.workspace,
            user_config_path=self.user_cfg_path,
            env=env,
            cli_args={},
        )

        # Overridden by Env
        self.assertEqual(cfg.timeout_seconds, 20.0)
        self.assertEqual(cfg.domain_profile, "philosophical")
        self.assertEqual(cfg.model, "gpt-4o")
        self.assertEqual(cfg.typography.get("strict_zwnj"), True)
        self.assertEqual(cfg.extra_settings.get("shared_key"), "env_val")

        # Retained from project TOML
        self.assertEqual(cfg.project_name, "project_toml")
        self.assertEqual(cfg.typography.get("western_digits"), True)

        # Retained from user config
        self.assertEqual(cfg.provider, "user_provider")

    def test_precedence_cli_overrides_all(self) -> None:
        """Tier 1: Explicit CLI arguments override Env, Project TOML, User config, and Defaults."""
        env = {
            "TARJOMAN_TIMEOUT_SECONDS": "20.0",
            "TARJOMAN_DOMAIN_PROFILE": "philosophical",
            "TARJOMAN_MODEL": "gpt-4o",
        }
        cli = {
            "timeout_seconds": 10.0,
            "domain_profile": "medical",
            "model": "claude-3-5-sonnet",
            "local_only": True,
            "typography": {"em_dash_policy": "eradicate"},
            "extra_settings": {"shared_key": "cli_val"},
        }

        cfg = load_config(
            workspace_root=self.workspace,
            user_config_path=self.user_cfg_path,
            env=env,
            cli_args=cli,
        )

        # CLI wins over everything
        self.assertEqual(cfg.timeout_seconds, 10.0)
        self.assertEqual(cfg.domain_profile, "medical")
        self.assertEqual(cfg.model, "claude-3-5-sonnet")
        self.assertTrue(cfg.local_only)
        self.assertEqual(cfg.extra_settings.get("shared_key"), "cli_val")

        # Deep merged typography preserves lower layers when not conflicting
        self.assertEqual(cfg.typography.get("em_dash_policy"), "eradicate")
        self.assertEqual(cfg.typography.get("western_digits"), True)
        self.assertEqual(cfg.typography.get("strict_zwnj"), False)

    def test_precedence_cli_none_values_do_not_clobber(self) -> None:
        """CLI arguments with value None (unset CLI flags) do not overwrite lower layers."""
        cli = {
            "timeout_seconds": None,  # Not provided on CLI
            "domain_profile": "media",
        }

        cfg = load_config(
            workspace_root=self.workspace,
            user_config_path=self.user_cfg_path,
            env={},
            cli_args=cli,
        )

        # domain_profile was set in CLI -> overrides project toml ('legal')
        self.assertEqual(cfg.domain_profile, "media")
        # timeout_seconds was None in CLI -> preserved from project toml (30.0)
        self.assertEqual(cfg.timeout_seconds, 30.0)


class TestSecretHandlingAndRedaction(unittest.TestCase):
    """Verify secret security contract per Architecture Zero §23.2 and D21."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_to_dict_redacts_api_key_by_default(self) -> None:
        """api_key is masked to '[REDACTED]' in to_dict(redacted=True)."""
        cfg = TarjomanConfig(api_key="sk-ant-api03-test-secret-key-123456789")

        redacted_dict = cfg.to_dict(redacted=True)
        self.assertEqual(redacted_dict["api_key"], "[REDACTED]")

        # Default argument is redacted=True
        self.assertEqual(cfg.to_dict()["api_key"], "[REDACTED]")

    def test_to_dict_unredacted_preserves_secret(self) -> None:
        """to_dict(redacted=False) returns plaintext secret when explicitly requested."""
        secret = "sk-proj-super-secret-key-987654321"
        cfg = TarjomanConfig(api_key=secret)

        raw_dict = cfg.to_dict(redacted=False)
        self.assertEqual(raw_dict["api_key"], secret)

    def test_to_dict_redacts_nested_secret_keys(self) -> None:
        """Keys matching secret regex in extra_settings/tables are masked."""
        cfg = TarjomanConfig(
            extra_settings={
                "custom_token": "my-secret-token",
                "auth_password": "superpassword",
                "nested": {
                    "access_token": "bearer-123",
                    "safe_config": "visible",
                },
                "safe_flag": 100,
            }
        )

        redacted = cfg.to_dict(redacted=True)
        extra = redacted["extra_settings"]
        self.assertEqual(extra["custom_token"], "[REDACTED]")
        self.assertEqual(extra["auth_password"], "[REDACTED]")
        self.assertEqual(extra["nested"]["access_token"], "[REDACTED]")
        self.assertEqual(extra["nested"]["safe_config"], "visible")
        self.assertEqual(extra["safe_flag"], 100)

    def test_project_toml_with_api_key_rejected(self) -> None:
        """Placing api_key in project tarjoman.toml raises ConfigurationError (§23.2, D21)."""
        toml_path = self.workspace / "tarjoman.toml"
        toml_path.write_text(
            """
project_name = "leak_attempt"
api_key = "sk-ant-test-key-should-fail"
""",
            encoding="utf-8",
        )

        with self.assertRaises(ConfigurationError) as cm:
            load_config(workspace_root=self.workspace, user_config_path=None)

        self.assertIn("Secret key", cm.exception.message)
        self.assertTrue("api_key" in cm.exception.details.get("forbidden_keys", []) or "api_key" in cm.exception.message)

    def test_project_toml_with_nested_secret_rejected(self) -> None:
        """Placing secrets inside subtables in project TOML raises ConfigurationError."""
        toml_path = self.workspace / "tarjoman.toml"
        toml_path.write_text(
            """
project_name = "subtable_leak"
[extra_settings]
hf_token = "hf_test_token_leak"
""",
            encoding="utf-8",
        )

        with self.assertRaises(ConfigurationError) as cm:
            load_config(workspace_root=self.workspace, user_config_path=None)

        self.assertIn("Secret key", cm.exception.message)
        self.assertTrue(
            any("token" in k for k in cm.exception.details.get("forbidden_keys", [])) or "token" in cm.exception.message
        )

    def test_repr_and_str_mask_secrets(self) -> None:
        """repr() and str() mask api_key to prevent leakage into normal logs (§23.2)."""
        cfg = TarjomanConfig(api_key="secret-value-never-in-logs")
        repr_str = repr(cfg)
        str_str = str(cfg)

        self.assertNotIn("secret-value-never-in-logs", repr_str)
        self.assertNotIn("secret-value-never-in-logs", str_str)
        self.assertIn("[REDACTED]", repr_str)
        self.assertIn("[REDACTED]", str_str)

    def test_to_toml_redaction(self) -> None:
        """to_toml() masks secrets by default."""
        cfg = TarjomanConfig(api_key="sk-secret-1234")
        toml_redacted = cfg.to_toml(redacted=True)
        self.assertIn('api_key = "[REDACTED]"', toml_redacted)
        self.assertNotIn("sk-secret-1234", toml_redacted)

        toml_raw = cfg.to_toml(redacted=False)
        self.assertIn('api_key = "sk-secret-1234"', toml_raw)

    def test_secrets_do_not_affect_compute_hash(self) -> None:
        """Two configs differing ONLY by secret value produce identical snapshot hashes."""
        cfg1 = TarjomanConfig(
            project_name="run",
            provider="openai",
            api_key="key-alpha-123",
            timeout_seconds=30.0,
        )
        cfg2 = TarjomanConfig(
            project_name="run",
            provider="openai",
            api_key="key-beta-456",
            timeout_seconds=30.0,
        )

        self.assertEqual(cfg1.compute_hash(), cfg2.compute_hash())


class TestUnknownConfigKeyPolicy(unittest.TestCase):
    """Verify unknown keys policy: fail closed by default for project config."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_unknown_keys_fail_closed_by_default(self) -> None:
        """Project TOML with unrecognized key raises ConfigurationError by default."""
        toml_path = self.workspace / "tarjoman.toml"
        toml_path.write_text(
            """
project_name = "test_project"
typo_setting = "invalid"
unknown_flag = 42
""",
            encoding="utf-8",
        )

        with self.assertRaises(ConfigurationError) as cm:
            load_config(workspace_root=self.workspace, user_config_path=None)

        self.assertIn("Unknown configuration key(s)", cm.exception.message)
        unknown_keys = cm.exception.details.get("unknown_keys", [])
        self.assertIn("typo_setting", unknown_keys)
        self.assertIn("unknown_flag", unknown_keys)

    def test_unknown_keys_allowed_with_allow_unknown_flag(self) -> None:
        """When allow_unknown=True, unknown keys are preserved in extra_settings."""
        toml_path = self.workspace / "tarjoman.toml"
        toml_path.write_text(
            """
project_name = "test_project"
custom_feature_flag = true
custom_counter = 12
[extra_settings]
existing_extra = "present"
""",
            encoding="utf-8",
        )

        cfg = load_config(
            workspace_root=self.workspace,
            user_config_path=None,
            allow_unknown=True,
        )

        self.assertEqual(cfg.project_name, "test_project")
        self.assertEqual(cfg.extra_settings["existing_extra"], "present")
        self.assertEqual(cfg.extra_settings["custom_feature_flag"], True)
        self.assertEqual(cfg.extra_settings["custom_counter"], 12)

    def test_cli_args_unknown_keys_policy(self) -> None:
        """CLI arguments with unknown keys fail by default and route with allow_unknown=True."""
        # Fail by default
        with self.assertRaises(ConfigurationError) as cm:
            load_config(
                workspace_root=None,
                user_config_path=None,
                cli_args={"bogus_cli_arg": "fail"},
            )
        self.assertIn("Unknown CLI argument", cm.exception.message)

        # Pass with allow_unknown=True
        cfg = load_config(
            workspace_root=None,
            user_config_path=None,
            cli_args={"bogus_cli_arg": "pass"},
            allow_unknown=True,
        )
        self.assertEqual(cfg.extra_settings["bogus_cli_arg"], "pass")

    def test_from_toml_unknown_keys_policy(self) -> None:
        """TarjomanConfig.from_toml respects allow_unknown flag."""
        toml_str = """
project_name = "from_toml_test"
unrecognized = 999
"""
        with self.assertRaises(ConfigurationError):
            TarjomanConfig.from_toml(toml_str, allow_unknown=False)

        cfg = TarjomanConfig.from_toml(toml_str, allow_unknown=True)
        self.assertEqual(cfg.extra_settings["unrecognized"], 999)


class TestReproducibilitySnapshotHash(unittest.TestCase):
    """Verify reproducibility snapshot hash (§23.3 and §42)."""

    def test_compute_hash_deterministic(self) -> None:
        """compute_hash() returns identical SHA-256 for identical configurations."""
        cfg1 = TarjomanConfig(project_name="book", timeout_seconds=12.0)
        cfg2 = TarjomanConfig(project_name="book", timeout_seconds=12.0)

        h1 = cfg1.compute_hash()
        h2 = cfg2.compute_hash()

        self.assertEqual(h1, h2)
        self.assertTrue(h1.startswith("sha256:"))
        hex_digest = h1.split(":", 1)[1]
        self.assertEqual(len(hex_digest), 64)

    def test_compute_hash_without_prefix(self) -> None:
        """compute_hash(prefix=False) returns pure 64-character hex digest."""
        cfg = TarjomanConfig()
        h = cfg.compute_hash(prefix=False)
        self.assertFalse(h.startswith("sha256:"))
        self.assertEqual(len(h), 64)

    def test_compute_hash_changes_on_non_secret_changes(self) -> None:
        """Changing any configuration field changes the snapshot hash."""
        base = TarjomanConfig(provider="echo", timeout_seconds=60.0)
        base_hash = base.compute_hash()

        variations = [
            TarjomanConfig(provider="openai", timeout_seconds=60.0),
            TarjomanConfig(provider="echo", timeout_seconds=45.0),
            TarjomanConfig(provider="echo", temperature=0.7),
            TarjomanConfig(provider="echo", domain_profile="scientific"),
            TarjomanConfig(provider="echo", local_only=True),
            TarjomanConfig(provider="echo", typography={"strict_zwnj": False}),
            TarjomanConfig(provider="echo", extra_settings={"version": 2}),
        ]

        for var in variations:
            self.assertNotEqual(
                base_hash,
                var.compute_hash(),
                f"Variation {var} should have different hash than base",
            )

    def test_compute_hash_unicode_normalization(self) -> None:
        """NFC normalized strings produce stable hashes."""
        composed = "é"
        decomposed = "é"

        cfg1 = TarjomanConfig(project_name=f"proj_{composed}")
        cfg2 = TarjomanConfig(project_name=f"proj_{decomposed}")

        self.assertEqual(cfg1.compute_hash(), cfg2.compute_hash())


class TestNoHiddenCwdConfigLookup(unittest.TestCase):
    """Verify §23.1: No hidden current-working-directory config lookup beyond explicit project file."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

        # Create a tarjoman.toml in the temporary directory
        (self.workspace / "tarjoman.toml").write_text(
            'project_name = "explicit_workspace"', encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_no_cwd_lookup_when_workspace_root_is_none(self) -> None:
        """When workspace_root is None, ConfigLoader does not look in CWD."""
        loader = ConfigLoader(
            workspace_root=None,
            project_config_path=None,
            user_config_path=None,
            env={},
        )
        # Resolved project config path should be None
        self.assertIsNone(loader._resolve_project_config_path())

    def test_explicit_workspace_root_loads_file(self) -> None:
        """Passing workspace_root explicitly finds workspace_root / 'tarjoman.toml'."""
        loader = ConfigLoader(
            workspace_root=self.workspace,
            project_config_path=None,
            user_config_path=None,
            env={},
        )
        resolved = loader._resolve_project_config_path()
        self.assertEqual(resolved, self.workspace / "tarjoman.toml")
        cfg = loader.load()
        self.assertEqual(cfg.project_name, "explicit_workspace")

    def test_explicit_project_config_path_nonexistent_raises(self) -> None:
        """Passing a non-existent project_config_path explicitly raises ConfigurationError."""
        bad_path = self.workspace / "does_not_exist.toml"
        loader = ConfigLoader(project_config_path=bad_path, env={})
        with self.assertRaises(ConfigurationError) as cm:
            loader.load()
        self.assertIn("not found", cm.exception.message)


class TestEnvironmentVariableParsing(unittest.TestCase):
    """Verify TARJOMAN_* environment variable parsing and type coercion."""

    def test_env_primitive_coercion(self) -> None:
        """Numeric, boolean, and path types are coerced correctly."""
        env = {
            "TARJOMAN_TIMEOUT_SECONDS": "15.5",
            "TARJOMAN_MAX_RETRIES": "5",
            "TARJOMAN_TEMPERATURE": "0.85",
            "TARJOMAN_LOCAL_ONLY": "true",
            "TARJOMAN_PROVIDER": "anthropic",
            "TARJOMAN_WORKSPACE_ROOT": "/tmp/test_ws",
        }
        parsed = parse_env_vars(env)
        self.assertEqual(parsed["timeout_seconds"], 15.5)
        self.assertEqual(parsed["max_retries"], 5)
        self.assertEqual(parsed["temperature"], 0.85)
        self.assertEqual(parsed["local_only"], True)
        self.assertEqual(parsed["provider"], "anthropic")
        self.assertEqual(parsed["workspace_root"], Path("/tmp/test_ws"))

    def test_env_invalid_float_raises_configuration_error(self) -> None:
        """Non-numeric string for float fields raises ConfigurationError."""
        env = {"TARJOMAN_TIMEOUT_SECONDS": "not-a-float"}
        with self.assertRaises(ConfigurationError) as cm:
            parse_env_vars(env)
        self.assertIn("Invalid value for environment variable", cm.exception.message)

    def test_env_nested_typography_fields(self) -> None:
        """TARJOMAN_TYPOGRAPHY__<KEY> maps to nested typography dict."""
        env = {
            "TARJOMAN_TYPOGRAPHY__STRICT_ZWNJ": "false",
            "TARJOMAN_TYPOGRAPHY__EM_DASH_POLICY": "adapt",
        }
        parsed = parse_env_vars(env)
        self.assertIn("typography", parsed)
        self.assertFalse(parsed["typography"]["strict_zwnj"])
        self.assertEqual(parsed["typography"]["em_dash_policy"], "adapt")

    def test_env_json_table_parsing(self) -> None:
        """JSON string values for typography and extra_settings are parsed."""
        env = {
            "TARJOMAN_TYPOGRAPHY": '{"strict_zwnj": false, "western_digits": true}',
            "TARJOMAN_EXTRA_SETTINGS": '{"debug_mode": true, "batch_size": 32}',
        }
        parsed = parse_env_vars(env)
        self.assertEqual(parsed["typography"]["strict_zwnj"], False)
        self.assertEqual(parsed["typography"]["western_digits"], True)
        self.assertEqual(parsed["extra_settings"]["debug_mode"], True)
        self.assertEqual(parsed["extra_settings"]["batch_size"], 32)

    def test_env_custom_key_routes_to_extra_settings(self) -> None:
        """Unrecognized TARJOMAN_* variable is routed to extra_settings."""
        env = {"TARJOMAN_CUSTOM_TUNING_FLAG": "42"}
        parsed = parse_env_vars(env)
        self.assertIn("extra_settings", parsed)
        self.assertEqual(parsed["extra_settings"]["custom_tuning_flag"], 42)


class TestTOMLSerializationAndRoundtrip(unittest.TestCase):
    """Verify TOML dumping and round-trip consistency."""

    def test_dump_toml_roundtrip(self) -> None:
        """Serialized TOML can be loaded back into TarjomanConfig without loss."""
        cfg = TarjomanConfig(
            project_name="roundtrip_book",
            provider="openai",
            model="gpt-4o",
            timeout_seconds=42.0,
            temperature=0.2,
            local_only=True,
            typography={"strict_zwnj": True, "em_dash_policy": "adapt"},
            extra_settings={"tuning_rate": 0.05, "experimental": True},
        )

        toml_str = cfg.to_toml(redacted=False)
        restored = TarjomanConfig.from_toml(toml_str)

        self.assertEqual(restored.project_name, cfg.project_name)
        self.assertEqual(restored.provider, cfg.provider)
        self.assertEqual(restored.model, cfg.model)
        self.assertEqual(restored.timeout_seconds, cfg.timeout_seconds)
        self.assertEqual(restored.temperature, cfg.temperature)
        self.assertEqual(restored.local_only, cfg.local_only)
        self.assertEqual(restored.typography, cfg.typography)
        self.assertEqual(restored.extra_settings, cfg.extra_settings)

    def test_dump_toml_escapes_special_characters(self) -> None:
        """Quotes, newlines, and backslashes in strings are escaped properly."""
        data = {
            "project_name": 'title with "quotes" and \n newlines and \\ backslash',
            "timeout_seconds": 10.0,
        }
        toml_str = dump_toml(data)
        import tomllib

        parsed = tomllib.loads(toml_str)
        self.assertEqual(parsed["project_name"], data["project_name"])


class TestValidationAndFieldConstraints(unittest.TestCase):
    """Verify model constraints and validation rules."""

    def test_invalid_timeout_seconds(self) -> None:
        """timeout_seconds <= 0 raises ConfigurationError."""
        with self.assertRaises(ConfigurationError):
            load_config(cli_args={"timeout_seconds": -5.0})
        with self.assertRaises(ConfigurationError):
            load_config(cli_args={"timeout_seconds": 0.0})

    def test_invalid_temperature(self) -> None:
        """temperature < 0 raises ConfigurationError."""
        with self.assertRaises(ConfigurationError):
            load_config(cli_args={"temperature": -0.1})

    def test_invalid_max_retries(self) -> None:
        """max_retries < 0 raises ConfigurationError."""
        with self.assertRaises(ConfigurationError):
            load_config(cli_args={"max_retries": -1})

    def test_typography_accepts_typographic_rules_model(self) -> None:
        """typography field accepts a TypographicRules instance and converts to dict."""
        rules = TypographicRules(strict_zwnj=True, western_digits=True)
        cfg = TarjomanConfig(typography=rules)
        self.assertTrue(cfg.typography["strict_zwnj"])
        self.assertTrue(cfg.typography["western_digits"])


if __name__ == "__main__":
    unittest.main()
