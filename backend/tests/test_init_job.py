import importlib.util
import os
import sys
import unittest
from pathlib import Path

INIT_DIR = Path(__file__).resolve().parents[2] / "deploy" / "init"
sys.path.insert(0, str(INIT_DIR))
spec = importlib.util.spec_from_file_location("fizrmm_init_job", INIT_DIR / "init.py")
init_job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init_job)


class InitServiceWaitTests(unittest.TestCase):
    def setUp(self):
        self.previous_required_services = os.environ.get("FIZRMM_INIT_REQUIRED_SERVICES")
        os.environ.pop("FIZRMM_INIT_REQUIRED_SERVICES", None)
        self.previous_timeout = init_job.WAIT_TIMEOUT_SECONDS
        self.previous_can_connect = init_job.can_connect
        self.previous_sleep = init_job.time.sleep
        init_job.WAIT_TIMEOUT_SECONDS = 0
        init_job.can_connect = lambda host, port: False
        init_job.time.sleep = lambda seconds: None

    def tearDown(self):
        if self.previous_required_services is None:
            os.environ.pop("FIZRMM_INIT_REQUIRED_SERVICES", None)
        else:
            os.environ["FIZRMM_INIT_REQUIRED_SERVICES"] = self.previous_required_services
        init_job.WAIT_TIMEOUT_SECONDS = self.previous_timeout
        init_job.can_connect = self.previous_can_connect
        init_job.time.sleep = self.previous_sleep

    def test_salt_is_required_by_default(self):
        services = {name: init_job.SERVICE_PORTS[name] for name in ("keycloak", "salt")}

        self.assertIn("salt", init_job.selected_required_services(services))

    def test_optional_unreachable_service_does_not_fail_init(self):
        reached = init_job.wait_for_services({"salt": ("salt-master", 4505)}, required_services=set())

        self.assertEqual(reached, set())

    def test_required_unreachable_service_still_fails_init(self):
        with self.assertRaisesRegex(TimeoutError, "required services: salt"):
            init_job.wait_for_services({"salt": ("salt-master", 4505)}, required_services={"salt"})

    def test_reachability_marker_records_false_for_optional_miss(self):
        config = {"integrations": {"salt": {"init": {"status": "planned"}}}}

        init_job.mark_service_reachability(
            config,
            {"salt": ("salt-master", 4505)},
            reached_services=set(),
        )

        self.assertFalse(config["integrations"]["salt"]["init"]["service_reachable"])


if __name__ == "__main__":
    unittest.main()
