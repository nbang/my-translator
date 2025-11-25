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

# Load environment variables from .env
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChapterScraper:
    """Scrapes chapters from HTML file and fetches content from website."""
    
    BASE_URL = os.getenv("BOOK_SOURCE_URL", "https://www.52shuku.net")
    RAW_DIR = os.path.join(os.getenv("BOOK_BASE_DIR", "bjXRF"), "raw_chinese")
    
    def __init__(self, html_file: str):
        """
        Initialize the scraper.
        
        Args:
            html_file: Path to the HTML file containing chapter links
        """
        self.html_file = html_file
        self.chapters: List[Dict] = []
        
        # Create output directories
        Path(self.RAW_DIR).mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory created: {self.RAW_DIR}")
    
    def parse_chapters_from_html(self) -> list:
        """
        Parse chapter links and titles from HTML file.
        
        Returns:
            List of tuples (chapter_number, title, url)
        """
        try:
            with open(self.html_file, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            
            chapters = []
            links = soup.find_all('a')
            
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
                    # Construct full URL
                    if isinstance(href, str) and href.startswith('/'):
                        url = self.BASE_URL + href
                    else:
                        url = str(href)
                    chapters.append({
                        'number': chapter_num,
                        'title': chapter_title,
                        'url': url,
                        'full_title': text
                    })
            
            self.chapters = chapters
            logger.info(f"Parsed {len(chapters)} chapters from HTML")
            return chapters
        
        except Exception as e:
            logger.error(f"Error parsing HTML file: {e}")
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
        filepath = Path(self.RAW_DIR) / filename
        
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
            self.parse_chapters_from_html()
        
        chapters_to_process = self.chapters[:max_chapters] if max_chapters else self.chapters
        total = len(chapters_to_process)
        
        logger.info(f"Processing {total} chapters...")
        
        for idx, chapter in enumerate(chapters_to_process, 1):
            try:
                logger.info(f"[{idx}/{total}] Processing chapter {chapter['number']}: {chapter['title']}")
                
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
    
    # Configuration
    html_file = "chapters.html"
    max_chapters = None  # Set to a number to limit processing
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        html_file = sys.argv[1]
    if len(sys.argv) > 2:
        max_chapters = int(sys.argv[2])
    
    logger.info(f"Starting chapter scraper (Step 1)")
    logger.info(f"HTML file: {html_file}")
    logger.info(f"Max chapters: {max_chapters}")
    
    # Initialize scraper
    scraper = ChapterScraper(html_file)
    
    # Parse chapters
    chapters = scraper.parse_chapters_from_html()
    if not chapters:
        logger.error("No chapters found. Exiting.")
        return
    
    logger.info(f"Found {len(chapters)} chapters")
    
    # Process chapters
    scraper.process_chapters(max_chapters=max_chapters, delay=0)
    
    logger.info("Done!")


if __name__ == "__main__":
    main()
