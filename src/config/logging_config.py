# File: src/config/logging_config.py

import logging
import sys

def setup_logging():
    """
    Configures a standardized logger for the entire application.
    """
    # Define the format for our log messages
    log_format = "%(asctime)s - [%(name)-25s] - [%(levelname)-8s] - %(message)s"
    
    # Create a formatter with our format
    formatter = logging.Formatter(log_format)
    
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Set the minimum level of logs to capture (DEBUG is the most verbose)
    root_logger.setLevel(logging.DEBUG)
    
    # Create a handler to output logs to the console (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    
    # Set the formatter for the handler
    console_handler.setFormatter(formatter)
    
    # Add the handler to the root logger
    # We check if handlers already exist to prevent duplicate logs
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)

    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    
    # Get a logger instance for this setup file to announce completion
    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully.")