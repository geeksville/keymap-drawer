

import sys

def has_pyqt6() -> bool:
    """Probe whether PyQt6 is installed (both python code and required native dependencies)."""
    try:
        # 1. This triggers the dynamic linker to load the C++ shared libraries.
        #    If system deps are missing, this explodes.
        from PyQt6 import QtWidgets, QtCore
        
        return True
        
    except Exception as e:
        return False