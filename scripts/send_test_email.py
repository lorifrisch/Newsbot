import sys
import os
from datetime import datetime
import logging

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import Settings
from src.mailer import NewsMailer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    try:
        # 1. Load settings
        print("Loading settings...")
        settings = Settings.load()
        
        # 2. Instantiate mailer
        print("Initializing mailer...")
        mailer = NewsMailer(settings)
        
        # 3. Define mock context
        now = datetime.now()
        date_str = now.strftime("%A, %b %d, %Y")
        time_str = now.strftime("%H:%M %Z")
        
        mock_context = {
            "subject": "Markets Brief - Test Run",
            "preheader": "Your daily market insights are ready. Check out the top 5 updates.",
            "brand_name": settings.app.brand_name,
            "date_label": date_str,
            "headline_title": "Nvidia Hits New High, Fed Keeps Rates Policy Steady",
            "generated_time": time_str,
            "intro_paragraph": "Markets opened higher this morning as tech continued its rally. Here is what you need to know before the closing bell.",
            "top5_html": """
                <ul style="padding-left:20px; margin:0; font-family:sans-serif; font-size:14px; line-height:21px; color:#374151;">
                    <li style="margin-bottom:8px;"><strong>NVDA:</strong> Reached an all-time high of $1,200 after strong earnings forecasts. <a href="#" style="color:#2563eb;">Source</a></li>
                    <li style="margin-bottom:8px;"><strong>FOMC:</strong> Minutes reveal a cautious stance on inflation but no immediate hikes. <a href="#" style="color:#2563eb;">Source</a></li>
                    <li style="margin-bottom:8px;"><strong>Oil:</strong> WTI drops 2% as inventory builds exceed expectations. <a href="#" style="color:#2563eb;">Source</a></li>
                    <li style="margin-bottom:8px;"><strong>Jobs:</strong> Non-farm payrolls came in slightly higher than the 200k estimated. <a href="#" style="color:#2563eb;">Source</a></li>
                    <li style="margin-bottom:8px;"><strong>Retail:</strong> Consumer spending remains resilient despite high interest rates. <a href="#" style="color:#2563eb;">Source</a></li>
                </ul>
            """,
            "macro_html": """
                <div style="font-family:sans-serif; font-size:14px; line-height:21px; color:#374151;">
                    <p>The US Dollar Index (DXY) remained flat as traders weighed mixed economic signals. In Europe, the ECB hinted at a potential rate cut in June if inflation targets remain on track.</p>
                </div>
            """,
            "snapshot_html": """
                <table width="100%" cellspacing="0" cellpadding="8" border="0" style="font-family:sans-serif; font-size:13px; color:#111827; border: 1px solid #e5e7eb; border-radius: 8px;">
                    <tr style="background-color:#f9fafb;">
                        <th align="left">Index</th>
                        <th align="right">Value</th>
                        <th align="right">Change</th>
                    </tr>
                    <tr>
                        <td>S&P 500</td>
                        <td align="right">5,350.20</td>
                        <td align="right" style="color:#059669;">+0.45%</td>
                    </tr>
                    <tr>
                        <td>Nasdaq 100</td>
                        <td align="right">19,020.10</td>
                        <td align="right" style="color:#059669;">+0.82%</td>
                    </tr>
                    <tr>
                        <td>Gold</td>
                        <td align="right">$2,340.50</td>
                        <td align="right" style="color:#dc2626;">-0.12%</td>
                    </tr>
                </table>
            """,
            "watchlist_label": "Your selected tickers",
            "watchlist_html": """
                <div style="display:flex; flex-wrap:wrap; gap:10px; font-family:sans-serif; font-size:12px;">
                    <span style="background:#f3f4f6; padding:4px 8px; border-radius:4px;">AAPL: +1.2%</span>
                    <span style="background:#f3f4f6; padding:4px 8px; border-radius:4px;">TSLA: -0.5%</span>
                    <span style="background:#f3f4f6; padding:4px 8px; border-radius:4px;">MSFT: +0.3%</span>
                </div>
            """,
            "archive_url": "https://example.com/archive",
            "preferences_url": "https://example.com/preferences",
            "footer_note": "Sent by Lori Invest automated news service.",
            "unsubscribe_line": "If you wish to stop receiving these, <a href='#'>click here to unsubscribe</a>."
        }
        
        # 4. Render HTML
        print("Rendering template...")
        html_content = mailer.render_content("email_template.html", mock_context)
        
        # 5. Send email
        print(f"Sending email to {settings.email.to_email}...")
        success = mailer.send_email(
            subject=mock_context["subject"],
            html_content=html_content
        )
        
        if success:
            print("SUCCESS: Test email sent!")
        else:
            print("ERROR: Failed to send test email. Check logs.")
            sys.exit(1)
            
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
