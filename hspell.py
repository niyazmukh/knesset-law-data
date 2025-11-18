import subprocess
import os
from pathlib import Path
import tempfile
import logging
import re

# Configure logging
logging.basicConfig(filename='spell_check.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_wsl():
    """Check if WSL is installed and reachable"""
    try:
        result = subprocess.run(['wsl', '--version'], capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            raise EnvironmentError("WSL is not installed or not reachable.")
    except FileNotFoundError:
        raise EnvironmentError("WSL is not installed or not reachable.")

def setup_hspell():
    """Install HSpell if not present and ensure it is reachable"""
    check_wsl()
    try:
        result = subprocess.run(['wsl', 'hspell', '-V'], capture_output=True, text=True, encoding='utf-8')
        logging.info(f"WSL HSpell version check output: {result.stdout}")
        logging.error(f"WSL HSpell version check error: {result.stderr}")
        if result.returncode != 0:
            raise EnvironmentError("HSpell is not installed or not reachable.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error checking HSpell version: {e}")
        logging.info("HSpell is not installed. Installing HSpell...")
        subprocess.run(['wsl', 'sudo', 'apt', 'update'])
        subprocess.run(['wsl', 'sudo', 'apt', 'install', '-y', 'hspell'])
        # Verify installation
        result = subprocess.run(['wsl', 'hspell', '-V'], capture_output=True, text=True, encoding='utf-8')
        logging.info(f"WSL HSpell version check output after install: {result.stdout}")
        logging.error(f"WSL HSpell version check error after install: {result.stderr}")
        if result.returncode != 0:
            raise EnvironmentError("Failed to install HSpell.")
        else:
            logging.info("HSpell installed successfully.")

def spell_check_hebrew(text):
    """Check Hebrew text spelling using HSpell via WSL"""
    # Convert text to ISO-8859-8 encoding
    text_iso = text.encode('iso-8859-8', errors='replace').decode('iso-8859-8')
    
    with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='iso-8859-8', suffix='.txt') as temp_file:
        temp_file.write(text_iso)
        temp_file_path = temp_file.name

    cmd = f'wsl hspell -c -H -i < {temp_file_path}'
    logging.info(f"Running command: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=False)
    
    os.remove(temp_file_path)  # Clean up the temporary file

    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)

    # Decode the output using ISO-8859-8 encoding
    output = result.stdout.decode('iso-8859-8', errors='replace')
    logging.info(f"Raw HSpell output: {output}")
    return output

def apply_corrections(original_text, hspell_output):
    """Apply corrections from HSpell output to the original text"""
    corrections = re.findall(r'(\S+) -> (\S+)', hspell_output)
    corrected_text = original_text
    corrections_made = False
    for typo, correction in corrections:
        corrected_text = re.sub(r'\b' + re.escape(typo) + r'\b', correction, corrected_text)
        corrections_made = True
    return corrected_text, corrections_made, len(corrections)

def process_file(file_path):
    """Process single text file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    logging.info(f"Processing file: {file_path}")
    logging.info(f"Input text: {text}")
    hspell_output = spell_check_hebrew(text)
    corrected_text, corrections_made, num_corrections = apply_corrections(text, hspell_output)
    log_spell_check(file_path, text, corrected_text, corrections_made, num_corrections)
    return corrected_text, corrections_made, num_corrections

def log_spell_check(file_path, original_text, checked_text, corrections_made, num_corrections):
    """Log the details of the spell check"""
    if corrections_made:
        original_words = set(original_text.split())
        checked_words = set(checked_text.split())
        typos = original_words - checked_words
        corrections = checked_words - original_words

        logging.info(f"Processing file: {file_path}")
        logging.info(f"Typos detected: {typos}")
        logging.info(f"Corrections made: {corrections}")
        logging.info(f"Number of corrections made: {num_corrections}")
    else:
        logging.info(f"No corrections made for file: {file_path}")

def batch_process(input_dir, output_dir):
    """Process all txt files in directory"""
    Path(output_dir).mkdir(exist_ok=True)
    
    total_files = 0
    total_corrections = 0
    
    for file in Path(input_dir).glob('*.txt'):
        try:
            corrected_text, corrections_made, num_corrections = process_file(file)
            total_files += 1
            if corrections_made:
                total_corrections += num_corrections
                output_path = Path(output_dir) / f"{file.stem}_checked{file.suffix}"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(corrected_text)
        except Exception as e:
            logging.error(f"Error processing file {file}: {e}")
    
    logging.info(f"Total files processed: {total_files}")
    logging.info(f"Total corrections made: {total_corrections}")

if __name__ == "__main__":
    try:
        setup_hspell()
    except EnvironmentError as e:
        logging.error(f"Setup error: {e}")
        exit(1)
    
    # Example usage
    input_dir = "ocr_texts"
    output_dir = "checked_texts"
    batch_process(input_dir, output_dir)
