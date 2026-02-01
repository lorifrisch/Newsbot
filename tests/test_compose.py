"""
Unit tests for composition module.

Tests DailyBriefComposer for daily and weekly brief generation,
OpenAI API error handling, and fallback responses.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from src.compose import DailyBriefComposer
from src.extract import FactCard


@pytest.mark.unit
class TestDailyBriefComposer:
    """Test suite for DailyBriefComposer."""
    
    def test_compose_daily_brief_success(self, test_settings, sample_fact_cards, mock_openai_composition_response):
        """Test successful daily brief composition."""
        composer = DailyBriefComposer(test_settings)
        
        # Create buckets
        buckets = {
            "top_stories": [sample_fact_cards[0]],
            "macro_policy": [sample_fact_cards[2]],
            "company_markets": [sample_fact_cards[1]],
            "watchlist": []
        }
        
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(mock_openai_composition_response)
        
        with patch.object(composer.ai, 'responses_create', return_value=mock_response):
            result = composer.compose_daily_brief(buckets)
        
        assert result["headline"] == "Markets Rally on Fed Pause Signal"
        assert "preheader" in result
        assert "intro" in result
        assert "top5_md" in result
        assert "macro_md" in result
        assert "watchlist_md" in result
        assert "snapshot_md" in result
    
    def test_compose_daily_brief_empty_buckets(self, test_settings, mock_openai_composition_response):
        """Test composition with empty buckets."""
        composer = DailyBriefComposer(test_settings)
        
        buckets = {
            "top_stories": [],
            "macro_policy": [],
            "company_markets": [],
            "watchlist": []
        }
        
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(mock_openai_composition_response)
        
        with patch.object(composer.ai, 'responses_create', return_value=mock_response):
            result = composer.compose_daily_brief(buckets)
        
        # Should still return valid structure
        assert "headline" in result
        assert "intro" in result
    
    def test_compose_daily_brief_openai_failure(self, test_settings, sample_fact_cards):
        """Test fallback response when OpenAI fails."""
        composer = DailyBriefComposer(test_settings)
        
        buckets = {
            "top_stories": [sample_fact_cards[0]],
            "macro_policy": [],
            "company_markets": [],
            "watchlist": []
        }
        
        # Mock OpenAI to raise exception
        with patch.object(composer.ai, 'responses_create', side_effect=Exception("API Error")):
            result = composer.compose_daily_brief(buckets)
        
        # Should return fallback response
        assert result["headline"] == "Morning Markets Update"
        assert "Data processing error" in result["top5_md"] or "currently unavailable" in result["macro_md"]
    
    def test_compose_daily_brief_invalid_json(self, test_settings, sample_fact_cards):
        """Test handling of invalid JSON from OpenAI."""
        composer = DailyBriefComposer(test_settings)
        
        buckets = {"top_stories": [sample_fact_cards[0]], "macro_policy": [], "company_markets": [], "watchlist": []}
        
        # Mock OpenAI to return invalid JSON
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not JSON"
        
        with patch.object(composer.ai, 'responses_create', return_value=mock_response):
            result = composer.compose_daily_brief(buckets)
        
        # Should return fallback response
        assert "headline" in result
    
    def test_compose_weekly_recap_success(self, test_settings, sample_fact_cards):
        """Test successful weekly recap composition."""
        composer = DailyBriefComposer(test_settings)
        
        # Mock OpenAI response
        weekly_response = {
            "headline": "Weekly Markets Recap: Fed Pivot Dominates",
            "preheader": "Central banks shift dovish as inflation cools",
            "intro": "Markets processed a major policy shift this week...",
            "theme_of_week": "The week's dominant theme was the Fed's dovish pivot",
            "top_developments": [
                {
                    "headline": "Fed Signals Pause",
                    "explanation": "Powell indicated rate hikes may be ending"
                }
            ],
            "next_week_outlook": "Focus turns to earnings season"
        }
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(weekly_response)
        
        with patch.object(composer.ai, 'responses_create', return_value=mock_response):
            result = composer.compose_weekly_recap(sample_fact_cards)
        
        assert result["headline"] == "Weekly Markets Recap: Fed Pivot Dominates"
        assert "theme_of_week" in result
        assert "top_developments" in result
        assert len(result["top_developments"]) > 0
        assert "next_week_outlook" in result
    
    def test_compose_weekly_recap_empty_cards(self, test_settings):
        """Test weekly recap with no fact cards."""
        composer = DailyBriefComposer(test_settings)
        
        weekly_response = {
            "headline": "Weekly Recap",
            "preheader": "Market updates",
            "intro": "Limited activity this week",
            "theme_of_week": "Quiet week",
            "top_developments": [],
            "next_week_outlook": "Watch for updates"
        }
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(weekly_response)
        
        with patch.object(composer.ai, 'responses_create', return_value=mock_response):
            result = composer.compose_weekly_recap([])
        
        assert "headline" in result
        assert "theme_of_week" in result
    
    def test_compose_weekly_recap_openai_failure(self, test_settings, sample_fact_cards):
        """Test fallback response when weekly recap fails."""
        composer = DailyBriefComposer(test_settings)
        
        with patch.object(composer.ai, 'responses_create', side_effect=Exception("API Error")):
            result = composer.compose_weekly_recap(sample_fact_cards)
        
        # Should return fallback response
        assert result["headline"] == "Weekly Markets Recap"
        assert "currently unavailable" in result.get("top5_md", "") or "currently unavailable" in result.get("macro_md", "")
    
    def test_compose_daily_brief_with_purpose_tag(self, test_settings, sample_fact_cards):
        """Test that composition calls include purpose tag for budget tracking."""
        composer = DailyBriefComposer(test_settings)
        
        buckets = {"top_stories": [sample_fact_cards[0]], "macro_policy": [], "company_markets": [], "watchlist": []}
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"headline": "Test", "intro": "Test", "preheader": "Test", "top5_md": "Test", "macro_md": "Test", "watchlist_md": "Test", "snapshot_md": "Test"})
        
        with patch.object(composer.ai, 'responses_create', return_value=mock_response) as mock_create:
            composer.compose_daily_brief(buckets)
        
        # Verify purpose tag was passed for budget tracking
        mock_create.assert_called_once()
        assert mock_create.call_args[1]['purpose'] == 'daily_composition'
    
    def test_compose_weekly_recap_with_purpose_tag(self, test_settings, sample_fact_cards):
        """Test that weekly recap includes purpose tag."""
        composer = DailyBriefComposer(test_settings)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"headline": "Test", "preheader": "Test", "intro": "Test", "theme_of_week": "Test", "top_developments": [], "next_week_outlook": "Test"})
        
        with patch.object(composer.ai, 'responses_create', return_value=mock_response) as mock_create:
            composer.compose_weekly_recap(sample_fact_cards)
        
        # Verify purpose tag
        assert mock_create.call_args[1]['purpose'] == 'weekly_composition'
    
    def test_compose_daily_brief_context_formatting(self, test_settings, sample_fact_cards):
        """Test that fact cards are properly formatted in context."""
        composer = DailyBriefComposer(test_settings)
        
        buckets = {"top_stories": sample_fact_cards[:2], "macro_policy": [], "company_markets": [], "watchlist": []}
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"headline": "Test", "intro": "Test", "preheader": "Test", "top5_md": "Test", "macro_md": "Test", "watchlist_md": "Test", "snapshot_md": "Test"})
        
        with patch.object(composer.ai, 'responses_create', return_value=mock_response) as mock_create:
            composer.compose_daily_brief(buckets)
        
        # Verify prompt includes fact card details
        call_args = mock_create.call_args
        prompt = call_args[1]['messages'][1]['content']
        
        # Should include entity names
        assert "Federal Reserve" in prompt
        assert "NVIDIA" in prompt
