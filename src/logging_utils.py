import logging
import json
import os
import shutil
import time
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Tuple

class RunIDFilter(logging.Filter):
    """
    Injects a unique run_id into every log record.
    """
    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record):
        record.run_id = self.run_id
        return True

def setup_logging(log_level: str = "INFO", logs_base_dir: str = "data/logs") -> Tuple[str, Path]:
    """
    Sets up structured logging and creates a unique directory for the current run.
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(logs_base_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Standard format including run_id and module name
    log_format = "%(asctime)s [%(run_id)s] %(name)s - %(levelname)s - %(message)s"
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    run_filter = RunIDFilter(run_id)

    # Console Handler
    c_handler = logging.StreamHandler()
    c_handler.setFormatter(logging.Formatter(log_format))
    c_handler.addFilter(run_filter)
    root_logger.addHandler(c_handler)

    # Run-specific File Handler (in the artifact folder)
    f_handler = logging.FileHandler(run_dir / "workflow.log")
    f_handler.setFormatter(logging.Formatter(log_format))
    f_handler.addFilter(run_filter)
    root_logger.addHandler(f_handler)

    logging.info(f"Logging initialized. Run ID: {run_id}. Artifacts saved to: {run_dir}")
    
    return run_id, run_dir

def save_artifact(run_dir: Path, name: str, content: Any, extension: str = "json"):
    """
    Saves a debug artifact (JSON or HTML) to the run directory.
    Retries up to 2 times on failure with exponential backoff.
    """
    filepath = run_dir / f"{name}.{extension}"
    max_retries = 2
    retries = 0
    backoff = 1.0
    
    while retries <= max_retries:
        try:
            if extension == "json":
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(content, f, indent=2)
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(str(content))
            
            if retries > 0:
                logging.info(f"Saved artifact {name} after {retries} retry(ies): {filepath}")
            # logging.debug(f"Saved artifact: {filepath}")
            return True
            
        except Exception as e:
            if retries == max_retries:
                logging.error(f"Failed to save artifact {name} after {max_retries} retries: {e}")
                return False
            
            jitter = random.uniform(0.75, 1.25)
            delay = backoff * jitter
            
            logging.warning(f"Failed to save artifact {name}: {e}. Retrying in {delay:.1f}s... ({retries + 1}/{max_retries})")
            time.sleep(delay)
            retries += 1
            backoff *= 2
    
    return False

def cleanup_old_runs(logs_base_dir: str = "data/logs", days_to_keep: int = 10):
    """
    Deletes run directories older than the specified number of days.
    """
    base_path = Path(logs_base_dir)
    if not base_path.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    count = 0
    for run_folder in base_path.iterdir():
        if not run_folder.is_dir():
            continue
            
        try:
            # Parse date from folder name format: YYYYMMDD_HHMMSS
            folder_date = datetime.strptime(run_folder.name, "%Y%m%d_%H%M%S")
            if folder_date < cutoff_date:
                shutil.rmtree(run_folder)
                count += 1
        except ValueError:
            # Ignore folders that don't match the format
            continue
            
    if count > 0:
        logging.info(f"Cleaned up {count} old run directories.")
