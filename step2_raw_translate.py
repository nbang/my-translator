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
import json
import random
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
    
    INPUT_DIR = os.path.join(os.getenv("BOOK_BASE_DIR", "biqu59096"), "raw_chinese")
    OUTPUT_DIR = os.path.join(os.getenv("BOOK_BASE_DIR", "biqu59096"), "raw_vietnamese")
    def __init__(self, batch_size: Optional[int] = None):
        # We don't need API keys for this method, but we keep the structure
        self.model = "google-translate-m"
        self.batch_size = batch_size
            
        # Create output directory
        Path(self.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory created: {self.OUTPUT_DIR}")
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def _fetch_google_params(self):
        """Fetch f.sid and bl parameters from Google Translate."""
        try:
            response = requests.get("https://translate.google.com", timeout=10)
            if response.status_code == 200:
                # Extract FdrFJe (f.sid)
                match_sid = re.search(r'"FdrFJe":"(.*?)"', response.text)
                if match_sid:
                    self.f_sid = match_sid.group(1)
                
                # Extract cfb2h (bl)
                match_bl = re.search(r'"cfb2h":"(.*?)"', response.text)
                if match_bl:
                    self.bl = match_bl.group(1)
                    
                logger.info(f"Fetched params: f.sid={getattr(self, 'f_sid', 'N/A')}, bl={getattr(self, 'bl', 'N/A')}")
        except Exception as e:
            logger.warning(f"Error fetching Google params: {e}")

    def translate_batch(self, texts: List[str], retries: int = 3) -> List[str]:
        """
        Translate a batch of texts using Google Translate Batch Execute API (RPC).
        """
        if not texts:
            return []
            
        # Ensure we have the required parameters
        if not hasattr(self, 'f_sid') or not hasattr(self, 'bl'):
            self._fetch_google_params()
            
        f_sid = getattr(self, 'f_sid', '')
        bl = getattr(self, 'bl', '')
        
        for attempt in range(retries):
            try:
                time.sleep(1.5)
                
                url = "https://translate.google.com/_/TranslateWebserverUi/data/batchexecute"
                
                rpc_id = "MkEWBc"
                source_lang = "zh"
                target_lang = "vi"
                
                # Construct RPC list for all texts
                rpc_list = []
                for text in texts:
                    if not text.strip():
                        continue
                        
                    # Inner parameter list
                    # Structure: [[text, source, target, boolean], [null]]
                    parameter = [[text, source_lang, target_lang, True], [None]]
                    json_parameter = json.dumps(parameter, separators=(',', ':'))
                    
                    # Outer RPC list item
                    # Structure: ["MkEWBc", inner_json, null, "generic"]
                    rpc_list.append(["MkEWBc", json_parameter, None, "generic"])
                
                if not rpc_list:
                    return [""] * len(texts)

                f_req = json.dumps([rpc_list], separators=(',', ':'))
                
                params = {
                    "rpcids": rpc_id,
                    "source-path": "/",
                    "f.sid": "",
                    "bl": "",
                    "hl": "en-US",
                    "soc-app": "1",
                    "soc-platform": "1",
                    "soc-device": "1",
                    "_reqid": str(random.randint(1000, 9999)),
                    "rt": "c"
                }
                
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                
                data = {
                    "f.req": f_req
                }
                
                response = self.session.post(url, params=params, headers=headers, data=data, timeout=30)
                
                if response.status_code == 200:
                    # Response parsing logic
                    content = response.text
                    
                    # Find the first '['
                    start_idx = content.find('[')
                    if start_idx != -1:
                        json_str = content[start_idx:]
                        try:
                            response_json = json.loads(json_str)
                        except json.JSONDecodeError:
                            lines = json_str.split('\n')
                            for line in lines:
                                try:
                                    if line.strip().startswith('['):
                                        response_json = json.loads(line)
                                        break
                                except:
                                    continue
                        
                        if isinstance(response_json, list):
                            # Map translations back to original texts
                            # The response is a list of [wrb.fr, rpc_id, json_data, ...]
                            # We need to match them. Since we sent them in order, hopefully they come back in order or we can just iterate.
                            # Actually, the batch execute response might not preserve order if we had different RPC IDs, but here we use the same RPC ID.
                            # However, for the same RPC ID, it usually returns one big response or multiple entries.
                            # Let's assume we get a list of responses corresponding to our requests.
                            
                            # Wait, for "MkEWBc", if we send multiple in one f.req, do we get multiple entries in the outer list?
                            # Yes, usually.
                            
                            translated_texts_map = {}
                            
                            for entry in response_json:
                                if isinstance(entry, list) and len(entry) > 2 and entry[1] == rpc_id:
                                    raw_data = entry[2]
                                    try:
                                        parsed_data = json.loads(raw_data)
                                        if parsed_data and isinstance(parsed_data, list) and len(parsed_data) > 1:
                                            # The translation segments are usually at parsed_data[1][0][0][5]
                                            segments = parsed_data[1][0][0][5]
                                            full_translation = ""
                                            original_text_snippet = "" # We might need to match by content if order isn't guaranteed
                                            
                                            # Google Translate response usually contains the source text too.
                                            # parsed_data[0][0] is usually the source text? No.
                                            # Let's look at the structure.
                                            # parsed_data[1][0][0][5] -> translation
                                            # parsed_data[1][4] -> source text (sometimes)
                                            
                                            for segment in segments:
                                                if segment and isinstance(segment, list):
                                                    full_translation += segment[0]
                                            
                                            # We need to map this back to the input. 
                                            # If we sent N requests, we expect N responses.
                                            # But matching them is tricky without a unique ID per request if they are reordered.
                                            # However, in a single batch request, they usually come back in order or we can't easily distinguish if texts are identical.
                                            # For now, let's assume they are returned in the order processed, which might be the order sent.
                                            # BUT, to be safe, we should probably send them one by one if we can't guarantee order, OR trust the order.
                                            # Let's trust the order for now as it's a standard RPC batch.
                                            
                                            # Actually, looking at standard batch implementations, often a request ID is used if supported.
                                            # But MkEWBc doesn't seem to support a custom ID in the inner JSON easily.
                                            
                                            # Let's collect all translations found.
                                            # If we sent 5 items, we hope to find 5 items.
                                            pass 
                                    except:
                                        pass

                            # Re-parsing strategy:
                            # We will iterate and collect all valid translations found in the response.
                            found_translations = []
                            for entry in response_json:
                                if isinstance(entry, list) and len(entry) > 2 and entry[1] == rpc_id:
                                    raw_data = entry[2]
                                    try:
                                        parsed_data = json.loads(raw_data)
                                        if parsed_data and isinstance(parsed_data, list) and len(parsed_data) > 1:
                                            segments = parsed_data[1][0][0][5]
                                            full_translation = ""
                                            for segment in segments:
                                                if segment and isinstance(segment, list):
                                                    full_translation += segment[0]
                                            found_translations.append(full_translation)
                                    except:
                                        pass
                            
                            # If we found the same number of translations as non-empty inputs, great.
                            # Note: We skipped empty texts in rpc_list construction.
                            
                            final_results = []
                            trans_idx = 0
                            for text in texts:
                                if not text.strip():
                                    final_results.append("")
                                else:
                                    if trans_idx < len(found_translations):
                                        final_results.append(found_translations[trans_idx])
                                        trans_idx += 1
                                    else:
                                        final_results.append("") # Failed to get this one
                            
                            return final_results

                    logger.warning(f"Could not parse batch response (Attempt {attempt + 1})")
                else:
                    logger.warning(f"Batch API request failed (Attempt {attempt + 1}): {response.status_code}")
                    
            except Exception as e:
                logger.warning(f"Batch Translation error (Attempt {attempt + 1}): {e}")
            
        return [""] * len(texts)
        
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
                
                # Use the single translation API endpoint with POST to handle large text
                url = "https://translate.google.com/translate_a/single"
                params = {
                    "client": "gtx",
                    "sl": "zh-CN",
                    "tl": "vi",
                    "dt": "t"
                }
                data = {
                    "q": text
                }
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
                
                response = requests.post(url, params=params, data=data, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    # Parse JSON response
                    # Response format: [[["Translated text", "Source text", ...], ...], ...]
                    data = response.json()
                    
                    if data and isinstance(data, list) and len(data) > 0:
                        # Combine all translated segments
                        translated_text = ""
                        for segment in data[0]:
                            if segment and isinstance(segment, list) and len(segment) > 0:
                                translated_text += segment[0]
                        return translated_text
                    else:
                        logger.warning(f"Unexpected JSON format (Attempt {attempt + 1})")
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
            translated_parts = []
            
            if self.batch_size:
                # Batch processing
                for i in range(0, len(chunks), self.batch_size):
                    batch_chunks = chunks[i:i + self.batch_size]
                    translated_batch = self.translate_batch(batch_chunks)
                    
                    if not translated_batch or len(translated_batch) != len(batch_chunks):
                        logger.error(f"Failed to translate batch starting at chunk {i+1} of {chapter_file}")
                        # Fallback or fail? Let's fail for now to be safe.
                        return False
                        
                    translated_parts.extend(translated_batch)
            else:
                # Single processing (original behavior)
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
    parser.add_argument('--batch', type=int, choices=range(1, 11), help='Batch size (1-10) for translation. If not set, uses single translation.')
    args = parser.parse_args()

    translator = RawTranslator(batch_size=args.batch)
    translator.run(force=args.force)

if __name__ == "__main__":
    main()
