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
    RULES_FILE = "TRANSLATOR.md"
    
    def __init__(self):
        self.api_key = os.getenv('STEP2_API_KEY')
        self.api_base = os.getenv('STEP2_API_BASE')
        self.model = os.getenv('STEP2_MODEL', 'GPT-5-nano')
        
        if not self.api_key or not self.api_base:
            raise ValueError("STEP2_API_KEY and STEP2_API_BASE must be set in .env file")
            
        # Create output directory
        Path(self.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory created: {self.OUTPUT_DIR}")
        
    def load_rules(self) -> str:
        """Load translation rules from file."""
        try:
            if os.path.exists(self.RULES_FILE):
                with open(self.RULES_FILE, 'r', encoding='utf-8') as f:
                    rules = f.read()
                logger.info(f"Loaded rules from {self.RULES_FILE}")
                return rules
            else:
                logger.warning(f"{self.RULES_FILE} not found, using default rules")
                return "Translate the following Chinese text to Vietnamese. Provide a literal translation that captures the meaning."
        except Exception as e:
            logger.error(f"Error loading rules: {e}")
            return "Translate the following Chinese text to Vietnamese. Provide a literal translation that captures the meaning."
        
    def translate_text(self, text: str, rules: str, retries: int = 3) -> Optional[str]:
        """
        Translate text using OpenAI API with instructions from TRANSLATOR.md.
        Returns None if translation fails after retries.
        """
        if not text.strip():
            return ""
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Prompt using loaded rules
        messages = [
            {
                "role": "system", 
                "content": rules
            },
            {
                "role": "user", 
                "content": text
            }
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            # temperature removed as requested for GPT-5-nano
        }
        
        for attempt in range(retries):
            try:
                response = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data['choices'][0]['message']['content'].strip()
                else:
                    logger.warning(f"API request failed (Attempt {attempt + 1}/{retries}): {response.status_code} - {response.text}")
                    
            except Exception as e:
                logger.warning(f"Translation error (Attempt {attempt + 1}/{retries}): {e}")
            
            if attempt < retries - 1:
                time.sleep(2) # Wait before retry
            
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
            
            # Reload rules dynamically for each chapter (or batch)
            current_rules = self.load_rules()
            
            with open(input_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple parsing to get content (assuming the format from Step 1)
            # We translate the whole thing or just the content part?
            # Let's translate the whole thing for simplicity in "Raw" step, 
            # or better, just translate the body.
            # For "Raw Translation", let's just translate the whole text to have a Vietnamese version.
            # But to be useful for Step 3, we might want to keep the structure.
            # Let's just translate the content block.
            
            translated_content = self.translate_text(content, current_rules)
            
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
