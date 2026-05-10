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


if __name__ == "__main__":
    unittest.main()
