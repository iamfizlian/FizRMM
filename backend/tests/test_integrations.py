import json
import os
import tempfile
import unittest
from pathlib import Path

from fizrmm.api import apply_meshcentral_agent_defaults, configure_integration, deployment_config, integration_status
from fizrmm.models import TenantContext


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
                "MESHCENTRAL_PUBLIC_URL",
                "FIZRMM_PUBLIC_URL",
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
            os.environ["FIZRMM_PUBLIC_URL"] = "http://164.152.27.91:8000"

            status = integration_status()
            config = deployment_config()

        integrations = {item["id"]: item for item in status["integrations"]}
        for integration_id in ("identity", "meshcentral", "zabbix", "wazuh", "salt", "opensearch", "nats"):
            self.assertTrue(integrations[integration_id]["configured"], integration_id)
            self.assertEqual(integrations[integration_id]["state"], "initialized")
            self.assertTrue(integrations[integration_id]["initialized"], integration_id)
            self.assertEqual(integrations[integration_id]["missing"], [])
        self.assertEqual(integrations["identity"]["service_url"], "http://keycloak:8080")
        self.assertEqual(integrations["zabbix"]["service_url"], "http://zabbix-web:8080/api_jsonrpc.php")
        self.assertEqual(config["zabbix"]["server_url"], "164.152.27.91")
        self.assertEqual(config["wazuh"]["manager_url"], "164.152.27.91")
        self.assertEqual(config["salt"]["master_url"], "164.152.27.91")
        self.assertEqual(integrations["meshcentral"]["bootstrap_missing"], [])
        self.assertFalse(integrations["meshcentral"]["setup_required"])
        self.assertIn("meshagents?id=6", config["meshcentral"]["linux_installer_url"])
        self.assertTrue(status["ready_for_real_endpoints"])


    def test_integration_setup_api_persists_runtime_config(self):
        import urllib.request
        import threading
        import time

        from fizrmm.api import make_server
        from fizrmm.store import seed_store

        with tempfile.TemporaryDirectory() as directory:
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(Path(directory) / "integrations.json")
            server = make_server("127.0.0.1", 8770, seed_store())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            time.sleep(0.05)

            try:
                request = urllib.request.Request(
                    "http://127.0.0.1:8770/api/integrations/meshcentral/setup",
                    data=json.dumps({
                        "service": {"url": "https://mesh.example.test"},
                        "bootstrap": {"mesh_id": "mesh/domain/customer", "linux_insecure_tls": "false"},
                    }).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-FizRMM-Role": "platform-admin",
                        "X-FizRMM-Orgs": "org_acme",
                    },
                    method="POST",
                )
                payload = json.loads(urllib.request.urlopen(request, timeout=2).read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            config = deployment_config()

        meshcentral = next(item for item in payload["status"]["integrations"] if item["id"] == "meshcentral")
        self.assertEqual(config["meshcentral"]["mesh_id"], "mesh/domain/customer")
        self.assertEqual(config["meshcentral"]["server_url"], "https://mesh.example.test")
        self.assertEqual(meshcentral["bootstrap_missing"], [])

    def test_meshcentral_runtime_public_url_generates_bootstrap_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integrations.json"
            path.write_text(
                json.dumps(
                    {
                        "integrations": {
                            "meshcentral": {
                                "service": {"public_url": "https://mesh.example.test"},
                                "bootstrap": {"mesh_id": "mesh/domain/customer"},
                                "init": {"status": "configured", "service_reachable": True},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(path)

            config = deployment_config()
            status = integration_status()

        meshcentral = next(item for item in status["integrations"] if item["id"] == "meshcentral")
        self.assertIn("https://mesh.example.test/meshagents?id=6", config["meshcentral"]["linux_installer_url"])
        self.assertIn("meshid=mesh%2Fdomain%2Fcustomer", config["meshcentral"]["linux_installer_url"])
        self.assertEqual(meshcentral["bootstrap_missing"], [])

    def test_meshcentral_status_uses_public_request_host_for_generated_installer(self):
        with tempfile.TemporaryDirectory() as directory:
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(Path(directory) / "missing-runtime.json")

            status = integration_status({"Host": "164.152.27.91:5173"})

        meshcentral = next(item for item in status["integrations"] if item["id"] == "meshcentral")
        self.assertEqual(meshcentral["bootstrap_missing"], [])
        self.assertIn("https://164.152.27.91:8443/meshagents?id=6", meshcentral["bootstrap"]["linux_installer_url"])

    def test_meshcentral_internal_runtime_url_is_replaced_for_endpoint_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integrations.json"
            path.write_text(
                json.dumps(
                    {
                        "integrations": {
                            "meshcentral": {
                                "service": {"url": "https://meshcentral:443"},
                                "bootstrap": {
                                    "server_url": "https://meshcentral:443",
                                    "linux_installer_url": "http://meshcentral:443/meshagents?id=6&installflags=0",
                                },
                                "init": {"status": "configured", "service_reachable": True},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(path)
            config = deployment_config()

            apply_meshcentral_agent_defaults(config, "http://164.152.27.91:8000")

        meshcentral = config["meshcentral"]
        self.assertEqual(meshcentral["server_url"], "https://164.152.27.91:8443")
        self.assertIn("https://164.152.27.91:8443/meshagents?id=6", meshcentral["linux_installer_url"])
        self.assertNotIn("meshcentral:443", meshcentral["linux_installer_url"])


    def test_setup_api_can_run_deployment_task_from_portal(self):
        import socket

        with tempfile.TemporaryDirectory() as directory:
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(Path(directory) / "integrations.json")
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            host, port = listener.getsockname()
            try:
                payload = configure_integration(
                    TenantContext(user_id="admin", allowed_org_ids=["org_acme"], platform_admin=True),
                    "nats",
                    {"service": {"url": f"nats://{host}:{port}"}, "run_setup": True},
                )
            finally:
                listener.close()

            status = integration_status()

        integration = payload["integration"]
        nats = next(item for item in status["integrations"] if item["id"] == "nats")
        self.assertEqual(integration["init"]["requested_from"], "web_ui")
        self.assertEqual(integration["init"]["status"], "configured")
        self.assertTrue(nats["initialized"])

    def test_setup_task_keeps_runtime_initialized_when_service_is_not_reachable(self):
        with tempfile.TemporaryDirectory() as directory:
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(Path(directory) / "integrations.json")
            payload = configure_integration(
                TenantContext(user_id="admin", allowed_org_ids=["org_acme"], platform_admin=True),
                "nats",
                {"service": {"url": "nats://127.0.0.1:9"}, "run_setup": True},
            )

        self.assertEqual(payload["integration"]["init"]["requested_from"], "web_ui")
        self.assertEqual(payload["integration"]["init"]["status"], "configured")
        self.assertFalse(payload["integration"]["init"]["service_reachable"])

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

    def test_runtime_config_is_auto_initialized(self):
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
        self.assertTrue(nats["initialized"])
        self.assertEqual(nats["state"], "initialized")

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
