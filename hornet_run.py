# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Hornet3000-Mitwirkende
"""Einstiegspunkt der installierten Version (Startmenü, Autostart, Konsole):
   python hornet_run.py [run|open|stop|selftest|token]"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, "lib"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from hornet.cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)