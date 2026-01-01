
import sys
from argparse import Namespace
from pathlib import Path
import xml.etree.ElementTree as ET

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QKeyEvent, QPainter, QShowEvent, QPaintEvent
from PyQt6.QtCore import QSize, Qt

from keymap_drawer.config import Config


class SvgWidget(QWidget):
    """Custom widget for rendering SVG with high quality
    
    Note: Qt's SVG renderer has known limitations with some CSS properties
    (e.g., dominant-baseline) compared to browser rendering. Text positioning
    may differ slightly from browser-rendered SVGs.
    """
    
    renderer: QSvgRenderer
    svg_path: Path
    svg_tree: ET.ElementTree
    svg_root: ET.Element
    held_keys: set[str]
    
    def __init__(self, svg_path: Path):
        super().__init__()
        self.svg_path = svg_path
        self.held_keys = set()
        
        # Parse the SVG XML
        self.svg_tree = ET.parse(str(svg_path))
        self.svg_root = self.svg_tree.getroot()
        
        # Load initial SVG
        self.renderer = QSvgRenderer(str(svg_path))
        
        # Set a fixed size based on the SVG's default size
        svg_size = self.renderer.defaultSize()
        self.setFixedSize(svg_size)
    
    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Custom paint event with high-quality rendering"""
        painter = QPainter(self)
        
        # Enable all quality rendering hints
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.LosslessImageRendering)
        
        # Render the SVG
        self.renderer.render(painter)
    
    def sizeHint(self) -> QSize:
        """Return the preferred size"""
        return self.renderer.defaultSize()
    
    def find_key_rect(self, key_text: str) -> ET.Element | None:
        """Find the rect element for a given key text"""
        # Register namespace to avoid ns0 prefixes
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        
        # Search for text elements with class "key" (including "key tap" and "key shifted")
        for text_elem in self.svg_root.iter('{http://www.w3.org/2000/svg}text'):
            class_attr = text_elem.get('class', '')
            
            # Check if this is a key-related text element
            if 'key' in class_attr:
                # Check direct text content
                if text_elem.text and text_elem.text.strip() == key_text:
                    return self._get_rect_from_text_element(text_elem)
        
        return None
    
    def _get_rect_from_text_element(self, text_elem: ET.Element) -> ET.Element | None:
        """Get the rect element from a text element's parent group"""
        parent = self._find_parent(self.svg_root, text_elem)
        if parent is not None:
            # Find rect in the parent group
            for rect in parent.findall('{http://www.w3.org/2000/svg}rect'):
                return rect
        return None
    
    def _find_parent(self, root: ET.Element, child: ET.Element) -> ET.Element | None:
        """Find the parent of a given element"""
        for parent in root.iter():
            if child in list(parent):
                return parent
        return None
    
    def update_key_state(self, key_text: str, is_held: bool) -> None:
        """Update the held state of a key"""
        rect = self.find_key_rect(key_text)
        if rect is not None:
            class_attr = rect.get('class', '')
            classes = set(class_attr.split())
            
            if is_held:
                classes.add('held')
                self.held_keys.add(key_text)
            else:
                classes.discard('held')
                self.held_keys.discard(key_text)
            
            # Update the class attribute
            rect.set('class', ' '.join(sorted(classes)))
            
            # Register namespace before converting to string
            ET.register_namespace('', 'http://www.w3.org/2000/svg')
            ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
            
            # Reload the SVG from the modified tree
            svg_bytes = ET.tostring(self.svg_root, encoding='unicode')
            self.renderer.load(svg_bytes.encode('utf-8'))
            
            # Trigger repaint
            self.update()


class KeymapWindow(QMainWindow):
    """Main window for displaying the keymap SVG"""
    
    svg_widget: SvgWidget
    
    def __init__(self, svg_path: Path):
        super().__init__()
        self.setWindowTitle("Keymap Drawer - Live View")
        
        # Create and set the custom SVG widget
        self.svg_widget = SvgWidget(svg_path)
        self.setCentralWidget(self.svg_widget)
        
        # Resize window to fit content
        self.adjustSize()
        
        svg_size = self.svg_widget.size()
        print(f"Window created with size: {svg_size.width()}x{svg_size.height()}")
        print("Press 'x' to exit, or press other keys to see them highlighted...")
        
    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        """Handle key press - exit on 'x', highlight other keys"""
        if a0 is None:
            return
            
        key_text = a0.text()
        
        if key_text.lower() == 'x':
            print("Exiting...")
            _ = self.close()
            return
        
        if key_text:
            self.svg_widget.update_key_state(key_text, is_held=True)
    
    def keyReleaseEvent(self, a0: QKeyEvent | None) -> None:
        """Handle key release - remove highlight"""
        if a0 is None:
            return
            
        key_text = a0.text()
        
        if key_text and key_text.lower() != 'x':
            self.svg_widget.update_key_state(key_text, is_held=False)
    
    def showEvent(self, a0: QShowEvent | None) -> None:
        """Called when window is shown"""
        super().showEvent(a0)
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
    sys.exit(exit_code)
