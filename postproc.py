import os
import logging
import warnings
from hebrew_tokenizer import tokenize
from convertdate import hebrew, gregorian

# Suppress known FutureWarning from hebrew_tokenizer regex
warnings.filterwarnings("ignore", category=FutureWarning, module="hebrew_tokenizer.tokenizer")

log = logging.getLogger(__name__)

def convert_hebrew_dates(text):
    """Convert Hebrew dates to Gregorian dates."""
    # Heuristic: if four-digit numbers in a range typical for Hebrew calendar appear,
    # try to translate year only (minimal transformation to avoid noise).
    out = []
    for token in text.split():
        if token.isdigit() and 5000 <= int(token) <= 7000:
            try:
                y = int(token)
                jd = hebrew.to_jd(y, 1, 1)
                g_y, _, _ = gregorian.from_jd(jd)
                out.append(str(g_y))
            except Exception:
                out.append(token)
        else:
            out.append(token)
    return " ".join(out)


def postprocess_text(text):
    """Postprocess the OCR text to improve accuracy."""
    try:
        # Tokenize the text
        tokens = tokenize(text)
        corrected_tokens = []

        for token in tokens:
            token_type, token_text, *_ = token
            corrected_tokens.append(token_text)

        corrected_text = ' '.join(corrected_tokens)
        
        # Convert Hebrew dates to Gregorian dates
        converted_text = convert_hebrew_dates(corrected_text)
        
        return converted_text
    except Exception as e:
        log.error(f"Error in postprocess_text: {e}")
        return text

def postprocess_files(input_dir, output_dir):
    """Postprocess all OCR text files in the specified directory."""
    if not os.path.exists(input_dir):
        log.error(f"Input directory '{input_dir}' does not exist.")
        return
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for text_file in os.listdir(input_dir):
        if text_file.endswith('.txt'):
            input_path = os.path.join(input_dir, text_file)
            output_path = os.path.join(output_dir, text_file)

            log.info(f"Postprocessing {input_path}")

            try:
                with open(input_path, 'r', encoding='utf-8') as file:
                    text = file.read()

                corrected_text = postprocess_text(text)

                with open(output_path, 'w', encoding='utf-8') as file:
                    file.write(corrected_text)

                log.info(f"Postprocessing completed for {input_path}, output saved to {output_path}")
            except Exception as e:
                log.error(f"Error processing file {input_path}: {e}")

def main():
    """Main function to orchestrate the postprocessing of OCR output."""
    input_dir = 'ocr_texts'  # Directory containing the OCR output text files
    output_dir = 'postproc_texts'  # Directory to save the postprocessed text files
    
    try:
        postprocess_files(input_dir, output_dir)
    except Exception as e:
        log.error(f"An error occurred during postprocessing: {e}")

if __name__ == "__main__":
    main()
