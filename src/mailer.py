import logging
import time
import random
import base64
from typing import Dict, Any, Optional, List, Tuple
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType, Disposition, ContentId
from src.config import Settings

logger = logging.getLogger(__name__)

class NewsMailer:
    """
    Handles rendering news briefs via Jinja2 and sending them via SendGrid.
    Supports both base64 inline images and CID attachments for charts.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.email_config = settings.email
        
        # Chart embedding method: "base64" (inline) or "cid" (attachment, more reliable)
        self.chart_embed_method = getattr(self.email_config, 'chart_embed_method', 'cid')
        
        # Initialize Jinja2 environment
        # Assuming templates are in src/templates relative to the project root
        self.jinja_env = Environment(
            loader=FileSystemLoader("src/templates"),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        # Initialize SendGrid client
        self.sg_client = SendGridAPIClient(api_key=self.email_config.api_key.get_secret_value())

    def render_content(self, template_name: str, context: Dict[str, Any], render_mode: str = "email") -> str:
        """
        Renders an HTML template with the provided context.
        
        Args:
            template_name: Name of the template file (or use default based on render_mode)
            context: Dictionary of template variables
            render_mode: "email" (default) for email clients, "pdf" for PDF generation
        
        Returns:
            Rendered HTML string
        """
        try:
            # If template_name is the base template, select appropriate version based on render_mode
            if template_name == "email_template.html" and render_mode == "pdf":
                template_name = "email_template_pdf.html"
            
            template = self.jinja_env.get_template(template_name)
            # Add some defaults to context if missing
            context.setdefault("brand_name", self.settings.app.brand_name)
            rendered = template.render(**context)
            
            # Debug logging: check for escaped HTML sequences
            if "&lt;" in rendered or "&gt;" in rendered:
                logger.warning(f"Detected escaped HTML sequences in rendered template (render_mode={render_mode})")
                
            return rendered
        except Exception as e:
            logger.error(f"Failed to render template {template_name}: {e}")
            raise

    def prepare_charts_for_email(
        self, 
        charts: Dict[str, str]
    ) -> Tuple[Dict[str, str], List[Attachment]]:
        """
        Prepares chart images for email embedding.
        
        Args:
            charts: Dict of {chart_name: base64_png_data}
            
        Returns:
            Tuple of (updated_chart_refs, attachments)
            - updated_chart_refs: Dict mapping chart_name to either data URI or cid: reference
            - attachments: List of SendGrid Attachment objects (only for CID method)
        """
        updated_refs = {}
        attachments = []
        
        for name, base64_data in charts.items():
            if self.chart_embed_method == 'cid':
                # CID attachment method (more reliable across email clients)
                content_id = f"chart_{name}"
                
                attachment = Attachment()
                attachment.file_content = FileContent(base64_data)
                attachment.file_type = FileType('image/png')
                attachment.file_name = FileName(f'{name}.png')
                attachment.disposition = Disposition('inline')
                attachment.content_id = ContentId(content_id)
                
                attachments.append(attachment)
                updated_refs[name] = f"cid:{content_id}"
                logger.debug(f"Chart '{name}' prepared as CID attachment: cid:{content_id}")
            else:
                # Base64 inline method (simpler but less reliable)
                updated_refs[name] = f"data:image/png;base64,{base64_data}"
                logger.debug(f"Chart '{name}' prepared as base64 inline image")
        
        return updated_refs, attachments

    def send_email(
        self, 
        subject: str, 
        html_content: str, 
        to_email: Optional[str] = None,
        from_email: Optional[str] = None,
        attachments: Optional[List[Attachment]] = None
    ) -> bool:
        """
        Sends an email using SendGrid with retry logic.
        Retries up to 3 times with exponential backoff and jitter.
        
        Args:
            subject: Email subject
            html_content: HTML body content
            to_email: Recipient email (defaults to config)
            from_email: Sender email (defaults to config)
            attachments: Optional list of SendGrid Attachment objects (for CID images)
        """
        from_email = from_email or self.email_config.from_email
        to_email = to_email or self.email_config.to_email
        
        full_subject = f"{self.email_config.subject_prefix} {subject}" if not subject.startswith(self.email_config.subject_prefix) else subject

        message = Mail(
            from_email=Email(from_email),
            to_emails=To(to_email),
            subject=full_subject,
            html_content=Content("text/html", html_content)
        )
        
        # Add attachments for CID images
        if attachments:
            for attachment in attachments:
                message.add_attachment(attachment)
            logger.info(f"Added {len(attachments)} CID attachments to email")

        max_retries = 3
        retries = 0
        backoff = 2.0  # Start with 2 seconds

        while retries <= max_retries:
            try:
                response = self.sg_client.send(message)
                if response.status_code >= 200 and response.status_code < 300:
                    if retries > 0:
                        logger.info(f"Email sent successfully to {to_email} after {retries} retry(ies). Status: {response.status_code}")
                    else:
                        logger.info(f"Email sent successfully to {to_email}. Status code: {response.status_code}")
                    return True
                else:
                    # Non-2xx response - check if retryable
                    if response.status_code >= 500 or response.status_code == 429:
                        # Server error or rate limit - retry
                        if retries == max_retries:
                            logger.error(f"Failed to send email after {max_retries} retries. Status: {response.status_code}, Body: {response.body}")
                            return False
                        
                        # Apply jitter to backoff
                        jitter = random.uniform(0.75, 1.25)
                        delay = backoff * jitter
                        
                        logger.warning(f"Email send returned {response.status_code}. Retrying in {delay:.1f}s... ({retries + 1}/{max_retries})")
                        time.sleep(delay)
                        retries += 1
                        backoff *= 2
                    else:
                        # Client error (4xx) - don't retry
                        logger.error(f"Failed to send email (client error). Status code: {response.status_code}, Body: {response.body}")
                        return False
                        
            except Exception as e:
                # Network error or SendGrid exception - retry
                if retries == max_retries:
                    logger.error(f"Exception occurred while sending email after {max_retries} retries: {e}")
                    return False
                
                # Apply jitter to backoff
                jitter = random.uniform(0.75, 1.25)
                delay = backoff * jitter
                
                logger.warning(f"Exception while sending email: {e}. Retrying in {delay:.1f}s... ({retries + 1}/{max_retries})")
                time.sleep(delay)
                retries += 1
                backoff *= 2

        return False  # Should not reach here
