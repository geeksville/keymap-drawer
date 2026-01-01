
import sys
from argparse import Namespace
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import QTimer

from keymap_drawer.config import Config


class KeymapWindow(QMainWindow):
    """Main window for displaying the keymap SVG"""
    
    svg_widget: QSvgWidget
    
    def __init__(self, svg_path: Path):
        super().__init__()
        self.setWindowTitle("Keymap Drawer - Live View")
        
        # Create and configure the SVG widget
        self.svg_widget = QSvgWidget(str(svg_path))
        self.setCentralWidget(self.svg_widget)
        
        # Resize window to fit the SVG content
        svg_size = self.svg_widget.sizeHint()
        self.resize(svg_size)
        
        print(f"Window created with size: {svg_size.width()}x{svg_size.height()}")
        print("Press any key to close the window...")
        
    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        """Close the window on any key press"""
        print("Key pressed, closing window...")
        _ = self.close()
    
    def showEvent(self, event):
        """Called when window is shown"""
        super().showEvent(event)
        print("Window is now visible!")


def live(args: Namespace, config: Config) -> None:  # pylint: disable=unused-argument
    """Show a live view of keypresses"""
    # Path to the SVG file
    svg_path = Path("test/miryoku-num.svg")
    
    # Check if the file exists
    if not svg_path.exists():
        print(f"Error: SVG file not found at {svg_path}")
        sys.exit(1)
    
    print(f"Loading SVG from: {svg_path.absolute()}")
    
    # Create the Qt application
    app = QApplication(sys.argv)
    
    # Create and show the window
    window = KeymapWindow(svg_path)
    window.show()
    
    print("Starting Qt event loop...")
    # Start the event loop
    exit_code = app.exec()
    print(f"Application closed with exit code: {exit_code}")
    sys.exit(exit_code)
