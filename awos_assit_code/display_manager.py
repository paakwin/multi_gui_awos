from screeninfo import get_monitors
import tkinter as tk

class DisplayManager:
    def __init__(self):
        self.root = tk.Tk()
        self.monitors = get_monitors()
        self.setup_display()
        
    def setup_display(self):
        if len(self.monitors) == 0:
            raise RuntimeError("No displays detected")
            
        # If only one display available, use it
        if len(self.monitors) == 1:
            self.setup_single_display()
        else:
            self.setup_dual_display()
    
    def setup_single_display(self):
        display = self.monitors[0]
        # Center the window on available display
        window_width = min(256, display.width)
        window_height = min(192, display.height)
        x = display.x + (display.width - window_width) // 2
        y = display.y + (display.height - window_height) // 2
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.setup_gui(self.root)
    
    def setup_dual_display(self):
        # Try to identify P5 panel (smaller display)
        displays = sorted(self.monitors, key=lambda m: m.width * m.height)
        p5_display = displays[0]  # Smallest display
        
        # Create window for P5 panel
        self.root.geometry(f"256x192+{p5_display.x}+{p5_display.y}")
        self.root.attributes('-type', 'dock')
        self.root.overrideredirect(True)
        self.setup_gui(self.root)
    
    def setup_gui(self, window):
        # Add your GUI elements here
        pass