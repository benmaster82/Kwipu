import unittest
from unittest import mock

from bridge import __main__ as bridge_main


class BridgeMainTests(unittest.TestCase):
    def test_main_runs_uvicorn_with_configured_host_and_port_without_reload(self):
        with mock.patch.object(bridge_main.uvicorn, "run") as run:
            bridge_main.main()

        run.assert_called_once_with(
            bridge_main.app,
            host=bridge_main.config.HOST,
            port=bridge_main.config.PORT,
        )
        self.assertNotIn("reload", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
