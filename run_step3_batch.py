#!/usr/bin/env python3
"""DEPRECATED. Superseded by the unified pipeline runner.

This script previously shelled out to step3_edited_translate.py with a --chapter
flag that no longer exists. Use the pipeline instead:

    python -m translator.workflow.pipeline --book <book_id> --stage edit --range 651-750
    python -m translator.workflow.pipeline --book <book_id> --stage all   --range 1-10

Run `python -m translator.workflow.pipeline --help` for all options.
"""

import sys

MESSAGE = __doc__

if __name__ == "__main__":
    print(MESSAGE, file=sys.stderr)
    sys.exit(1)
