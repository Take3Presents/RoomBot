"""
Unit tests for feature-based redirects in waittime app.

Tests that the waittime feature properly enforces access control:
- Returns 501 when feature is disabled
- Logs warnings when disabled features are accessed
- Allows normal operation when feature is enabled
"""

import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory
from rest_framework import status
from waittime.views import WaitViewSet
from waittime.models import Wait


class WaitTimeFeatureRedirectTests(TestCase):
    """Test feature enforcement for waittime endpoints."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = APIRequestFactory()
        self.viewset = WaitViewSet.as_view({'get': 'list', 'post': 'create'})
        self.detail_viewset = WaitViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'delete': 'destroy'
        })

        # Create a test wait time entry
        self.wait = Wait.objects.create(
            name='Test Ride',
            short_name='test_ride',
            time=30
        )

    @patch('reservations.config.FEATURES', '')
    @patch('waittime.views.logger')
    def test_list_returns_501_when_feature_disabled(self, mock_logger):
        """Test that list endpoint returns 501 when waittime feature is disabled."""
        request = self.factory.get('/api/wait/')
        response = self.viewset(request)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        self.assertIn('error', response.data)
        self.assertIn('not enabled', response.data['error'].lower())

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        self.assertIn('waittime', log_message.lower())

    @patch('reservations.config.FEATURES', '')
    @patch('waittime.views.logger')
    def test_retrieve_returns_501_when_feature_disabled(self, mock_logger):
        """Test that retrieve endpoint returns 501 when waittime feature is disabled."""
        request = self.factory.get(f'/api/wait/{self.wait.short_name}/')
        response = self.detail_viewset(request, short_name=self.wait.short_name)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        mock_logger.warning.assert_called_once()

    @patch('reservations.config.FEATURES', '')
    @patch('waittime.views.logger')
    def test_create_returns_501_when_feature_disabled(self, mock_logger):
        """Test that create endpoint returns 501 when waittime feature is disabled."""
        request = self.factory.post('/api/wait/', {
            'name': 'New Ride',
            'short_name': 'new_ride',
            'time': 45
        }, format='json')
        response = self.viewset(request)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        mock_logger.warning.assert_called_once()

    @patch('reservations.config.FEATURES', '')
    @patch('waittime.views.logger')
    def test_update_returns_501_when_feature_disabled(self, mock_logger):
        """Test that update endpoint returns 501 when waittime feature is disabled."""
        request = self.factory.put(f'/api/wait/{self.wait.short_name}/', {
            'name': 'Updated Ride',
            'short_name': 'updated_ride',
            'time': 60
        }, format='json')
        response = self.detail_viewset(request, short_name=self.wait.short_name)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        mock_logger.warning.assert_called_once()

    @patch('reservations.config.FEATURES', '')
    @patch('waittime.views.logger')
    def test_destroy_returns_501_when_feature_disabled(self, mock_logger):
        """Test that destroy endpoint returns 501 when waittime feature is disabled."""
        request = self.factory.delete(f'/api/wait/{self.wait.short_name}/')
        response = self.detail_viewset(request, short_name=self.wait.short_name)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        mock_logger.warning.assert_called_once()

    @patch('reservations.config.FEATURES', 'waittime')
    def test_list_works_when_feature_enabled(self):
        """Test that list endpoint works normally when waittime feature is enabled."""
        request = self.factory.get('/api/wait/')
        response = self.viewset(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

    @patch('reservations.config.FEATURES', 'waittime')
    def test_retrieve_works_when_feature_enabled(self):
        """Test that retrieve endpoint works normally when waittime feature is enabled."""
        request = self.factory.get(f'/api/wait/{self.wait.short_name}/')
        response = self.detail_viewset(request, short_name=self.wait.short_name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Ride')
