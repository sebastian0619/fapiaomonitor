import os
import logging

def ensure_dir(directory):
    try:
        logging.debug(f"Ensuring directory exists: {directory}")
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        logging.debug(f"Error in ensuring directory exists: {e}")

def rename_file(old_path, new_name):
    try:
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        logging.debug(f"Renaming file from {old_path} to {new_path}")
        os.rename(old_path, new_path)
        return new_path
    except Exception as e:
        logging.debug(f"Error in renaming file: {e}")

def clean_up(*paths):
    for path in paths:
        try:
            logging.debug(f"Removing file: {path}")
            os.remove(path)
        except Exception as e:
            logging.debug(f"Error in removing file: {e}")