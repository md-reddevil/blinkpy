"""
Test full system.

Tests the system initialization and attributes of
the main Blink system.  Tests if we properly catch
any communication related errors at startup.
"""

import unittest
from unittest import mock
from blinkpy import api
from blinkpy.blinkpy import Blink
from blinkpy.sync_module import BlinkSyncModule
from blinkpy.helpers.util import (
    http_req, create_session, BlinkAuthenticationException,
    BlinkException, BlinkURLHandler)
from blinkpy.helpers.constants import PROJECT_URL
import tests.mock_responses as mresp

USERNAME = 'foobar'
PASSWORD = 'deadbeef'


@mock.patch('blinkpy.helpers.util.Session.send',
            side_effect=mresp.mocked_session_send)
class TestBlinkSetup(unittest.TestCase):
    """Test the Blink class in blinkpy."""

    def setUp(self):
        """Set up Blink module."""
        self.blink_no_cred = Blink()
        self.blink = Blink(username=USERNAME,
                           password=PASSWORD)
        self.blink.sync = BlinkSyncModule(self.blink)
        self.blink.urls = BlinkURLHandler('test')
        self.blink.session = create_session()

    def tearDown(self):
        """Clean up after test."""
        self.blink = None
        self.blink_no_cred = None

    def test_initialization(self, mock_sess):
        """Verify we can initialize blink."""
        # pylint: disable=protected-access
        self.assertEqual(self.blink._username, USERNAME)
        # pylint: disable=protected-access
        self.assertEqual(self.blink._password, PASSWORD)

    def test_no_credentials(self, mock_sess):
        """Check that we throw an exception when no username/password."""
        with self.assertRaises(BlinkAuthenticationException):
            self.blink_no_cred.get_auth_token()
        # pylint: disable=protected-access
        self.blink_no_cred._username = USERNAME
        with self.assertRaises(BlinkAuthenticationException):
            self.blink_no_cred.get_auth_token()

    def test_no_auth_header(self, mock_sess):
        """Check that we throw an exception when no auth header given."""
        # pylint: disable=unused-variable
        (region_id, region), = mresp.LOGIN_RESPONSE['region'].items()
        self.blink.urls = BlinkURLHandler(region_id)
        with self.assertRaises(BlinkException):
            self.blink.get_ids()

    @mock.patch('blinkpy.blinkpy.getpass.getpass')
    def test_manual_login(self, getpwd, mock_sess):
        """Check that we can manually use the login() function."""
        getpwd.return_value = PASSWORD
        with mock.patch('builtins.input', return_value=USERNAME):
            self.assertTrue(self.blink_no_cred.login())
        # pylint: disable=protected-access
        self.assertEqual(self.blink_no_cred._username, USERNAME)
        # pylint: disable=protected-access
        self.assertEqual(self.blink_no_cred._password, PASSWORD)

    def test_bad_request(self, mock_sess):
        """Check that we raise an Exception with a bad request."""
        self.blink.session = create_session()
        explog = ("ERROR:blinkpy.helpers.util:"
                  "Cannot obtain new token for server auth. "
                  "Please report this issue on {}").format(PROJECT_URL)
        with self.assertRaises(BlinkException):
            http_req(self.blink, reqtype='bad')

        with self.assertLogs() as logrecord:
            http_req(self.blink, reqtype='post', is_retry=True)
        self.assertEqual(logrecord.output, [explog])

    def test_authentication(self, mock_sess):
        """Check that we can authenticate Blink up properly."""
        authtoken = self.blink.get_auth_token()['TOKEN_AUTH']
        expected = mresp.LOGIN_RESPONSE['authtoken']['authtoken']
        self.assertEqual(authtoken, expected)

    def test_reauthorization_attempt(self, mock_sess):
        """Check that we can reauthorize after first unsuccessful attempt."""
        original_header = self.blink.get_auth_token()
        # pylint: disable=protected-access
        bad_header = {'Host': self.blink._host, 'TOKEN_AUTH': 'BADTOKEN'}
        # pylint: disable=protected-access
        self.blink._auth_header = bad_header
        self.assertEqual(self.blink.auth_header, bad_header)
        api.request_homescreen(self.blink)
        self.assertEqual(self.blink.auth_header, original_header)

    @mock.patch('blinkpy.api.request_networks')
    def test_multiple_networks(self, mock_net, mock_sess):
        """Check that we handle multiple networks appropriately."""
        mock_net.return_value = {
            'networks': [{'id': 1234, 'account_id': 1111},
                         {'id': 5678, 'account_id': 2222}]
        }
        self.blink.networks = {'0000': {'onboarded': False},
                               '5678': {'onboarded': True},
                               '1234': {'onboarded': False}}
        self.blink.get_ids()
        self.assertEqual(self.blink.network_id, '5678')
        self.assertEqual(self.blink.account_id, 2222)

    @mock.patch('blinkpy.blinkpy.time.time')
    def test_throttle(self, mock_time, mock_sess):
        """Check throttling functionality."""
        now = self.blink.refresh_rate + 1
        mock_time.return_value = now
        self.assertEqual(self.blink.last_refresh, None)
        result = self.blink.check_if_ok_to_update()
        self.assertEqual(self.blink.last_refresh, now)
        self.assertEqual(result, True)
        self.assertEqual(self.blink.check_if_ok_to_update(), False)
        self.assertEqual(self.blink.last_refresh, now)
