import unittest

from app.correlation.provenance import enrich
from app.models import PipelineHealth, PipelineSpec, RunProvenance


class ProvenanceTests(unittest.TestCase):
    def test_only_exact_project_pipeline_and_run_matches_are_enriched(self):
        run = PipelineHealth(pipeline=PipelineSpec("smoke", "Platform", "Smoke", 1, "smoke-test"), run_id=10)
        provenance = (RunProvenance("Platform", "smoke", 10, image_version="v2"), RunProvenance("Platform", "smoke", 11, image_version="v3"))

        enrich(run, provenance)

        self.assertEqual(run.provenance.image_version, "v2")
