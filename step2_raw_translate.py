#!/usr/bin/env python3
"""
Step 2: Raw Translator
Translates raw Chinese chapters to raw Vietnamese using a basic prompt.
"""

import os
import time
import logging
import argparse
from pathlib import Path
from typing import List, Optional
import requests
import urllib.parse
import re
import html
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
# Configure logging
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Root logger configuration
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# File Handler
file_handler = logging.FileHandler('errors.log')
file_handler.setLevel(logging.ERROR)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

class RawTranslator:
    """Translates Chinese content to Vietnamese using a basic prompt."""
    
    INPUT_DIR = "biqu59096/raw_chinese"
    OUTPUT_DIR = "biqu59096/raw_vietnamese"
    def __init__(self):
        # We don't need API keys for this method, but we keep the structure
        self.model = "google-translate-m"
            
        # Create output directory
        Path(self.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory created: {self.OUTPUT_DIR}")
        
    def translate_single_chunk(self, text: str, retries: int = 3) -> Optional[str]:
        """
        Translate a single chunk of text using Google Translate Mobile API.
        """
        if not text.strip():
            return ""

        for attempt in range(retries):
            try:
                # Rate limiting
                time.sleep(1.5) 
                
                source_language = 'zh-CN'
                target_language = 'vi'
                escaped_text = urllib.parse.quote(text)
                
                url = 'https://translate.google.com/m?tl=%s&sl=%s&q=%s' % (target_language, source_language, escaped_text)
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    # Extract translation from HTML
                    # Pattern typically looks like: <div class="result-container">...</div>
                    # Or for mobile: <div dir="ltr" class="t0">...</div>
                    
                    # Try to find the result container
                    match = re.search(r'<div[^>]*class="[^"]*result-container[^"]*"[^>]*>(.*?)</div>', response.text, re.DOTALL)
                    if not match:
                        # Fallback for other mobile variations
                        match = re.search(r'<div[^>]*class="[^"]*t0[^"]*"[^>]*>(.*?)</div>', response.text, re.DOTALL)
                        
                    if match:
                        translated_html = match.group(1)
                        # Unescape HTML entities
                        translated_text = html.unescape(translated_html)
                        return translated_text
                    else:
                        logger.warning(f"Could not parse translation from response (Attempt {attempt + 1})")
                else:
                    logger.warning(f"API request failed (Attempt {attempt + 1}): {response.status_code}")
                    
            except Exception as e:
                logger.warning(f"Translation error (Attempt {attempt + 1}): {e}")
            
            time.sleep(2) # Wait longer before retry
        
        logger.error("Translation failed after all retries.")
        return None

    def process_chapter(self, chapter_file: str, force: bool = False) -> bool:
        """Process a single chapter file."""
        try:
            input_path = Path(self.INPUT_DIR) / chapter_file
            output_path = Path(self.OUTPUT_DIR) / chapter_file
            
            if output_path.exists() and not force:
                if output_path.stat().st_size > 0:
                    logger.info(f"Skipping {chapter_file} (already exists). Use --force to overwrite.")
                    return True
                else:
                    logger.warning(f"Found empty file {chapter_file}, re-processing...")
                
            logger.info(f"Processing {chapter_file}...")
            
            with open(input_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Chunking logic moved here
            CHUNK_SIZE = 4000
            chunks = []
            current_chunk = ""
            
            for line in content.split('\n'):
                if len(current_chunk) + len(line) < CHUNK_SIZE:
                    current_chunk += line + "\n"
                else:
                    chunks.append(current_chunk)
                    current_chunk = line + "\n"
            if current_chunk:
                chunks.append(current_chunk)
            
            translated_parts = []
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    translated_parts.append("")
                    continue
                    
                translated_chunk = self.translate_single_chunk(chunk)
                if translated_chunk is None:
                    logger.error(f"Failed to translate chunk {i+1}/{len(chunks)} of {chapter_file}")
                    return False
                translated_parts.append(translated_chunk)
            
            translated_content = "\n".join(translated_parts)
            
            if translated_content is None:
                logger.error(f"Failed to translate {chapter_file}. Skipping write.")
                return False

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(translated_content)
                
            logger.info(f"Saved raw translation to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing {chapter_file}: {e}")
            return False

    def run(self, force: bool = False):
        """Run the raw translation process."""
        files = sorted([f for f in os.listdir(self.INPUT_DIR) if f.endswith('.md')])
        
        if not files:
            logger.warning(f"No files found in {self.INPUT_DIR}")
            return
            
        logger.info(f"Found {len(files)} chapters to process")
        
        for file in files:
            self.process_chapter(file, force=force)
            time.sleep(1)

def main():
    parser = argparse.ArgumentParser(description='Step 2: Raw Translation')
    parser.add_argument('--force', action='store_true', help='Force re-translation even if output exists')
    args = parser.parse_args()

    translator = RawTranslator()
    translator.run(force=args.force)

if __name__ == "__main__":
    main()
