"""
Integration tests for end-to-end workflow.

Tests the complete daily brief workflow with mocked external
dependencies (Perplexity, OpenAI, SendGrid). Validates that all
phases execute correctly and handle failures gracefully.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import workflow function
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.integration
class TestDailyWorkflowIntegration:
    """Integration tests for complete daily workflow."""
    
    def test_daily_workflow_e2e_success(
        self,
        test_settings,
        temp_db,
        temp_run_dir,
        mock_perplexity_response,
        mock_openai_extraction_response,
        mock_openai_composition_response,
        mock_sendgrid_client
    ):
        """
        Test successful end-to-end daily workflow execution.
        All phases should complete successfully.
        """
        from run_daily import run_daily_workflow
        
        # Mock all external dependencies
        with patch('src.retrieval.PerplexityClient') as MockPerplexity, \
             patch('src.openai_client.OpenAIClient') as MockOpenAI, \
             patch('src.mailer.SendGridAPIClient', return_value=mock_sendgrid_client), \
             patch('src.logging_utils.setup_logging', return_value=("test_run", temp_run_dir)), \
             patch('src.config.Settings.load', return_value=test_settings):
            
            # Configure Perplexity mock
            mock_pplx_instance = MockPerplexity.return_value
            mock_pplx_instance.chat.return_value = mock_perplexity_response
            
            # Configure OpenAI mock
            mock_openai_instance = MockOpenAI.return_value
            
            # Mock extraction response
            extraction_response = MagicMock()
            extraction_response.choices = [MagicMock()]
            extraction_response.choices[0].message.content = json.dumps(mock_openai_extraction_response)
            extraction_response.usage = MagicMock(prompt_tokens=100, completion_tokens=200, total_tokens=300)
            
            # Mock composition response
            composition_response = MagicMock()
            composition_response.choices = [MagicMock()]
            composition_response.choices[0].message.content = json.dumps(mock_openai_composition_response)
            composition_response.usage = MagicMock(prompt_tokens=150, completion_tokens=250, total_tokens=400)
            
            mock_openai_instance.responses_create.side_effect = [extraction_response, composition_response]
            
            # Execute workflow in dry-run mode (no actual email send)
            success = run_daily_workflow(dry_run=True)
        
        # Verify workflow completed successfully
        assert success is True
        
        # Verify Perplexity was called for all 6 queries
        assert mock_pplx_instance.chat.call_count == 6
        
        # Verify OpenAI was called for extraction and composition
        assert mock_openai_instance.responses_create.call_count == 2
        
        # Verify email was not sent (dry-run mode)
        mock_sendgrid_client.send.assert_not_called()
    
    def test_daily_workflow_circuit_breaker(
        self,
        test_settings,
        temp_db,
        temp_run_dir
    ):
        """
        Test circuit breaker stops workflow after 2 consecutive failures.
        """
        from run_daily import run_daily_workflow
        
        with patch('src.retrieval.PerplexityClient') as MockPerplexity, \
             patch('src.logging_utils.setup_logging', return_value=("test_run", temp_run_dir)), \
             patch('src.config.Settings.load', return_value=test_settings):
            
            # Configure first 2 queries to fail
            mock_pplx_instance = MockPerplexity.return_value
            mock_pplx_instance.chat.side_effect = [
                Exception("API Error 1"),
                Exception("API Error 2")
            ]
            
            # Execute workflow
            success = run_daily_workflow(dry_run=True)
        
        # Workflow should abort due to circuit breaker
        assert success is False
        
        # Should only attempt 2 queries (circuit breaker triggers)
        assert mock_pplx_instance.chat.call_count == 2
    
    def test_daily_workflow_insufficient_queries(
        self,
        test_settings,
        temp_db,
        temp_run_dir,
        mock_perplexity_response
    ):
        """
        Test workflow aborts when only 2/6 queries succeed (below threshold).
        """
        from run_daily import run_daily_workflow
        
        with patch('src.retrieval.PerplexityClient') as MockPerplexity, \
             patch('src.logging_utils.setup_logging', return_value=("test_run", temp_run_dir)), \
             patch('src.config.Settings.load', return_value=test_settings):
            
            # Configure 2 successes, 4 failures (non-consecutive to avoid circuit breaker)
            call_count = [0]
            def mock_chat_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] in [1, 3]:  # Queries 1 and 3 succeed
                    return mock_perplexity_response
                raise Exception("API Error")
            
            mock_pplx_instance = MockPerplexity.return_value
            mock_pplx_instance.chat.side_effect = mock_chat_side_effect
            
            # Execute workflow
            success = run_daily_workflow(dry_run=True)
        
        # Workflow should abort (insufficient queries)
        assert success is False
    
    def test_daily_workflow_extraction_failure(
        self,
        test_settings,
        temp_db,
        temp_run_dir,
        mock_perplexity_response
    ):
        """
        Test workflow handles extraction failure gracefully.
        """
        from run_daily import run_daily_workflow
        
        with patch('src.retrieval.PerplexityClient') as MockPerplexity, \
             patch('src.openai_client.OpenAIClient') as MockOpenAI, \
             patch('src.logging_utils.setup_logging', return_value=("test_run", temp_run_dir)), \
             patch('src.config.Settings.load', return_value=test_settings):
            
            # Retrieval succeeds
            mock_pplx_instance = MockPerplexity.return_value
            mock_pplx_instance.chat.return_value = mock_perplexity_response
            
            # Extraction fails
            mock_openai_instance = MockOpenAI.return_value
            mock_openai_instance.responses_create.side_effect = Exception("OpenAI API Error")
            
            # Execute workflow
            success = run_daily_workflow(dry_run=True)
        
        # Workflow should abort after extraction failure
        assert success is False
    
    def test_daily_workflow_email_failure(
        self,
        test_settings,
        temp_db,
        temp_run_dir,
        mock_perplexity_response,
        mock_openai_extraction_response,
        mock_openai_composition_response
    ):
        """
        Test workflow handles email send failure in production mode.
        """
        from run_daily import run_daily_workflow
        
        with patch('src.retrieval.PerplexityClient') as MockPerplexity, \
             patch('src.openai_client.OpenAIClient') as MockOpenAI, \
             patch('src.mailer.SendGridAPIClient') as MockSendGrid, \
             patch('src.logging_utils.setup_logging', return_value=("test_run", temp_run_dir)), \
             patch('src.config.Settings.load', return_value=test_settings):
            
            # Retrieval succeeds
            mock_pplx_instance = MockPerplexity.return_value
            mock_pplx_instance.chat.return_value = mock_perplexity_response
            
            # Extraction and composition succeed
            mock_openai_instance = MockOpenAI.return_value
            extraction_response = MagicMock()
            extraction_response.choices = [MagicMock()]
            extraction_response.choices[0].message.content = json.dumps(mock_openai_extraction_response)
            extraction_response.usage = MagicMock(prompt_tokens=100, completion_tokens=200, total_tokens=300)
            
            composition_response = MagicMock()
            composition_response.choices = [MagicMock()]
            composition_response.choices[0].message.content = json.dumps(mock_openai_composition_response)
            composition_response.usage = MagicMock(prompt_tokens=150, completion_tokens=250, total_tokens=400)
            
            mock_openai_instance.responses_create.side_effect = [extraction_response, composition_response]
            
            # Email fails (all retries exhausted)
            mock_sg_instance = MockSendGrid.return_value
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_sg_instance.send.return_value = mock_response
            
            # Execute workflow in production mode
            success = run_daily_workflow(dry_run=False)
        
        # Workflow should fail due to email error
        assert success is False
        
        # Email should have been attempted with retries (4 total: 1 initial + 3 retries)
        assert mock_sg_instance.send.call_count == 4
    
    def test_daily_workflow_dry_run_mode(
        self,
        test_settings,
        temp_db,
        temp_run_dir,
        mock_perplexity_response,
        mock_openai_extraction_response,
        mock_openai_composition_response,
        mock_sendgrid_client
    ):
        """
        Test dry-run mode generates artifacts but doesn't send email.
        """
        from run_daily import run_daily_workflow
        
        with patch('src.retrieval.PerplexityClient') as MockPerplexity, \
             patch('src.openai_client.OpenAIClient') as MockOpenAI, \
             patch('src.mailer.SendGridAPIClient', return_value=mock_sendgrid_client), \
             patch('src.logging_utils.setup_logging', return_value=("test_run", temp_run_dir)), \
             patch('src.config.Settings.load', return_value=test_settings):
            
            # Configure mocks for success
            mock_pplx_instance = MockPerplexity.return_value
            mock_pplx_instance.chat.return_value = mock_perplexity_response
            
            mock_openai_instance = MockOpenAI.return_value
            extraction_response = MagicMock()
            extraction_response.choices = [MagicMock()]
            extraction_response.choices[0].message.content = json.dumps(mock_openai_extraction_response)
            extraction_response.usage = MagicMock(prompt_tokens=100, completion_tokens=200, total_tokens=300)
            
            composition_response = MagicMock()
            composition_response.choices = [MagicMock()]
            composition_response.choices[0].message.content = json.dumps(mock_openai_composition_response)
            composition_response.usage = MagicMock(prompt_tokens=150, completion_tokens=250, total_tokens=400)
            
            mock_openai_instance.responses_create.side_effect = [extraction_response, composition_response]
            
            # Execute in dry-run mode
            success = run_daily_workflow(dry_run=True)
        
        # Workflow should succeed
        assert success is True
        
        # Email should NOT be sent
        mock_sendgrid_client.send.assert_not_called()
        
        # Verify other phases executed
        assert mock_pplx_instance.chat.call_count == 6
        assert mock_openai_instance.responses_create.call_count == 2


@pytest.mark.integration
@pytest.mark.slow
class TestWeeklyWorkflowIntegration:
    """Integration tests for weekly workflow."""
    
    def test_weekly_workflow_metadata_save_order(
        self,
        test_settings,
        temp_db,
        temp_run_dir,
        mock_openai_composition_response,
        mock_sendgrid_client
    ):
        """
        Test that metadata is saved BEFORE email send attempt.
        This ensures metadata isn't lost if email fails.
        """
        from run_weekly import run_weekly_workflow
        
        # Create some test fact cards in database
        from src.storage import NewsStorage
        db = NewsStorage(temp_db)
        db.init_db()
        
        # Insert sample fact cards
        db.insert_fact_cards([
            {
                "story_id": "test_1",
                "entity": "Test Entity",
                "trend": "Test Trend",
                "data_point": "100%",
                "why_it_matters": "Test matter",
                "confidence": 0.9,
                "tickers": ["TEST"],
                "sources": ["Test Source"],
                "urls": ["https://test.com"],
                "retrieved_at": "2026-01-31T10:00:00"
            }
        ])
        
        with patch('src.openai_client.OpenAIClient') as MockOpenAI, \
             patch('src.mailer.SendGridAPIClient', return_value=mock_sendgrid_client), \
             patch('src.logging_utils.setup_logging', return_value=("test_run", temp_run_dir)), \
             patch('src.config.Settings.load', return_value=test_settings):
            
            # Mock OpenAI composition
            mock_openai_instance = MockOpenAI.return_value
            composition_response = MagicMock()
            composition_response.choices = [MagicMock()]
            
            # Create weekly-specific response
            weekly_response = {
                "headline": "Weekly Recap",
                "preheader": "Test",
                "intro": "Test intro",
                "theme_of_week": "Test theme",
                "top_developments": [{"headline": "Dev 1", "explanation": "Explanation"}],
                "next_week_outlook": "Outlook"
            }
            
            composition_response.choices[0].message.content = json.dumps(weekly_response)
            composition_response.usage = MagicMock(prompt_tokens=150, completion_tokens=250, total_tokens=400)
            mock_openai_instance.responses_create.return_value = composition_response
            
            # Configure email to fail
            mock_sendgrid_client.send.return_value = MagicMock(status_code=503)
            
            # Execute workflow (should fail on email but metadata should be saved)
            # Note: We expect this to exit with sys.exit(1), so we catch that
            with pytest.raises(SystemExit):
                run_weekly_workflow(dry_run=False)
        
        # Verify metadata was saved before email failure
        # (This validates the order fix from Issue 19)
        reports = db.dataset["reports"].all()
        assert len(reports) > 0
        assert reports[0]["kind"] == "weekly_recap"
