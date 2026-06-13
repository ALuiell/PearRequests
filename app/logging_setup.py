import logging
import re

class SensitiveDataFilter(logging.Filter):
    """Filters out sensitive information like OAuth tokens from logs."""
    
    def __init__(self):
        super().__init__()
        # Patterns to redact: PASS oauth:<token>, Authorization: Bearer <token>, etc.
        self.patterns = [
            (re.compile(r'(oauth:)[a-zA-Z0-9]+', re.IGNORECASE), r'\1***REDACTED***'),
            (re.compile(r'(Bearer\s+)[a-zA-Z0-9_-]+', re.IGNORECASE), r'\1***REDACTED***'),
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in self.patterns:
                record.msg = pattern.sub(replacement, record.msg)
        return True

def setup_logging(log_level: int = logging.INFO) -> None:
    """Configures the root logger with a safe console handler."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # Add redaction filter
    console_handler.addFilter(SensitiveDataFilter())

    root_logger.addHandler(console_handler)
    
    # Avoid duplicate logs if setup_logging is called multiple times
    root_logger.propagate = False
    
    # Silence httpx INFO logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
