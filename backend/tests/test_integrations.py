import json
import os
import tempfile
import unittest
from pathlib import Path

from fizrmm.api import deployment_config, integration_status


class RuntimeIntegrationConfigTests(unittest.TestCase):
    def setUp(self):
        self.previous = {
            key: os.environ.get(key)
            for key in (
                "FIZRMM_INTEGRATIONS_FILE",
                "KEYCLOAK_URL",
                "OIDC_CLIENT_ID",
                "OIDC_CLIENT_SECRET",
                "MESHCENTRAL_URL",
            )
        }

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_runtime_config_feeds_deployment_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integrations.json"
            path.write_text(
                json.dumps(
                    {
                        "integrations": {
                            "meshcentral": {
                                "bootstrap": {
                                    "server_url": "http://meshcentral:443",
                                    "installer_url": "http://api/installers/meshcentral.exe",
                                    "install_args": "/quiet",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(path)

            config = deployment_config()

        self.assertEqual(config["meshcentral"]["server_url"], "http://meshcentral:443")
        self.assertEqual(config["meshcentral"]["installer_url"], "http://api/installers/meshcentral.exe")
        self.assertEqual(config["meshcentral"]["install_args"], "/quiet")

    def test_integration_status_reports_runtime_init_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integrations.json"
            path.write_text(
                json.dumps(
                    {
                        "integrations": {
                            "nats": {
                                "service": {"url": "nats://nats:4222"},
                                "init": {"runtime_config_written": True},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(path)

            status = integration_status()

        nats = next(item for item in status["integrations"] if item["id"] == "nats")
        self.assertTrue(status["runtime_config_loaded"])
        self.assertTrue(nats["configured"])
        self.assertTrue(nats["initialized"])
        self.assertEqual(nats["state"], "initialized")


if __name__ == "__main__":
    unittest.main()
