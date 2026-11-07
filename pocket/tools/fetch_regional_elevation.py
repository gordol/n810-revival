#!/usr/bin/env python3
"""Compatibility entry point for area-selected elevation acquisition."""
if __package__:
    from .elevation_pipeline import main
else:
    from elevation_pipeline import main
if __name__=='__main__':main()
