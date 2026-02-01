import markdown2
import re
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from datetime import datetime

class EmailFormatter:
    """
    Handles formatting of markdown content into email-safe HTML with inline styles.
    """
    
    def __init__(self):
        # Define inline styles for common HTML tags to ensure good rendering in email clients
        self.styles = {
            'ul': 'padding-left: 20px; margin-top: 0; margin-bottom: 15px; color: #374151;',
            'li': 'margin-bottom: 10px; line-height: 1.6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; font-size: 15px; color: #374151;',
            'strong': 'color: #111827; font-weight: 600;',
            'p': 'margin-top: 0; margin-bottom: 14px; line-height: 1.6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; font-size: 15px; color: #374151;',
            'a': 'color: #2563eb; text-decoration: underline;',
            'code': 'background-color: #f3f4f6; padding: 2px 4px; border-radius: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 13px; color: #374151;',
            'table': 'width: 100%; border-collapse: collapse; margin-bottom: 15px; font-size: 14px; border: 1px solid #e5e7eb; color: #374151;',
            'th': 'background-color: #f8fafc; border: 1px solid #e5e7eb; padding: 8px; text-align: left; font-weight: 600; color: #475569;',
            'td': 'border: 1px solid #e5e7eb; padding: 8px; text-align: left; color: #374151;'
        }
        
        # Setup Jinja2 environment for email templates
        template_dir = Path(__file__).parent / 'templates'
        self.jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))

    def _convert_markdown_links(self, text: str) -> str:
        """
        Convert Markdown links [text](url) to HTML anchor tags with styling.
        This runs BEFORE markdown2 processing to ensure proper handling.
        """
        # Pattern for Markdown links: [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        
        def replace_link(match):
            link_text = match.group(1)
            url = match.group(2)
            # Apply inline style for email compatibility
            style = self.styles.get('a', 'color: #2563eb; text-decoration: underline;')
            return f'<a href="{url}" style="{style}" target="_blank">{link_text}</a>'
        
        return re.sub(link_pattern, replace_link, text)

    def md_to_html(self, md_text: str) -> str:
        """
        Converts Markdown text to HTML and injects inline styles for email clients.
        Uses markdown2 extras like tables and implements Outlook-proof bullets.
        Handles Markdown links [text](url) converting them to clickable <a> tags.
        """
        if not md_text:
            return ""
        
        # First, convert Markdown links to HTML anchors (before markdown2 processing)
        # This ensures our links are preserved with proper styling
        text_with_links = self._convert_markdown_links(md_text)
        
        # Convert MD to HTML with extras
        html = markdown2.markdown(text_with_links, extras=["tables", "break-on-newline"])
        
        # Apply standard inline styles (skip 'a' since we handled it above)
        for tag, style in self.styles.items():
            if tag != 'a':  # Skip anchor tags, already styled
                html = html.replace(f'<{tag}>', f'<{tag} style="{style}">')

        # Outlook/Gmail-friendly bullet replacement for <li>
        # Replace <li>...</li> with <div>• ...</div> for better consistency
        li_style = self.styles.get('li', '')
        html = html.replace('<li style="' + li_style + '">', f'<div style="{li_style}"><span style="color: #3b82f6; margin-right: 8px;">•</span>')
        html = html.replace('</li>', '</div>')
        
        # Remove <ul> tags as they are now redundant with our <div> bullets
        html = html.replace('<ul style="' + self.styles.get('ul', '') + '">', '<div>')
        html = html.replace('</ul>', '</div>')
            
        return html
    
    def count_clickable_links(self, html_content: str) -> int:
        """
        Count the number of clickable links (<a href=...>) in HTML content.
        Useful for quality metrics.
        """
        pattern = r'<a\s+[^>]*href\s*=\s*["\'][^"\']+["\'][^>]*>'
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        return len(matches)

    def render_weekly_email(
        self,
        theme_html: str,
        top_developments_html: str,
        next_week_html: str,
        date_range: str
    ) -> str:
        """
        Renders the weekly recap email using simplified template structure.
        
        Args:
            theme_html: HTML for the theme of the week section
            top_developments_html: HTML for the top developments list
            next_week_html: HTML for the next week outlook
            date_range: String like "Jan 23 - Jan 30, 2026"
            
        Returns:
            Complete HTML email body
        """
        template = self.jinja_env.get_template('weekly_email_template.html')
        
        return template.render(
            date_range=date_range,
            theme_html=theme_html,
            top_developments_html=top_developments_html,
            next_week_html=next_week_html,
            generated_time=datetime.now().strftime('%H:%M %Z')
        )
