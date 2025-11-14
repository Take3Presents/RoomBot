"""
Unit tests for login endpoint redirect URL functionality.

Tests that the login endpoint properly returns:
- Feature list
- Redirect URL for disabled features
- Configurable redirect URL via environment variable
"""

import pytest
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework import status
from reservations.views.login import login


class LoginRedirectURLTests(TestCase):
    """Test login endpoint returns redirect URL for disabled features."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = APIRequestFactory()

    @patch('reservations.config.FEATURES', 'waittime,party')
    @patch('reservations.config.DISABLED_FEATURE_REDIRECT_URL', 'https://zombo.com')
    def test_login_returns_features_and_redirect_url(self):
        """Test that GET /api/login/ returns both features and redirect URL."""
        request = self.factory.get('/api/login/')
        response = login(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('features', response.data)
        self.assertIn('disabled_redirect_url', response.data)
        self.assertEqual(response.data['features'], 'waittime,party')
        self.assertEqual(response.data['disabled_redirect_url'], 'https://zombo.com')

    @patch('reservations.config.FEATURES', '')
    @patch('reservations.config.DISABLED_FEATURE_REDIRECT_URL', 'https://zombo.com')
    def test_login_returns_empty_features_with_redirect_url(self):
        """Test that login endpoint works with empty features list."""
        request = self.factory.get('/api/login/')
        response = login(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['features'], '')
        self.assertEqual(response.data['disabled_redirect_url'], 'https://zombo.com')

    @patch('reservations.config.FEATURES', 'waittime')
    @patch('reservations.config.DISABLED_FEATURE_REDIRECT_URL', 'https://example.com/custom')
    def test_login_returns_custom_redirect_url(self):
        """Test that custom redirect URL from config is returned."""
        request = self.factory.get('/api/login/')
        response = login(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['disabled_redirect_url'], 'https://example.com/custom')
