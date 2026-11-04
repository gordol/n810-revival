#!/usr/bin/env python3
"""Import the app so Python can validate and reuse its bytecode cache."""
import os
import sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from app import main
if __name__=='__main__':main()
