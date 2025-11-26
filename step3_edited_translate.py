#!/usr/bin/env python3
"""
Step 3: Edited Translator
Translates raw Chinese chapters to polished Vietnamese using dynamic rules from TRANSLATOR.md.
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

class EditedTranslator:
    """Translates Chinese content to polished Vietnamese using dynamic rules."""
    
    BOOK_DIR = os.getenv("BOOK_BASE_DIR", "bjXRF")
    INPUT_DIR = os.path.join(BOOK_DIR, "raw_vietnamese")
    REF_DIR = os.path.join(BOOK_DIR, "raw_chinese")
    OUTPUT_DIR = os.path.join(BOOK_DIR, "edited_vietnamese")
    RULES_FILE = os.path.join(BOOK_DIR, "EDITOR.md")
    
    def __init__(self):
        self.provider = os.getenv('LLM_PROVIDER', 'openai').lower()
        self.api_key = os.getenv('LLM_API_KEY')
        self.api_base = os.getenv('LLM_API_BASE')
        self.model = os.getenv('LLM_MODEL', 'gpt-5-mini')
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY must be set in .env file")
            
        if self.provider == 'openai' and not self.api_base:
             raise ValueError("LLM_API_BASE must be set in .env file for OpenAI provider")
            
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
                return "Translate to natural Vietnamese."
        except Exception as e:
            logger.error(f"Error loading rules: {e}")
            return "Translate to natural Vietnamese."

    def translate_text(self, text: str, ref_text: str, rules: str, retries: int = 3) -> Optional[str]:
        """
        Translate text using the configured provider (OpenAI or Google).
        Returns None if translation fails after retries.
        """
        if not text.strip():
            return ""

        if self.provider == 'google':
            return self._translate_google(text, ref_text, rules, retries)
        else:
            return self._translate_openai(text, ref_text, rules, retries)

    def _translate_google(self, text: str, ref_text: str, rules: str, retries: int) -> Optional[str]:
        """Translate using Google Generative AI (Gemini) REST API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        # Construct the prompt with system instructions and user content
        # Note: 'system_instruction' is supported in newer Gemini models.
        # If using an older model that doesn't support it, it might be better to prepend to the prompt.
        # For now, we'll try the system_instruction field for cleaner separation.
        
        payload = {
            "system_instruction": {
                "parts": [{"text": rules}]
            },
            "contents": [{
                "parts": [{"text": f"## Bản gốc:\n{ref_text}\n\n## Bản dịch thô:\n{text}"}]
            }],
            "generationConfig": {
                "temperature": 0.7
            }
        }

        for attempt in range(retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=120)
                
                if response.status_code == 200:
                    data = response.json()
                    # Check for valid response structure
                    if 'candidates' in data and data['candidates']:
                        content = data['candidates'][0]['content']['parts'][0]['text']
                        return content.strip()
                    else:
                        logger.warning(f"Google API returned no candidates: {data}")
                else:
                    logger.warning(f"Google API request failed (Attempt {attempt + 1}/{retries}): {response.status_code} - {response.text}")
                    
            except Exception as e:
                logger.warning(f"Translation error (Attempt {attempt + 1}/{retries}): {e}")
            
            if attempt < retries - 1:
                time.sleep(2)
            
        logger.error("Translation failed after all retries.")
        return None

    def _translate_openai(self, text: str, ref_text: str, rules: str, retries: int) -> Optional[str]:
        """Translate using OpenAI-compatible API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = [
            {
                "role": "system", 
                "content": rules
            },
            {
                "role": "user", 
                "content": f"## Bản gốc:\n{ref_text}\n\n## Bản dịch thô:\n{text}"
            }
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }
        
        for attempt in range(retries):
            try:
                response = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data['choices'][0]['message']['content'].strip()
                else:
                    logger.warning(f"API request failed (Attempt {attempt + 1}/{retries}): {response.status_code} - {response.text}")
                    
            except Exception as e:
                logger.warning(f"Translation error (Attempt {attempt + 1}/{retries}): {e}")
            
            if attempt < retries - 1:
                time.sleep(2)
            
        logger.error("Translation failed after all retries.")
        return None

    def process_chapter(self, chapter_file: str, force: bool = False) -> bool:
        """Process a single chapter file."""
        try:
            input_path = Path(self.INPUT_DIR) / chapter_file
            output_path = Path(self.OUTPUT_DIR) / chapter_file
            ref_path = Path(self.REF_DIR) / chapter_file
            
            if output_path.exists() and not force:
                if output_path.stat().st_size > 0:
                    logger.info(f"Skipping {chapter_file} (already exists). Use --force to overwrite.")
                    return True
                else:
                    logger.warning(f"Found empty file {chapter_file}, re-processing...")
                
            logger.info(f"Processing {chapter_file}...")
            
            # Reload rules dynamically for each chapter (or batch)
            current_rules = self.load_rules()
            
            # Read Input (Raw Vietnamese)
            with open(input_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Read Reference (Raw Chinese)
            if ref_path.exists():
                with open(ref_path, 'r', encoding='utf-8') as f:
                    ref_content = f.read()
            else:
                logger.warning(f"Reference file {ref_path} not found. Proceeding without reference.")
                ref_content = "No reference available."
            
            # Extract content if needed, or translate the whole file
            # For better results, we should probably parse the markdown and translate only the content
            # But for now, let's pass the whole thing and let the LLM handle it or just the body.
            # To be safe and simple, let's pass the whole text.
            
            translated_content = self.translate_text(content, ref_content, current_rules)
            
            if translated_content is None:
                logger.error(f"Failed to translate {chapter_file}. Skipping write.")
                return False

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(translated_content)
                
            logger.info(f"Saved edited translation to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing {chapter_file}: {e}")
            return False

    def run(self, specific_chapter: Optional[str] = None, force: bool = False):
        """Run the edited translation process."""
        if specific_chapter:
            files = [specific_chapter]
        else:
            files = sorted([f for f in os.listdir(self.INPUT_DIR) if f.endswith('.md')])
        
        if not files:
            logger.warning(f"No files found in {self.INPUT_DIR}")
            return
            
        logger.info(f"Found {len(files)} chapters to process")
        
        for file in files:
            self.process_chapter(file, force=force)
            time.sleep(1)

def main():
    parser = argparse.ArgumentParser(description='Step 3: Edited Translation')
    parser.add_argument('--chapter', type=str, help='Specific chapter file to process (e.g., chapter_001.md)')
    parser.add_argument('--force', action='store_true', help='Force re-translation even if output exists')
    args = parser.parse_args()
    
    translator = EditedTranslator()
    translator.run(specific_chapter=args.chapter, force=args.force)

if __name__ == "__main__":
    main()
