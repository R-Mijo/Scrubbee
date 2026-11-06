# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Scrubbee: local pattern-assisted privacy preparation."""
from .core import ScrubVault, ScrubReport, scrub_text, restore_text, scrub_bytes, scrub_file
__version__ = '0.2.1'
__all__ = ['ScrubVault', 'ScrubReport', 'scrub_text', 'restore_text', 'scrub_bytes', 'scrub_file']
