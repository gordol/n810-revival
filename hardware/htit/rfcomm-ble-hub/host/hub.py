#!/usr/bin/env python3
"""Standalone entry point for Pocket's shared HTIT hub transport."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from hub_transport import *

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except (OSError,ValueError,TimeoutError) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
