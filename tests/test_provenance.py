import unittest

from app.correlation.provenance import enrich
from app.models import PipelineHealth, PipelineSpec, RunProvenance


class ProvenanceTests(unittest.TestCase):
    def test_only_exact_project_definition_id_and_run_matches_are_enriched(self):
        run = PipelineHealth(
            pipeline=PipelineSpec(project="Platform", name="Smoke", definition_id=1, role="smoke-test"),
            run_id=10,
            agent_pool="actual-execution-pool",
        )
        provenance = (
            RunProvenance(project="Templates", pipeline_definition_id=1, run_id=10, image_version="wrong-project"),
            RunProvenance(project="Platform", pipeline_definition_id=2, run_id=10, image_version="wrong-definition"),
            RunProvenance(project="Platform", pipeline_definition_id=1, run_id=11, image_version="wrong-run"),
            RunProvenance(
                project="Platform",
                pipeline_definition_id=1,
                run_id=10,
                agent_pool="deployment-target-pool",
                image_version="v2",
            ),
        )

        enrich(run, provenance)

        self.assertEqual(run.provenance.image_version, "v2")
        self.assertEqual(run.agent_pool, "actual-execution-pool")
