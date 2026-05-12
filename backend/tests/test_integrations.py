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
                "ZABBIX_SERVER",
                "WAZUH_MANAGER",
                "SALT_MASTER",
                "ZABBIX_API_URL",
                "WAZUH_API_URL",
                "SALT_API_URL",
                "OPENSEARCH_URL",
                "NATS_URL",
                "MESHCENTRAL_MESH_ID",
                "MESHCENTRAL_LINUX_AGENT_INSTALLER_URL",
            )
        }
        for key in self.previous:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_bundled_stack_defaults_are_reported_as_configured(self):
        for key in (
            "KEYCLOAK_URL",
            "OIDC_CLIENT_ID",
            "MESHCENTRAL_URL",
            "ZABBIX_SERVER",
            "WAZUH_MANAGER",
            "SALT_MASTER",
            "OPENSEARCH_URL",
            "NATS_URL",
        ):
            os.environ[key] = ""
        with tempfile.TemporaryDirectory() as directory:
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(Path(directory) / "missing-runtime.json")

            status = integration_status()
            config = deployment_config()

        integrations = {item["id"]: item for item in status["integrations"]}
        for integration_id in ("identity", "meshcentral", "zabbix", "wazuh", "salt", "opensearch", "nats"):
            self.assertTrue(integrations[integration_id]["configured"], integration_id)
            self.assertEqual(integrations[integration_id]["state"], "configured")
            self.assertEqual(integrations[integration_id]["missing"], [])
        self.assertEqual(integrations["identity"]["service_url"], "http://keycloak:8080")
        self.assertEqual(integrations["zabbix"]["service_url"], "http://zabbix-web:8080/api_jsonrpc.php")
        self.assertEqual(config["zabbix"]["server_url"], "zabbix-server")
        self.assertEqual(config["wazuh"]["manager_url"], "wazuh-manager")
        self.assertEqual(config["salt"]["master_url"], "salt-master")
        self.assertEqual(integrations["meshcentral"]["bootstrap_missing"], ["mesh_id or linux_installer_url"])
        self.assertFalse(status["ready_for_real_endpoints"])

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

    def test_runtime_config_written_alone_does_not_mark_initialized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integrations.json"
            path.write_text(
                json.dumps(
                    {
                        "integrations": {
                            "nats": {
                                "service": {"url": "nats://nats:4222"},
                                "init": {
                                    "status": "planned",
                                    "service_reachable": True,
                                    "runtime_config_written": True,
                                },
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
        self.assertFalse(nats["initialized"])
        self.assertEqual(nats["state"], "configured")

    def test_configured_runtime_status_marks_integration_initialized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integrations.json"
            path.write_text(
                json.dumps(
                    {
                        "integrations": {
                            "nats": {
                                "service": {"url": "nats://nats:4222"},
                                "init": {"status": "configured", "runtime_config_written": True},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(path)

            status = integration_status()

        nats = next(item for item in status["integrations"] if item["id"] == "nats")
        self.assertTrue(nats["initialized"])
        self.assertEqual(nats["state"], "initialized")


if __name__ == "__main__":
    unittest.main()
