
import sys
from argparse import Namespace
from pathlib import Path
import xml.etree.ElementTree as ET

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QKeyEvent, QPainter, QShowEvent, QPaintEvent, QColor, QMouseEvent
from PyQt6.QtCore import QSize, Qt, QPoint

from keymap_drawer.config import Config

# Try to import pynput for global keyboard monitoring
try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    keyboard = None  # type: ignore


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
        
        # Enable transparent background for the widget
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
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
        
        # Fill background with 30% transparent (70% opaque)
        painter.fillRect(self.rect(), QColor(128, 128, 128, 179))
        
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
    keyboard_listener: "keyboard.Listener | None"
    drag_position: QPoint | None
    
    def __init__(self, svg_path: Path):
        super().__init__()
        self.setWindowTitle("Keymap Drawer - Live View")
        
        # Remove window border and frame
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        # Enable transparent background for the window
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Create and set the custom SVG widget
        self.svg_widget = SvgWidget(svg_path)
        self.setCentralWidget(self.svg_widget)
        
        # Resize window to fit content
        self.adjustSize()
        
        # Global keyboard listener (will be started when window is shown)
        self.keyboard_listener = None
        
        # Track drag position for moving the window
        self.drag_position = None
        
        svg_size = self.svg_widget.size()
        print(f"Window created with size: {svg_size.width()}x{svg_size.height()}")
        if PYNPUT_AVAILABLE:
            print("Press 'x' to exit, or press other keys to see them highlighted...")
            print("Global keyboard monitoring is active - keys will be captured even when window is not focused")
        else:
            print("Press 'x' to exit, or press other keys to see them highlighted...")
            print("(Window must be focused to capture keys)")
    
    def start_global_keyboard_listener(self) -> None:
        """Start listening to global keyboard events"""
        if not PYNPUT_AVAILABLE or keyboard is None:
            return
            
        try:
            self.keyboard_listener = keyboard.Listener(
                on_press=self.on_global_key_press,
                on_release=self.on_global_key_release
            )
            self.keyboard_listener.start()
        except Exception as e:
            print(f"Failed to start global keyboard listener: {e}")
            print("Falling back to window-focused keyboard events only")
    
    def on_global_key_press(self, key: "keyboard.Key | keyboard.KeyCode | None") -> bool | None:
        """Handle global key press events"""
        if key is None or keyboard is None:
            return None
            
        # Get the character representation
        key_char = None
        if isinstance(key, keyboard.KeyCode):
            key_char = key.char
        elif isinstance(key, keyboard.Key):
            # Handle special keys if needed
            if key == keyboard.Key.esc:
                key_char = 'x'  # Treat Esc as exit
        
        if key_char:
            if key_char.lower() == 'x':
                print("Exiting...")
                self.close()
                return False  # Stop listener
            else:
                self.svg_widget.update_key_state(key_char, is_held=True)
        
        return None  # Continue listening
    
    def on_global_key_release(self, key: "keyboard.Key | keyboard.KeyCode | None") -> bool | None:
        """Handle global key release events"""
        if key is None or keyboard is None:
            return None
            
        # Get the character representation
        key_char = None
        if isinstance(key, keyboard.KeyCode):
            key_char = key.char
        
        if key_char and key_char.lower() != 'x':
            self.svg_widget.update_key_state(key_char, is_held=False)
        
        return None  # Continue listening
    
    def closeEvent(self, event) -> None:
        """Clean up when window is closed"""
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        super().closeEvent(event)
    
    def showEvent(self, a0: QShowEvent | None) -> None:
        """Called when window is shown"""
        super().showEvent(a0)
        # Start global keyboard listener after window is shown
        if PYNPUT_AVAILABLE:
            self.start_global_keyboard_listener()
        print("Window is now visible!")
        
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
    
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Handle mouse press to start dragging"""
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        """Handle mouse move to drag the window"""
        if event is not None and event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        """Handle mouse release to stop dragging"""
        if event is not None:
            self.drag_position = None
            event.accept()


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
