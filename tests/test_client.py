import unittest

from remarkable.client import RemarkableClient, RemarkableError


class RestartXochitlTests(unittest.TestCase):
    def test_restart_resets_failed_state_before_restart(self):
        commands = []

        class StubClient(RemarkableClient):
            def __init__(self):
                super().__init__(
                    {
                        "host": "127.0.0.1",
                        "username": "root",
                        "password": "secret",
                        "xochitl_path": "/tmp/xochitl",
                    }
                )

            def exec_command(self, command: str):
                commands.append(command)
                if command == "systemctl restart xochitl.service":
                    return 0, "", ""
                return 0, "", ""

        StubClient().restart_xochitl()
        self.assertEqual(
            commands,
            [
                "systemctl reset-failed xochitl.service",
                "systemctl restart xochitl.service",
            ],
        )

    def test_restart_reports_failure_details_when_status_check_fails(self):
        class StubClient(RemarkableClient):
            def __init__(self):
                super().__init__(
                    {
                        "host": "127.0.0.1",
                        "username": "root",
                        "password": "secret",
                        "xochitl_path": "/tmp/xochitl",
                    }
                )

            def exec_command(self, command: str):
                if command == "systemctl reset-failed xochitl.service":
                    return 0, "", ""
                if command == "systemctl restart xochitl.service":
                    return -1, "", ""
                if command == "systemctl is-active xochitl.service":
                    return 3, "failed\n", ""
                raise AssertionError(command)

        with self.assertRaises(RemarkableError) as ctx:
            StubClient().restart_xochitl()

        self.assertIn("exit=-1", str(ctx.exception))
        self.assertIn("is-active=failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
