#!/usr/bin/env python3
"""
Step 1: Chapter Scraper
Parses chapters from HTML, fetches content from website, and saves raw Chinese content.
"""

import os
import re
import time
from pathlib import Path
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
import logging
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse

# Load environment variables from .env
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChapterScraper:
    """Scrapes chapters from website."""
    
    def __init__(self):
        """
        Initialize the scraper.
        Reads URL from .env and determines output directory dynamically.
        """
        self.url = os.getenv("BOOK_SOURCE_URL")
        if not self.url:
            raise ValueError("BOOK_SOURCE_URL not found in .env")
            
        # Try to get base dir from environment first
        env_base_dir = os.getenv("BOOK_BASE_DIR")
        
        if env_base_dir and env_base_dir.strip():
            self.base_dir = env_base_dir.strip()
            self.book_name = self.base_dir # Use base dir as book name for consistency
        else:
            # Derive book name/base dir from URL
            # e.g. https://www.52shuku.net/yanqing/29_b/bkadd.html -> bkadd
            path = urlparse(self.url).path
            filename = os.path.basename(path)
            # Remove extension if present
            self.book_name = os.path.splitext(filename)[0]
            self.base_dir = self.book_name
        self.raw_dir = os.path.join(self.base_dir, "raw_chinese")
        
        self.chapters: List[Dict] = []
        
        # Create output directories
        Path(self.raw_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Target URL: {self.url}")
        logger.info(f"Output directory: {self.raw_dir}")
    
    def fetch_and_parse_chapters(self) -> list:
        """
        Fetch chapter list from the source URL and parse links.
        
        Returns:
            List of dictionaries containing chapter info
        """
        try:
            logger.info(f"Fetching chapter list from {self.url}...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the list container: <ul class="list clearfix">
            chapter_list_ul = soup.find('ul', class_='list clearfix')
            
            if not chapter_list_ul:
                logger.error("Could not find <ul class='list clearfix'> in the page.")
                return []
            
            chapters = []
            # Find all links inside the ul
            links = chapter_list_ul.find_all('a')
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Match chapter pattern like "第1章 章节标题" or "第1页"
                match = re.match(r'第(\d+)[页章]\s*(.*)', text)
                
                if match:
                    chapter_num = int(match.group(1))
                    chapter_title = match.group(2).strip()
                    if not chapter_title:
                        chapter_title = text
                else:
                    continue

                # Construct full URL
                full_url = urljoin(self.url, href)
                
                chapters.append({
                    'number': chapter_num,
                    'title': chapter_title,
                    'url': full_url,
                    'full_title': text
                })
            
            # Sort chapters by number to ensure order
            chapters.sort(key=lambda x: x['number'])
            
            self.chapters = chapters
            logger.info(f"Parsed {len(chapters)} chapters from website")
            return chapters
        
        except Exception as e:
            logger.error(f"Error fetching/parsing chapters: {e}")
            return []
    
    def fetch_chapter_content(self, url: str) -> str:
        """
        Fetch chapter content from the given URL.
        
        Args:
            url: URL of the chapter
            
        Returns:
            Chapter content as text
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find chapter content in div with id="text"
            content_div = soup.find('div', id='text')
            
            if content_div:
                content = content_div.get_text(strip=True)
                # Clean up excessive whitespace
                content = re.sub(r'\s+', '\n', content)
                return content
            
            logger.warning(f"No content found for {url}")
            return ""
        
        except Exception as e:
            logger.error(f"Error fetching chapter from {url}: {e}")
            return ""
    
    def save_chapter(self, chapter_num: int, title: str, content: str) -> str:
        """
        Save chapter to individual markdown file in raw directory.
        
        Args:
            chapter_num: Chapter number
            title: Chapter title
            content: Chapter content
            
        Returns:
            Path to saved file
        """
        filename = f"chapter_{chapter_num:04d}.md"
        filepath = Path(self.raw_dir) / filename
        
        markdown_content = f"""
### 标题 | Title

第{chapter_num}章 {title}

---

### 内容 | Content

{content}

---
*生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            logger.info(f"Saved chapter {chapter_num} to {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Error saving chapter {chapter_num}: {e}")
            return ""
    
    def process_chapters(self, max_chapters: Optional[int] = None, 
                        delay: float = 1.0) -> None:
        """
        Process all chapters: fetch content and save original.
        
        Args:
            max_chapters: Maximum number of chapters to process (None for all)
            delay: Delay between requests in seconds
        """
        if not self.chapters:
            self.fetch_and_parse_chapters()
        
        chapters_to_process = self.chapters[:max_chapters] if max_chapters else self.chapters
        total = len(chapters_to_process)
        
        logger.info(f"Processing {total} chapters...")
        
        for idx, chapter in enumerate(chapters_to_process, 1):
            try:
                logger.info(f"[{idx}/{total}] Processing chapter {chapter['number']}: {chapter['title']}")
                
                # Check if file already exists
                filename = f"chapter_{chapter['number']:04d}.md"
                filepath = Path(self.raw_dir) / filename
                if filepath.exists():
                     logger.info(f"Skipping chapter {chapter['number']} - already exists")
                     continue

                # Fetch content
                content = self.fetch_chapter_content(chapter['url'])
                if not content:
                    logger.warning(f"Skipping chapter {chapter['number']} - no content fetched")
                    continue
                
                # Save original chapter
                self.save_chapter(
                    chapter['number'],
                    chapter['title'],
                    content
                )
                
                # Be respectful to the server
                time.sleep(delay)
            
            except Exception as e:
                logger.error(f"Error processing chapter {chapter['number']}: {e}")
                continue

def main():
    """Main execution function."""
    import sys
    
    max_chapters = None  # Set to a number to limit processing
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        try:
            max_chapters = int(sys.argv[1])
        except ValueError:
            pass 
    
    logger.info(f"Starting chapter scraper (Step 1)")
    logger.info(f"Max chapters: {max_chapters}")
    
    try:
        # Initialize scraper
        scraper = ChapterScraper()
        
        # Parse chapters
        chapters = scraper.fetch_and_parse_chapters()
        if not chapters:
            logger.error("No chapters found. Exiting.")
            return
        
        logger.info(f"Found {len(chapters)} chapters")
        
        # Process chapters
        scraper.process_chapters(max_chapters=max_chapters, delay=1.0)
        
        logger.info("Done!")
        
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
