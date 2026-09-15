import unittest
from http import HTTPStatus
from unittest.mock import Mock, patch

from app.server import DashboardHandler


class DashboardHandlerTests(unittest.TestCase):
    def _handler(self, send_json):
        handler = object.__new__(DashboardHandler)
        handler.config = Mock()
        handler._send_json = send_json
        return handler

    @patch("app.server.token_provider_from_environment")
    @patch("app.server.AzureDevOpsClient")
    def test_client_disconnect_writing_success_response_does_not_send_502(self, client_class, token_provider):
        send_json = Mock(side_effect=BrokenPipeError())
        handler = self._handler(send_json)

        with patch("app.server.collect_dashboard", return_value={"summary": {}}):
            handler._dashboard()

        send_json.assert_called_once_with(HTTPStatus.OK, {"summary": {}})

    @patch("app.server.token_provider_from_environment")
    @patch("app.server.AzureDevOpsClient")
    def test_collection_failure_sends_502(self, client_class, token_provider):
        send_json = Mock()
        handler = self._handler(send_json)

        with patch("app.server.collect_dashboard", side_effect=RuntimeError("Azure DevOps unavailable")):
            handler._dashboard()

        send_json.assert_called_once_with(HTTPStatus.BAD_GATEWAY, {"error": "Azure DevOps unavailable"})

    @patch("app.server.token_provider_from_environment")
    @patch("app.server.AzureDevOpsClient")
    def test_client_disconnect_writing_error_response_is_harmless(self, client_class, token_provider):
        send_json = Mock(side_effect=ConnectionResetError())
        handler = self._handler(send_json)

        with patch("app.server.collect_dashboard", side_effect=RuntimeError("Azure DevOps unavailable")):
            handler._dashboard()

        send_json.assert_called_once_with(HTTPStatus.BAD_GATEWAY, {"error": "Azure DevOps unavailable"})
