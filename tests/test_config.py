import tempfile
import unittest
from pathlib import Path

from app.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def test_loads_pipeline_configuration(self):
        content = """
organization_url: https://dev.azure.com/example
projects:
  - name: Platform
    repositories:
      - name: agents
    pipelines:
      - name: Smoke
        definition_id: 12
        role: smoke-test
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"
            path.write_text(content)
            config = load_config(path)

        self.assertEqual(config.pipelines[0].definition_id, 12)

    def test_rejects_agent_pool_in_pipeline_configuration(self):
        content = """
organization_url: https://dev.azure.com/example
projects:
  - name: Platform
    pipelines:
      - name: Smoke
        definition_id: 12
        role: smoke-test
        agent_pool: stale-configured-pool
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"
            path.write_text(content)
            with self.assertRaisesRegex(ConfigError, "agent_pool"):
                load_config(path)

    def test_rejects_manual_provenance_configuration(self):
        content = """
organization_url: https://dev.azure.com/example
projects:
  - name: Platform
    pipelines:
      - name: Smoke
        definition_id: 12
        role: smoke-test
provenance:
  pipeline_runs: []
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"
            path.write_text(content)
            with self.assertRaisesRegex(ConfigError, "provenance"):
                load_config(path)

    def test_rejects_unknown_pipeline_role(self):
        content = """
organization_url: https://dev.azure.com/example
projects:
  - name: Platform
    pipelines:
      - name: Bad
        definition_id: 1
        role: guessed-correlation
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"
            path.write_text(content)
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_pipeline_identity_is_project_and_definition_id(self):
        content = """
organization_url: https://dev.azure.com/example
projects:
  - name: Platform
    pipelines:
      - name: Platform Smoke
        definition_id: 12
        role: smoke-test
  - name: Templates
    pipelines:
      - name: Template Smoke
        definition_id: 12
        role: smoke-test
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"
            path.write_text(content)
            config = load_config(path)

        self.assertEqual(
            {(pipeline.project, pipeline.definition_id) for pipeline in config.pipelines},
            {("Platform", 12), ("Templates", 12)},
        )

    def test_rejects_duplicate_definition_id_within_a_project(self):
        content = """
organization_url: https://dev.azure.com/example
projects:
  - name: Platform
    pipelines:
      - name: Smoke A
        definition_id: 12
        role: smoke-test
      - name: Smoke B
        definition_id: 12
        role: smoke-test
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"
            path.write_text(content)
            with self.assertRaisesRegex(ConfigError, "definition ID 12 is duplicated"):
                load_config(path)
