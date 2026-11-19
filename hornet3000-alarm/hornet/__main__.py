# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Start:  python -m hornet [run|open|stop|selftest|token]"""
import sys

from .cli import main

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)