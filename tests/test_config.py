import tempfile
import unittest
from pathlib import Path

from app.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def test_loads_pipeline_and_explicit_provenance(self):
        content = """
organization_url: https://dev.azure.com/example
projects:
  - name: Platform
    repositories:
      - name: agents
    pipelines:
      - key: smoke
        name: Smoke
        definition_id: 12
        role: smoke-test
provenance:
  pipeline_runs:
    - project: Platform
      pipeline_key: smoke
      run_id: 55
      image_version: v1
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"
            path.write_text(content)
            config = load_config(path)

        self.assertEqual(config.pipelines[0].key, "smoke")
        self.assertEqual(config.run_provenance[0].image_version, "v1")

    def test_rejects_unknown_pipeline_role(self):
        content = """
organization_url: https://dev.azure.com/example
projects:
  - name: Platform
    pipelines:
      - key: bad
        name: Bad
        definition_id: 1
        role: guessed-correlation
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"
            path.write_text(content)
            with self.assertRaises(ConfigError):
                load_config(path)
