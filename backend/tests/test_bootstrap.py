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
        self.assertIn("sudo bash ./fizrmm-bootstrap.sh", enrollment["linux_command"])

    def test_linux_bootstrap_claims_reports_and_skips_missing_installers(self):
        script = render_linux_bootstrap("http://127.0.0.1:8000", "token-123")

        self.assertIn("#!/usr/bin/env bash", script)
        self.assertIn("/api/enrollments/$ENROLLMENT_TOKEN/claim", script)
        self.assertIn("/api/enrollments/$ENROLLMENT_TOKEN/report", script)
        self.assertIn("skipped_no_installer_url", script)
        self.assertIn("linux_installer_url", script)

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


if __name__ == "__main__":
    unittest.main()
