#!/usr/bin/env python3
"""Stable ComicFrame Studio entrypoint."""

# Install the long-render resilience boundary before re-exporting the canonical
# product entrypoint. comicframe_resilience patches comicframe_product's class
# global, while product.main remains the established public launcher.
import comicframe_resilience as _resilience  # noqa: F401
from comicframe_product import ComicFrameStudioApp, main

__all__ = ["ComicFrameStudioApp", "main"]


if __name__ == "__main__":
    main()
