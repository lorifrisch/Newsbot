#!/usr/bin/env python3
"""
Sample Email Rendering Script

Tests both email and PDF rendering modes with sample data.
Validates that HTML content is not escaped and PDF mode has proper styling.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import Settings
from src.mailer import NewsMailer
from src.templates import EmailFormatter

def main():
    print("🎨 Sample Email Rendering Test\n")
    
    # Set minimal environment variables for testing (if not already set)
    if "SENDGRID_API_KEY" not in os.environ:
        os.environ["SENDGRID_API_KEY"] = "dummy_key_for_testing"
    if "OPENAI_API_KEY" not in os.environ:
        os.environ["OPENAI_API_KEY"] = "dummy_key_for_testing"
    if "PERPLEXITY_API_KEY" not in os.environ:
        os.environ["PERPLEXITY_API_KEY"] = "dummy_key_for_testing"
    if "EMAIL_FROM" not in os.environ:
        os.environ["EMAIL_FROM"] = "test@example.com"
    if "EMAIL_TO" not in os.environ:
        os.environ["EMAIL_TO"] = "test@example.com"
    
    # Initialize components - use Settings.load() to load from YAML
    settings = Settings.load()
    mailer = NewsMailer(settings)
    formatter = EmailFormatter()
    
    # Create sample data
    sample_markdown = """
## Strong Economic Data

The latest employment figures show robust job creation, with non-farm payrolls increasing by 250K positions. Unemployment rate remained steady at 3.8%.

### Key Metrics
- Job growth: +250K
- Unemployment: 3.8%
- Wage growth: +4.2% YoY
"""
    
    sample_context = {
        "headline_title": "Markets Rally on Strong Economic Data",
        "intro_paragraph": "Global equities advanced as investors digested stronger-than-expected economic indicators, while central banks maintained their cautious stance on monetary policy.",
        "top5_html": formatter.md_to_html(sample_markdown),
        "macro_html": formatter.md_to_html("### Federal Reserve maintains rates\n\nThe FOMC held interest rates steady at 5.25-5.50%, signaling data-dependent approach."),
        "snapshot_html": '<table style="width:100%;border-collapse:collapse;"><tr><td style="padding:8px;border-bottom:1px solid #e2e8f0;"><strong>S&P 500</strong></td><td style="padding:8px;border-bottom:1px solid #e2e8f0;text-align:right;color:#16a34a;">+1.2%</td></tr><tr><td style="padding:8px;border-bottom:1px solid #e2e8f0;"><strong>Nasdaq</strong></td><td style="padding:8px;border-bottom:1px solid #e2e8f0;text-align:right;color:#16a34a;">+1.8%</td></tr></table>',
        "watchlist_html": formatter.md_to_html("### Tech Sector Leaders\n\n**AAPL**: New iPhone launch drives optimism\n**MSFT**: Cloud revenue beats estimates"),
        "sentiment_html": '<div style="background-color:#ecfdf5;border:1px solid #86efac;border-radius:8px;padding:16px;"><div style="display:flex;align-items:center;justify-content:space-between;"><div style="font-size:14px;font-weight:700;color:#16a34a;">🟢 Risk-On</div><div style="font-size:12px;color:#6b7280;">Bullish sentiment across major indices</div></div></div>',
        "preheader": "Markets rally on strong economic data and positive earnings",
        "date_label": datetime.now().strftime("%A, %b %d, %Y"),
        "generated_time": datetime.now().strftime("%H:%M %Z"),
        "archive_url": "#",
        "preferences_url": "#"
    }
    
    # Ensure output directory exists
    out_dir = project_root / "out"
    out_dir.mkdir(exist_ok=True)
    
    # Test 1: Email mode
    print("📧 Test 1: Email mode rendering...")
    email_html = mailer.render_content("email_template.html", sample_context, render_mode="email")
    email_output = out_dir / "sample_email.html"
    email_output.write_text(email_html, encoding="utf-8")
    
    # Validate email mode
    escaped_count = email_html.count("&lt;")
    if escaped_count > 0:
        print(f"   ❌ FAIL: Found {escaped_count} escaped HTML sequences (&lt;)")
        # Show example
        idx = email_html.find("&lt;")
        if idx >= 0:
            snippet = email_html[max(0, idx-50):min(len(email_html), idx+150)]
            print(f"   Example: ...{snippet}...")
    else:
        print(f"   ✅ PASS: No escaped HTML sequences found")
    
    if 'color-scheme' in email_html:
        print(f"   ✅ PASS: Color-scheme meta tag present for email clients")
    
    print(f"   📄 Saved to: {email_output}")
    print(f"   📊 Size: {len(email_html):,} bytes\n")
    
    # Test 2: PDF mode
    print("📄 Test 2: PDF mode rendering...")
    pdf_html = mailer.render_content("email_template.html", sample_context, render_mode="pdf")
    pdf_output = out_dir / "sample_pdf.html"
    pdf_output.write_text(pdf_html, encoding="utf-8")
    
    # Validate PDF mode
    escaped_count_pdf = pdf_html.count("&lt;")
    if escaped_count_pdf > 0:
        print(f"   ❌ FAIL: Found {escaped_count_pdf} escaped HTML sequences (&lt;)")
    else:
        print(f"   ✅ PASS: No escaped HTML sequences found")
    
    if 'color-scheme' in pdf_html:
        print(f"   ❌ FAIL: Color-scheme meta tag should not be present in PDF mode")
    else:
        print(f"   ✅ PASS: No color-scheme meta tag (prevents dark mode issues)")
    
    if 'color: #111827 !important' in pdf_html:
        print(f"   ✅ PASS: Explicit body text color for PDF rendering")
    
    print(f"   📄 Saved to: {pdf_output}")
    print(f"   📊 Size: {len(pdf_html):,} bytes\n")
    
    # Summary
    total_tests = 4
    passed_tests = 0
    
    if email_html.count("&lt;") == 0:
        passed_tests += 1
    if pdf_html.count("&lt;") == 0:
        passed_tests += 1
    if 'color-scheme' not in pdf_html:
        passed_tests += 1
    if 'color: #111827 !important' in pdf_html:
        passed_tests += 1
    
    print(f"📊 Summary: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("✅ All rendering tests passed!")
        return 0
    else:
        print(f"❌ {total_tests - passed_tests} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
