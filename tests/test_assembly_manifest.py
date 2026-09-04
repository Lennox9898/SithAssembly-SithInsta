import unittest

from src.agent_controller import AgentController
from src.assembly_manifest import module_name, public_manifest


class AssemblyManifestTests(unittest.TestCase):
    def test_manifest_exposes_public_sithassembly_codenames(self) -> None:
        manifest = public_manifest()

        self.assertGreaterEqual(len(manifest), 10)
        self.assertIn(
            "SithAssembly//VektorZero",
            {module["codename"] for module in manifest},
        )
        self.assertEqual(module_name("relationship_engine"), "SithAssembly//SpectreNet")

    def test_processing_uses_manifest_module_name(self) -> None:
        updates = AgentController().updates_for_observation(
            relationship_count=2,
            profile_change_count=1,
        )

        self.assertEqual(updates[0].stage, "SithAssembly//VektorZero")


if __name__ == "__main__":
    unittest.main()
