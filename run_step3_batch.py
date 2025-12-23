#!/usr/bin/env python3
"""
Batch runner for step3_edited_translate.py
Processes a specific range of chapters.
"""

import subprocess
import sys
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_chapter(chapter_num: int, force: bool = False) -> bool:
    """Run step3 for a specific chapter."""
    chapter_file = f"chapter_{chapter_num:04d}.md"
    
    cmd = [sys.executable, "step3_edited_translate.py", "--chapter", chapter_file]
    if force:
        cmd.append("--force")
    
    logger.info(f"Processing {chapter_file}...")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            logger.info(f"✓ Successfully processed {chapter_file}")
            return True
        else:
            logger.error(f"✗ Failed to process {chapter_file}")
            logger.error(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"✗ Timeout processing {chapter_file}")
        return False
    except Exception as e:
        logger.error(f"✗ Error processing {chapter_file}: {e}")
        return False

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch process chapters for step3')
    parser.add_argument('--start', type=int, default=651, help='Starting chapter number')
    parser.add_argument('--count', type=int, default=100, help='Number of chapters to process')
    parser.add_argument('--force', action='store_true', help='Force re-translation')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between chapters (seconds)')
    args = parser.parse_args()
    
    start_chapter = args.start
    end_chapter = start_chapter + args.count
    
    logger.info(f"Starting batch processing: chapters {start_chapter} to {end_chapter - 1}")
    logger.info(f"Total chapters: {args.count}")
    
    success_count = 0
    fail_count = 0
    
    for chapter_num in range(start_chapter, end_chapter):
        success = run_chapter(chapter_num, force=args.force)
        
        if success:
            success_count += 1
        else:
            fail_count += 1
        
        # Delay between chapters to avoid rate limiting
        if chapter_num < end_chapter - 1:
            time.sleep(args.delay)
    
    logger.info("=" * 60)
    logger.info(f"Batch processing complete!")
    logger.info(f"Success: {success_count}/{args.count}")
    logger.info(f"Failed: {fail_count}/{args.count}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
