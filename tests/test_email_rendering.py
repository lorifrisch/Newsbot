"""
Unit tests for email rendering functionality.

Tests:
- HTML content is not escaped in dynamic sections
- PDF mode does not include dark-mode meta tags
- Both modes render valid HTML structure
"""

import os
import pytest
from pathlib import Path
from datetime import datetime
from src.config import Settings
from src.mailer import NewsMailer
from src.templates import EmailFormatter


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables once for all tests."""
    # Set dummy environment variables for testing
    os.environ.setdefault("SENDGRID_API_KEY", "dummy_key_for_testing")
    os.environ.setdefault("OPENAI_API_KEY", "dummy_key_for_testing")
    os.environ.setdefault("PERPLEXITY_API_KEY", "dummy_key_for_testing")
    os.environ.setdefault("EMAIL_FROM", "test@example.com")
    os.environ.setdefault("EMAIL_TO", "test@example.com")


@pytest.fixture
def settings():
    """Create settings instance for testing."""
    return Settings.load()


@pytest.fixture
def mailer(settings):
    """Create NewsMailer instance for testing."""
    return NewsMailer(settings)


@pytest.fixture
def formatter():
    """Create EmailFormatter instance for testing."""
    return EmailFormatter()


@pytest.fixture
def sample_context(formatter):
    """Create sample email context with HTML content."""
    return {
        "headline_title": "Test Market Brief",
        "intro_paragraph": "Sample introduction paragraph for testing.",
        "top5_html": formatter.md_to_html("### Test Story\n\nSample content with **bold** text."),
        "macro_html": formatter.md_to_html("### Macro Analysis\n\nCentral banks maintain policy stance."),
        "snapshot_html": '<table style="width:100%;"><tr><td><strong>Index</strong></td><td>Value</td></tr></table>',
        "watchlist_html": formatter.md_to_html("### Watchlist\n\n**AAPL**: Positive outlook"),
        "sentiment_html": '<div style="background-color:#ecfdf5;padding:16px;"><span>🟢 Risk-On</span></div>',
        "preheader": "Test preheader text",
        "date_label": datetime.now().strftime("%A, %b %d, %Y"),
        "generated_time": datetime.now().strftime("%H:%M %Z"),
        "archive_url": "#",
        "preferences_url": "#"
    }


def test_html_not_escaped(mailer, sample_context):
    """
    Test that HTML content in dynamic sections is not escaped.
    
    Ensures that markdown-generated HTML and raw HTML strings
    are rendered correctly without &lt; &gt; escaping.
    """
    html = mailer.render_content("email_template.html", sample_context, render_mode="email")
    
    # Check for common escaped HTML patterns
    assert "&lt;p" not in html, "Found escaped <p> tag"
    assert "&lt;div" not in html, "Found escaped <div> tag"
    assert "&lt;table" not in html, "Found escaped <table> tag"
    assert "&lt;strong" not in html, "Found escaped <strong> tag"
    assert "&lt;span" not in html, "Found escaped <span> tag"
    
    # Verify actual HTML tags are present
    assert "<p" in html or "<div" in html, "No HTML tags found in output"
    assert "<table" in html, "Expected table tag not found"
    assert "<strong>" in html, "Expected strong tag not found"


def test_pdf_mode_no_color_scheme(mailer, sample_context):
    """
    Test that PDF mode does not include color-scheme meta tags.
    
    Ensures that dark mode meta tags are excluded to prevent
    white-on-white text in PDF rendering.
    """
    pdf_html = mailer.render_content("email_template.html", sample_context, render_mode="pdf")
    
    # Check that color-scheme meta tags are NOT present
    assert 'name="color-scheme"' not in pdf_html, "PDF mode should not have color-scheme meta tag"
    assert 'name="supported-color-schemes"' not in pdf_html, "PDF mode should not have supported-color-schemes meta tag"
    
    # Verify explicit text color is set for PDF
    assert 'color: #111827 !important' in pdf_html, "PDF mode should have explicit body text color"


def test_email_mode_has_color_scheme(mailer, sample_context):
    """
    Test that email mode includes color-scheme meta tags.
    
    Ensures that email clients receive proper dark mode support.
    """
    email_html = mailer.render_content("email_template.html", sample_context, render_mode="email")
    
    # Check that color-scheme meta tags ARE present in email mode
    assert 'name="color-scheme"' in email_html, "Email mode should have color-scheme meta tag"
    assert 'name="supported-color-schemes"' in email_html, "Email mode should have supported-color-schemes meta tag"


def test_both_modes_have_valid_structure(mailer, sample_context):
    """
    Test that both email and PDF modes produce valid HTML structure.
    
    Ensures basic HTML structure is present in both rendering modes.
    """
    for mode in ["email", "pdf"]:
        html = mailer.render_content("email_template.html", sample_context, render_mode=mode)
        
        # Check basic HTML structure
        assert "<!doctype html>" in html.lower(), f"{mode} mode: Missing doctype"
        assert "<html" in html.lower(), f"{mode} mode: Missing html tag"
        assert "<head>" in html.lower(), f"{mode} mode: Missing head tag"
        assert "<body" in html.lower(), f"{mode} mode: Missing body tag"
        assert "</html>" in html.lower(), f"{mode} mode: Missing closing html tag"
        
        # Check that content is present
        assert sample_context["headline_title"] in html, f"{mode} mode: Headline not found"
        assert sample_context["intro_paragraph"] in html, f"{mode} mode: Intro not found"


def test_markdown_to_html_conversion(formatter):
    """
    Test that EmailFormatter correctly converts markdown to HTML.
    
    Ensures markdown conversion produces inline-styled HTML suitable for emails.
    """
    markdown = "### Test Heading\n\nThis is a **bold** paragraph."
    html = formatter.md_to_html(markdown)
    
    # Check that HTML was generated
    assert "<" in html and ">" in html, "No HTML tags generated"
    assert "bold" in html or "<strong>" in html or "<b>" in html, "Bold formatting not applied"
    
    # Check for inline styles (email-safe)
    assert "style=" in html, "No inline styles found (required for email clients)"


def test_sentiment_html_injection(mailer, sample_context):
    """
    Test that raw HTML in sentiment_html is properly rendered without escaping.
    
    Ensures that the sentiment gauge HTML is injected correctly.
    """
    html = mailer.render_content("email_template.html", sample_context, render_mode="email")
    
    # Verify sentiment HTML is present and not escaped
    assert "🟢 Risk-On" in html, "Sentiment text not found"
    assert '&lt;div style="background-color:#ecfdf5' not in html, "Sentiment HTML is escaped"
    assert '<div style="background-color:#ecfdf5' in html, "Sentiment HTML not properly injected"


def test_empty_optional_sections(mailer):
    """
    Test that optional sections (like sentiment) can be omitted without errors.
    """
    minimal_context = {
        "headline_title": "Test",
        "intro_paragraph": "Test intro",
        "top5_html": "<p>Test</p>",
        "macro_html": "<p>Test</p>",
        "snapshot_html": "<table></table>",
        "watchlist_html": "<p>Test</p>",
        "sentiment_html": "",  # Empty sentiment
        "preheader": "Test",
        "date_label": "Monday, Jan 01, 2026",
        "generated_time": "12:00 UTC",
        "archive_url": "#",
        "preferences_url": "#"
    }
    
    html = mailer.render_content("email_template.html", minimal_context, render_mode="email")
    
    # Should render without errors
    assert "Test" in html
    assert len(html) > 1000, "HTML output seems too short"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
