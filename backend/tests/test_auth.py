import unittest
from email.message import Message

from fizrmm.api import context_from_headers
from fizrmm.auth import context_from_claims


class AuthContextTests(unittest.TestCase):
    def test_claims_map_platform_admin_role(self):
        context = context_from_claims(
            {
                "preferred_username": "demo-admin",
                "fizrmm_orgs": ["org_acme", "org_globex"],
                "realm_access": {"roles": ["platform-admin"]},
            }
        )

        self.assertEqual(context.user_id, "demo-admin")
        self.assertTrue(context.platform_admin)
        self.assertEqual(context.allowed_org_ids, ("org_acme", "org_globex"))

    def test_claims_map_technician_orgs_from_string(self):
        context = context_from_claims(
            {
                "preferred_username": "demo-tech",
                "fizrmm_orgs": "org_acme, org_globex",
                "realm_access": {"roles": ["technician"]},
            }
        )

        self.assertEqual(context.role, "technician")
        self.assertFalse(context.platform_admin)
        self.assertEqual(context.allowed_org_ids, ("org_acme", "org_globex"))

    def test_header_simulation_still_works_without_bearer_token(self):
        headers = Message()
        headers["X-FizRMM-User"] = "header-tech"
        headers["X-FizRMM-Orgs"] = "org_acme"
        headers["X-FizRMM-Role"] = "technician"

        context = context_from_headers(headers)

        self.assertEqual(context.user_id, "header-tech")
        self.assertEqual(context.allowed_org_ids, ("org_acme",))


if __name__ == "__main__":
    unittest.main()
