import unittest

from fizrmm.models import AccessDenied, TenantContext, ValidationError
from fizrmm.store import seed_store


class TenancyTests(unittest.TestCase):
    def setUp(self):
        self.store = seed_store()
        self.acme_tech = TenantContext(
            user_id="tech-a",
            allowed_org_ids=("org_acme",),
        )
        self.platform_admin = TenantContext(
            user_id="admin",
            allowed_org_ids=(),
            role="platform-admin",
            platform_admin=True,
        )

    def test_technician_sees_only_allowed_org_assets(self):
        assets = self.store.list_assets(self.acme_tech)

        self.assertEqual({asset.org_id for asset in assets}, {"org_acme"})

    def test_cross_org_asset_lookup_is_denied(self):
        with self.assertRaises(AccessDenied):
            self.store.get_asset(self.acme_tech, "asset-globex-mac-01")

    def test_platform_admin_can_see_all_assets(self):
        assets = self.store.list_assets(self.platform_admin)

        self.assertEqual(
            {asset.org_id for asset in assets},
            {"org_acme", "org_globex"},
        )

    def test_platform_admin_can_create_organization(self):
        organization = self.store.create_organization(
            self.platform_admin,
            "New Customer",
        )

        self.assertEqual(organization.id, "org_new_customer")
        self.assertIn(organization, self.store.list_organizations(self.platform_admin))

    def test_technician_cannot_create_organization(self):
        with self.assertRaises(AccessDenied):
            self.store.create_organization(self.acme_tech, "Blocked Customer")

    def test_remote_session_creates_timeline_event(self):
        result = self.store.create_remote_session(
            self.acme_tech,
            "asset-acme-win-01",
            "meshcentral",
        )

        timeline = self.store.list_timeline(self.acme_tech, "asset-acme-win-01")
        self.assertEqual(result["engine"], "meshcentral")
        self.assertIn(result["status"], {"brokered", "integration_not_configured"})
        self.assertTrue(result["launch_url"].startswith("/remote/meshcentral/"))
        self.assertEqual(timeline[0].kind, "remote_session")


    def test_remote_session_reports_skipped_meshcentral_agent(self):
        enrollment = self.store.create_enrollment(
            self.acme_tech,
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://127.0.0.1:8000"},
            "2099-01-01T00:00:00+00:00",
        )
        claim = self.store.claim_enrollment(enrollment["token"], "fedora-endpoint", "Fedora Linux")
        self.store.report_enrollment(
            enrollment["token"],
            [{"agent": "meshcentral", "status": "skipped_no_installer_url"}],
        )

        result = self.store.create_remote_session(
            self.acme_tech,
            claim["asset_id"],
            "meshcentral",
        )

        self.assertEqual(result["status"], "agent_not_installed")
        self.assertIn("MeshCentral is not installed", result["message"])
        self.assertIn("status=agent_not_installed", result["launch_url"])

    def test_script_run_uses_salt_executor(self):
        result = self.store.create_script_run(
            self.acme_tech,
            "asset-acme-win-01",
            "script-disk-cleanup",
        )

        self.assertEqual(result["executor"], "salt")
        self.assertEqual(result["status"], "queued")

    def test_enrollment_claim_and_report_creates_asset_health(self):
        enrollment = self.store.create_enrollment(
            self.acme_tech,
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://127.0.0.1:8000"},
            "2099-01-01T00:00:00+00:00",
        )

        claim = self.store.claim_enrollment(
            enrollment["token"],
            "ACME-LAPTOP-01",
            "Windows 11 Pro",
        )
        report = self.store.report_enrollment(
            enrollment["token"],
            [
                {
                    "agent": "meshcentral",
                    "status": "installed",
                    "version": "1.0",
                    "external_id": "meshcentral:ACME-LAPTOP-01",
                }
            ],
        )

        agents = self.store.list_agent_health(self.acme_tech, claim["asset_id"])
        self.assertEqual(report["status"], "completed")
        self.assertEqual(agents[0].agent, "meshcentral")

    def test_enrollment_token_claim_is_idempotent_for_retries(self):
        enrollment = self.store.create_enrollment(
            self.acme_tech,
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://127.0.0.1:8000"},
            "2099-01-01T00:00:00+00:00",
        )

        first_claim = self.store.claim_enrollment(enrollment["token"], "ACME-ONE", "Windows 11 Pro")
        second_claim = self.store.claim_enrollment(enrollment["token"], "ACME-TWO", "Windows 11 Pro")

        self.assertEqual(second_claim["asset_id"], first_claim["asset_id"])

    def test_expired_enrollment_token_is_rejected(self):
        enrollment = self.store.create_enrollment(
            self.acme_tech,
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://127.0.0.1:8000"},
            "2000-01-01T00:00:00+00:00",
        )

        with self.assertRaises(ValidationError):
            self.store.claim_enrollment(enrollment["token"], "ACME-OLD", "Windows 11 Pro")

    def test_invalid_agent_report_is_rejected(self):
        enrollment = self.store.create_enrollment(
            self.acme_tech,
            "org_acme",
            "Acme HQ",
            {"portal_url": "http://127.0.0.1:8000"},
            "2099-01-01T00:00:00+00:00",
        )
        self.store.claim_enrollment(enrollment["token"], "ACME-LAPTOP-02", "Windows 11 Pro")

        with self.assertRaises(ValidationError):
            self.store.report_enrollment(
                enrollment["token"],
                [{"agent": "unknown-agent", "status": "installed"}],
            )


if __name__ == "__main__":
    unittest.main()
