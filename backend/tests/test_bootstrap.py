import unittest

from fizrmm.bootstrap import render_linux_bootstrap, render_windows_bootstrap
from fizrmm.store import seed_store
from fizrmm.models import TenantContext


class BootstrapTests(unittest.TestCase):
    def test_enrollment_includes_windows_and_linux_bootstrap_commands(self):
        store = seed_store()
        enrollment = store.create_enrollment(
            TenantContext(user_id="tech", allowed_org_ids=("org_acme",)),
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://127.0.0.1:8000"},
            "2099-01-01T00:00:00+00:00",
        )

        self.assertTrue(enrollment["bootstrap_url"].endswith("/bootstrap.ps1"))
        self.assertTrue(enrollment["linux_bootstrap_url"].endswith("/bootstrap.sh"))
        self.assertIn("powershell.exe", enrollment["command"])
        self.assertIn(enrollment["token"], enrollment["command"])
        self.assertIn(enrollment["token"], enrollment["linux_command"])
        self.assertIn("sudo bash ./fizrmm-bootstrap.sh", enrollment["linux_command"])
        self.assertNotIn("<token>", enrollment["command"])
        self.assertNotIn("<token>", enrollment["linux_command"])

    def test_linux_bootstrap_claims_reports_and_skips_missing_installers(self):
        script = render_linux_bootstrap("http://127.0.0.1:8000", "token-123")

        self.assertIn("#!/usr/bin/env bash", script)
        self.assertIn("/api/enrollments/$ENROLLMENT_TOKEN/claim", script)
        self.assertIn("/api/enrollments/$ENROLLMENT_TOKEN/report", script)
        self.assertIn("skipped_no_installer_url", script)
        self.assertIn("linux_installer_url", script)

    def test_rendered_linux_bootstrap_runs_against_api(self):
        import os
        import subprocess
        import tempfile
        import threading
        import time
        import urllib.request

        from fizrmm.api import deployment_config, make_server

        store = seed_store()
        config = deployment_config()
        config["portal_url"] = "http://127.0.0.1:8766"
        enrollment = store.create_enrollment(
            TenantContext(user_id="tech", allowed_org_ids=("org_acme",)),
            "org_acme",
            "Acme HQ",
            config,
            "2099-01-01T00:00:00+00:00",
        )
        token = enrollment["token"]
        server = make_server("127.0.0.1", 8766, store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.05)

        try:
            script = urllib.request.urlopen(
                f"http://127.0.0.1:8766/api/enrollments/{token}/bootstrap.sh",
                timeout=2,
            ).read().decode("utf-8")
            with tempfile.NamedTemporaryFile("w", delete=False) as handle:
                handle.write(script)
                path = handle.name
            os.chmod(path, 0o755)
            result = subprocess.run(["bash", path], text=True, capture_output=True, timeout=10)
        finally:
            server.shutdown()
            server.server_close()
            if "path" in locals():
                os.unlink(path)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FizRMM Linux bootstrap complete", result.stdout)

    def test_linux_bootstrap_does_not_use_windows_installer_fallbacks(self):
        script = render_linux_bootstrap("http://127.0.0.1:8000", "token-123")

        self.assertIn('get("linux_installer_url", "")', script)
        self.assertIn('get("linux_install_args", "")', script)
        self.assertNotIn('get("installer_url", "")', script)
        self.assertNotIn('get("install_args", "")', script)

    def test_windows_bootstrap_still_claims_and_reports(self):
        script = render_windows_bootstrap("http://127.0.0.1:8000", "token-123")

        self.assertIn("/api/enrollments/$EnrollmentToken/claim", script)
        self.assertIn("/api/enrollments/$EnrollmentToken/report", script)

    def test_enrollment_claim_and_report_are_idempotent_for_retries(self):
        store = seed_store()
        enrollment = store.create_enrollment(
            TenantContext(user_id="tech", allowed_org_ids=("org_acme",)),
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://server:8000"},
            "2099-01-01T00:00:00+00:00",
        )
        token = enrollment["token"]

        first_claim = store.claim_enrollment(token, "retry-host", "Linux")
        second_claim = store.claim_enrollment(token, "retry-host", "Linux")

        self.assertEqual(second_claim["asset_id"], first_claim["asset_id"])

        first_report = store.report_enrollment(token, [{"agent": "salt", "status": "reported"}])
        second_report = store.report_enrollment(token, [{"agent": "salt", "status": "reported"}])

        self.assertEqual(first_report["status"], "completed")
        self.assertEqual(second_report["status"], "completed")


class PublicPortalUrlTests(unittest.TestCase):
    def setUp(self):
        import os
        self.previous_public_url = os.environ.get("FIZRMM_PUBLIC_URL")
        os.environ.pop("FIZRMM_PUBLIC_URL", None)

    def tearDown(self):
        import os
        if self.previous_public_url is None:
            os.environ.pop("FIZRMM_PUBLIC_URL", None)
        else:
            os.environ["FIZRMM_PUBLIC_URL"] = self.previous_public_url

    def test_request_host_replaces_loopback_portal_url_for_bootstrap(self):
        from fizrmm.api import public_portal_url

        portal_url = public_portal_url({"Host": "164.152.27.91:8000"}, "http://127.0.0.1:8000")

        self.assertEqual(portal_url, "http://164.152.27.91:8000")

    def test_forwarded_host_is_used_for_proxied_portal_requests(self):
        from fizrmm.api import public_portal_url

        portal_url = public_portal_url(
            {"Host": "api:8000", "X-Forwarded-Host": "164.152.27.91:5173", "X-Forwarded-Proto": "http"},
            "http://127.0.0.1:8000",
        )

        self.assertEqual(portal_url, "http://164.152.27.91:5173")


class MeshCentralInstallerDefaultTests(unittest.TestCase):
    def setUp(self):
        import os
        self.previous = {
            key: os.environ.get(key)
            for key in (
                "MESHCENTRAL_MESH_ID",
                "MESHCENTRAL_PUBLIC_URL",
                "MESHCENTRAL_PUBLIC_PORT",
                "MESHCENTRAL_LINUX_INSECURE_TLS",
                "FIZRMM_PUBLIC_URL",
                "FIZRMM_INTEGRATIONS_FILE",
                "FIZRMM_REQUIRE_MESHCENTRAL_AGENT",
            )
        }
        for key in self.previous:
            os.environ.pop(key, None)

    def tearDown(self):
        import os
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_create_enrollment_succeeds_without_meshcentral_installer(self):
        import json
        import os
        import threading
        import time
        import urllib.request

        from fizrmm.api import make_server

        for key in ("MESHCENTRAL_MESH_ID", "MESHCENTRAL_LINUX_AGENT_INSTALLER_URL"):
            os.environ.pop(key, None)
        store = seed_store()
        server = make_server("127.0.0.1", 8769, store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.05)

        try:
            request = urllib.request.Request(
                "http://127.0.0.1:8769/api/enrollments",
                data=json.dumps({"org_id": "org_acme", "site": "Acme HQ", "expires_hours": 24}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Host": "164.152.27.91:5173"},
                method="POST",
            )
            payload = json.loads(urllib.request.urlopen(request, timeout=2).read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertIn("token", payload)
        self.assertTrue(payload["linux_bootstrap_url"].endswith("/bootstrap.sh"))
        self.assertIn("sudo bash ./fizrmm-bootstrap.sh", payload["linux_command"])

    def test_claim_skips_missing_meshcentral_by_default(self):
        import json
        import urllib.request
        import threading
        import time

        from fizrmm.api import make_server

        store = seed_store()
        enrollment = store.create_enrollment(
            TenantContext(user_id="tech", allowed_org_ids=("org_acme",)),
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://127.0.0.1:8000", "meshcentral": {}},
            "2099-01-01T00:00:00+00:00",
        )
        server = make_server("127.0.0.1", 8768, store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.05)

        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:8768/api/enrollments/{enrollment['token']}/claim",
                data=json.dumps({"hostname": "host1", "operating_system": "Linux"}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Host": "164.152.27.91:5173"},
                method="POST",
            )
            payload = json.loads(urllib.request.urlopen(request, timeout=2).read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertIn("asset_id", payload)
        self.assertEqual(store.get_enrollment_by_token(enrollment["token"]).status, "claimed")

    def test_meshcentral_mesh_id_generates_linux_installer_url(self):
        import os
        from fizrmm.api import meshcentral_installer_defaults

        os.environ["MESHCENTRAL_MESH_ID"] = "mesh/domain/example id"

        defaults = meshcentral_installer_defaults("http://164.152.27.91:5173")

        self.assertEqual(defaults["mesh_id"], "mesh/domain/example id")
        self.assertEqual(defaults["linux_install_args"], '"$INSTALLER_PATH" -install')
        self.assertEqual(defaults["linux_insecure_tls"], "true")
        self.assertIn("https://164.152.27.91:8443/meshagents?id=6", defaults["linux_installer_url"])
        self.assertIn("meshid=mesh%2Fdomain%2Fexample%20id", defaults["linux_installer_url"])

    def test_claim_response_fills_meshcentral_defaults_for_existing_enrollment(self):
        import os
        import urllib.request
        import json
        import threading
        import time

        from fizrmm.api import make_server

        os.environ["MESHCENTRAL_MESH_ID"] = "mesh/domain/default"
        store = seed_store()
        enrollment = store.create_enrollment(
            TenantContext(user_id="tech", allowed_org_ids=("org_acme",)),
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://127.0.0.1:8000", "meshcentral": {}},
            "2099-01-01T00:00:00+00:00",
        )
        server = make_server("127.0.0.1", 8767, store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.05)

        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:8767/api/enrollments/{enrollment['token']}/claim",
                data=json.dumps({"hostname": "host1", "operating_system": "Linux"}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Host": "164.152.27.91:5173"},
                method="POST",
            )
            payload = json.loads(urllib.request.urlopen(request, timeout=2).read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        meshcentral = payload["config"]["meshcentral"]
        self.assertIn("https://164.152.27.91:8443/meshagents?id=6", meshcentral["linux_installer_url"])
        self.assertEqual(meshcentral["linux_install_args"], '"$INSTALLER_PATH" -install')

    def test_explicit_meshcentral_requirement_rejects_missing_agent_configuration(self):
        import json
        import os
        import tempfile
        from pathlib import Path

        from fizrmm.api import require_meshcentral_agent_config
        from fizrmm.models import ValidationError

        os.environ["FIZRMM_REQUIRE_MESHCENTRAL_AGENT"] = "true"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integrations.json"
            path.write_text(
                json.dumps({"integrations": {"meshcentral": {"init": {"service_reachable": True}}}}),
                encoding="utf-8",
            )
            os.environ["FIZRMM_INTEGRATIONS_FILE"] = str(path)

            with self.assertRaisesRegex(ValidationError, "MESHCENTRAL_MESH_ID"):
                require_meshcentral_agent_config({"meshcentral": {}})


if __name__ == "__main__":
    unittest.main()
