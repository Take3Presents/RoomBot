"""
Unit tests for feature-based redirects in party app.

Tests that the party feature properly enforces access control:
- Returns 501 when feature is disabled
- Logs warnings when disabled features are accessed
- Allows normal operation when feature is enabled
"""

import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory
from rest_framework import status
from party.views import PartyViewSet
from party.models import Party


class PartyFeatureRedirectTests(TestCase):
    """Test feature enforcement for party endpoints."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = APIRequestFactory()
        self.viewset = PartyViewSet.as_view({'get': 'list', 'post': 'create'})
        self.detail_viewset = PartyViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'delete': 'destroy'
        })

        # Create a test party entry
        self.party = Party.objects.create(
            room_number='1234',
            description='Test Party'
        )

    @patch('reservations.config.FEATURES', '')
    @patch('party.views.logger')
    def test_list_returns_501_when_feature_disabled(self, mock_logger):
        """Test that list endpoint returns 501 when party feature is disabled."""
        request = self.factory.get('/api/party/')
        response = self.viewset(request)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        self.assertIn('error', response.data)
        self.assertIn('not enabled', response.data['error'].lower())

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        self.assertIn('party', log_message.lower())

    @patch('reservations.config.FEATURES', '')
    @patch('party.views.logger')
    def test_retrieve_returns_501_when_feature_disabled(self, mock_logger):
        """Test that retrieve endpoint returns 501 when party feature is disabled."""
        request = self.factory.get(f'/api/party/{self.party.room_number}/')
        response = self.detail_viewset(request, room_number=self.party.room_number)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        mock_logger.warning.assert_called_once()

    @patch('reservations.config.FEATURES', '')
    @patch('party.views.logger')
    def test_create_returns_501_when_feature_disabled(self, mock_logger):
        """Test that create endpoint returns 501 when party feature is disabled."""
        request = self.factory.post('/api/party/', {
            'room_number': '5678',
            'description': 'New Party'
        }, format='json')
        response = self.viewset(request)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        mock_logger.warning.assert_called_once()

    @patch('reservations.config.FEATURES', '')
    @patch('party.views.logger')
    def test_update_returns_501_when_feature_disabled(self, mock_logger):
        """Test that update endpoint returns 501 when party feature is disabled."""
        request = self.factory.put(f'/api/party/{self.party.room_number}/', {
            'room_number': '5678',
            'description': 'Updated Party'
        }, format='json')
        response = self.detail_viewset(request, room_number=self.party.room_number)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        mock_logger.warning.assert_called_once()

    @patch('reservations.config.FEATURES', '')
    @patch('party.views.logger')
    def test_destroy_returns_501_when_feature_disabled(self, mock_logger):
        """Test that destroy endpoint returns 501 when party feature is disabled."""
        request = self.factory.delete(f'/api/party/{self.party.room_number}/')
        response = self.detail_viewset(request, room_number=self.party.room_number)

        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        mock_logger.warning.assert_called_once()

    @patch('reservations.config.FEATURES', 'party')
    def test_list_works_when_feature_enabled(self):
        """Test that list endpoint works normally when party feature is enabled."""
        request = self.factory.get('/api/party/')
        response = self.viewset(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

    @patch('reservations.config.FEATURES', 'party')
    def test_retrieve_works_when_feature_enabled(self):
        """Test that retrieve endpoint works normally when party feature is enabled."""
        request = self.factory.get(f'/api/party/{self.party.room_number}/')
        response = self.detail_viewset(request, room_number=self.party.room_number)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['room_number'], '1234')
