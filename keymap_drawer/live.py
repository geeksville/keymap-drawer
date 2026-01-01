
import sys
from argparse import Namespace
from pathlib import Path
import xml.etree.ElementTree as ET
from threading import Thread
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QKeyEvent, QPainter, QShowEvent, QPaintEvent, QColor, QMouseEvent
from PyQt6.QtCore import QSize, Qt, QPoint, pyqtSignal, QObject

from keymap_drawer.config import Config

# Try to import evdev for global keyboard monitoring
try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    if TYPE_CHECKING:
        evdev = None  # type: ignore

# Map evdev key names to SVG labels
EVDEV_KEY_MAP = {
    'leftshift': 'Shift',
    'rightshift': 'Shift',
    'leftctrl': 'Control',
    'rightctrl': 'Control',
    'leftalt': 'Alt',
    'rightalt': 'AltGr',
    'leftmeta': 'Meta',
    'rightmeta': 'Meta',
    'capslock': 'Caps',
    'tab': 'Tab',
    'enter': 'Enter',
    'space': 'Space',
    'backspace': 'Backspace',
    'delete': 'Delete',
    'esc': 'Esc',
    'escape': 'Esc',
}

# Map Qt key codes to SVG labels
QT_KEY_MAP = {
    Qt.Key.Key_Shift: 'Shift',
    Qt.Key.Key_Control: 'Control',
    Qt.Key.Key_Alt: 'Alt',
    Qt.Key.Key_AltGr: 'AltGr',
    Qt.Key.Key_Meta: 'Meta',
    Qt.Key.Key_Super_L: 'Meta',
    Qt.Key.Key_Super_R: 'Meta',
    Qt.Key.Key_CapsLock: 'Caps',
    Qt.Key.Key_Tab: 'Tab',
    Qt.Key.Key_Return: 'Enter',
    Qt.Key.Key_Enter: 'Enter',
    Qt.Key.Key_Space: 'Space',
    Qt.Key.Key_Backspace: 'Backspace',
    Qt.Key.Key_Delete: 'Delete',
    Qt.Key.Key_Escape: 'Esc',
}


class KeyboardMonitor(QObject):
    """Monitor keyboard events using evdev in background thread"""
    
    key_pressed = pyqtSignal(str)
    key_released = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.stop_flag = False
        self.thread: Thread | None = None
    
    def find_keyboard_device(self) -> "InputDevice | None":
        """Find a keyboard device from available input devices"""
        if not EVDEV_AVAILABLE:
            return None
        
        try:
            devices = [InputDevice(path) for path in evdev.list_devices()]
            for device in devices:
                # Look for a device with keyboard capabilities
                caps = device.capabilities()
                if ecodes.EV_KEY in caps and any(
                    key in caps[ecodes.EV_KEY] 
                    for key in [ecodes.KEY_A, ecodes.KEY_B, ecodes.KEY_C]
                ):
                    return device
        except (PermissionError, OSError) as e:
            print(f"Cannot access input devices: {e}")
            print("Tip: Add your user to the 'input' group with: sudo usermod -a -G input $USER")
            return None
        
        return None
    
    def start(self) -> bool:
        """Start monitoring keyboard events in background thread"""
        device = self.find_keyboard_device()
        if not device:
            return False
        
        print(f"Monitoring keyboard: {device.name}")
        
        def event_loop():
            """Background thread that monitors keyboard events"""
            try:
                for event in device.read_loop():
                    if self.stop_flag:
                        break
                    
                    if event.type == ecodes.EV_KEY:
                        key_event = categorize(event)
                        
                        # Map keycode to character
                        keycode = key_event.keycode
                        if isinstance(keycode, list):
                            keycode = keycode[0]
                        
                        # Strip KEY_ prefix and convert to lowercase
                        if keycode.startswith('KEY_'):
                            key_name = keycode[4:].lower()
                            
                            # Check if it's a special key that needs mapping
                            key_char = EVDEV_KEY_MAP.get(key_name, key_name)
                            
                            # Only handle single characters or mapped special keys
                            if len(key_char) == 1 or key_name in EVDEV_KEY_MAP:
                                if key_event.keystate == key_event.key_down:
                                    self.key_pressed.emit(key_char)
                                elif key_event.keystate == key_event.key_up:
                                    self.key_released.emit(key_char)
            except Exception as e:
                print(f"Keyboard monitoring error: {e}")
            finally:
                device.close()
        
        self.thread = Thread(target=event_loop, daemon=True)
        self.thread.start()
        return True
    
    def stop(self):
        """Stop monitoring keyboard events"""
        self.stop_flag = True
        if self.thread:
            self.thread.join(timeout=1.0)


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
    drag_position: QPoint | None
    keyboard_monitor: KeyboardMonitor | None
    
    def __init__(self, svg_path: Path):
        super().__init__()
        self.setWindowTitle("Keymap Drawer - Live View")
        
        # Remove window border and frame, keep on top
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        # Enable transparent background for the window
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Create and set the custom SVG widget
        self.svg_widget = SvgWidget(svg_path)
        self.setCentralWidget(self.svg_widget)
        
        # Resize window to fit content
        self.adjustSize()
        
        # Track drag position for moving the window
        self.drag_position = None
        
        # Keyboard monitor for global events
        self.keyboard_monitor = None
        
        svg_size = self.svg_widget.size()
        print(f"Window created with size: {svg_size.width()}x{svg_size.height()}")
        print("Press 'x' to exit. Drag window to reposition it.")
    
    def showEvent(self, a0: QShowEvent | None) -> None:
        """Called when window is shown"""
        super().showEvent(a0)
        
        # Try to start global keyboard monitoring
        if EVDEV_AVAILABLE:
            self.keyboard_monitor = KeyboardMonitor()
            self.keyboard_monitor.key_pressed.connect(self.on_global_key_press)
            self.keyboard_monitor.key_released.connect(self.on_global_key_release)
            
            if self.keyboard_monitor.start():
                print("Global keyboard monitoring active - keys captured even when window not focused")
            else:
                print("Could not start global monitoring - window must be focused to capture keys")
                self.keyboard_monitor = None
        else:
            print("Global monitoring unavailable - window must be focused to capture keys")
            print("Tip: Install evdev with: poetry install -E live")
        
        print("Window is now visible!")
    
    def on_global_key_press(self, key_char: str) -> None:
        """Handle global key press from keyboard monitor"""
        if key_char == 'x':
            print("Exiting...")
            self.close()
        else:
            self.svg_widget.update_key_state(key_char, is_held=True)
    
    def on_global_key_release(self, key_char: str) -> None:
        """Handle global key release from keyboard monitor"""
        if key_char != 'x':
            self.svg_widget.update_key_state(key_char, is_held=False)
    
    def closeEvent(self, event) -> None:
        """Clean up when window is closed"""
        if self.keyboard_monitor:
            self.keyboard_monitor.stop()
        super().closeEvent(event)
        
    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        """Handle key press - exit on 'x', highlight other keys"""
        if a0 is None:
            return
        
        # Try to map special keys first
        key_char = QT_KEY_MAP.get(a0.key())
        if not key_char:
            # Fall back to text for regular keys
            key_char = a0.text()
        
        if key_char and key_char.lower() == 'x':
            print("Exiting...")
            _ = self.close()
            return
        
        if key_char:
            self.svg_widget.update_key_state(key_char, is_held=True)
    
    def keyReleaseEvent(self, a0: QKeyEvent | None) -> None:
        """Handle key release - remove highlight"""
        if a0 is None:
            return
        
        # Try to map special keys first
        key_char = QT_KEY_MAP.get(a0.key())
        if not key_char:
            # Fall back to text for regular keys
            key_char = a0.text()
        
        if key_char and key_char.lower() != 'x':
            self.svg_widget.update_key_state(key_char, is_held=False)
    
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Handle mouse press to start dragging"""
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            # On Wayland, use startSystemMove() which is compositor-aware
            # On X11, fall back to manual dragging
            if hasattr(self.windowHandle(), 'startSystemMove') and self.windowHandle():
                # Try Wayland-native move first
                self.windowHandle().startSystemMove()
            else:
                # Fall back to manual dragging for X11
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        """Handle mouse move to drag the window (X11 only, Wayland uses startSystemMove)"""
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
