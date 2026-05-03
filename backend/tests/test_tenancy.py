import unittest

from fizrmm.models import AccessDenied, TenantContext
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

    def test_remote_session_creates_timeline_event(self):
        result = self.store.create_remote_session(
            self.acme_tech,
            "asset-acme-win-01",
            "meshcentral",
        )

        timeline = self.store.list_timeline(self.acme_tech, "asset-acme-win-01")
        self.assertEqual(result["engine"], "meshcentral")
        self.assertEqual(timeline[0].kind, "remote_session")

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


if __name__ == "__main__":
    unittest.main()
