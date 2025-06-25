import tkinter as tk
from PIL import Image, ImageTk

class WidgetPositioner:
    def __init__(self, root):
        self.root = root
        self.root.title("Widget Position Mapper")
        self.root.attributes('-fullscreen', True)
        
        # Initialize variables
        self.dragged_widget = None
        self.offset_x = 0 
        self.offset_y = 0
        self.widgets = {}
        self.positions = {}

        # Set up canvas
        self.canvas = tk.Canvas(root)
        self.canvas.pack(fill='both', expand=True)

        # Load and display background image
        self.load_background()
        
        # Create sample widgets with static data
        self.create_widgets()
        
        # Bind events
        self.bind_events()
        
        # Add save button
        self.save_button = tk.Button(root, text="Save Positions", command=self.save_positions)
        self.save_button.place(x=10, y=10)
        
        # Add exit button
        self.exit_button = tk.Button(root, text="Exit", command=root.destroy)
        self.exit_button.place(x=100, y=10)

    def load_background(self):
        try:
            img = Image.open("./images/final_blank.png")
            img = img.resize((self.root.winfo_screenwidth(), self.root.winfo_screenheight()))
            self.bg_image = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, image=self.bg_image, anchor='nw')
        except Exception as e:
            print(f"Error loading background: {e}")
            
    def create_widgets(self):
        # Sample data for each sensor including states
        self.widget_configs = {
            'temperature': {'text': '25.6', 'size': 100, 'pos': (200, 180)},
            'humidity': {'text': '65.2%', 'size': 60, 'pos': (840, 186)},
            'humidity_state': {'text': 'HIGH', 'size': 40, 'pos': (550, 575)},
            'pressure': {'text': '1013.2 hPa', 'size': 50, 'pos': (124, 521)},
            'wind_speed': {'text': '15.7 km/h', 'size': 70, 'pos': (1452, 210)},
            'wind_direction': {'text': '180°', 'size': 60, 'pos': (1520, 560)},
            'rainfall': {'text': '2.5 mm', 'size': 60, 'pos': (855, 520)},
            'uv': {'text': '5.8', 'size': 60, 'pos': (1800, 900)},
            'uv_state': {'text': 'MODERATE', 'size': 40, 'pos': (1800, 1000)},
            'aqi': {'text': '45', 'size': 60, 'pos': (666, 900)},
            'aqi_state': {'text': 'GOOD', 'size': 40, 'pos': (600, 1000)},
            # Add time and date widgets
            'current_day': {'text': 'SUNDAY', 'size': 55, 'pos': (730, 10)},
            'current_date': {'text': '25-05-2025', 'size': 55, 'pos': (30, 10)},
            'current_time': {'text': '12:30:45', 'size': 55, 'pos': (1550, 10)},
            'sunrise': {'text': '06:00', 'size': 70, 'pos': (1100, 848)},
            'sunset': {'text': '18:30', 'size': 70, 'pos': (1100, 938)}
        }

        for name, config in self.widget_configs.items():
            widget = self.canvas.create_text(
                config['pos'][0],
                config['pos'][1],
                text=config['text'],
                font=('Digital-7', config['size'], 'bold'),
                fill='white',
                tags=(name, 'draggable')  # Add both name and draggable tags
            )
            self.widgets[name] = widget
            self.positions[name] = config['pos']

        # Add size adjustment controls
        self.size_frame = tk.Frame(self.root)
        self.size_frame.place(x=10, y=50)
        
        tk.Label(self.size_frame, text="Adjust Size:").pack()
        self.size_var = tk.StringVar()
        self.size_entry = tk.Entry(self.size_frame, textvariable=self.size_var, width=5)
        self.size_entry.pack(side='left')
        
        tk.Button(self.size_frame, text="Apply", command=self.adjust_size).pack(side='left')

    def adjust_size(self):
        """Adjust the font size of the selected widget"""
        if self.dragged_widget:
            try:
                new_size = int(self.size_var.get())
                widget_name = self.canvas.gettags(self.dragged_widget)[0]
                self.widget_configs[widget_name]['size'] = new_size
                
                # Update the widget's font size
                self.canvas.itemconfig(
                    self.dragged_widget,
                    font=('Digital-7', new_size, 'bold')
                )
                print(f"Updated {widget_name} size to {new_size}")
            except ValueError:
                print("Please enter a valid number for size")

    def bind_events(self):
        self.canvas.tag_bind('all', '<Button-1>', self.drag_start)
        self.canvas.tag_bind('all', '<B1-Motion>', self.drag_motion)
        self.canvas.tag_bind('all', '<ButtonRelease-1>', self.drag_stop)
        
    def drag_start(self, event):
        # Get the clicked widget
        self.dragged_widget = self.canvas.find_closest(event.x, event.y)[0]
        # Calculate offset from widget position to mouse position
        coords = self.canvas.coords(self.dragged_widget)
        self.offset_x = event.x - coords[0]
        self.offset_y = event.y - coords[1]
        
    def drag_motion(self, event):
        if self.dragged_widget:
            # Move the widget
            new_x = event.x - self.offset_x
            new_y = event.y - self.offset_y
            self.canvas.coords(self.dragged_widget, new_x, new_y)
            
            # Update positions dictionary
            widget_name = self.canvas.gettags(self.dragged_widget)[0]
            self.positions[widget_name] = (int(new_x), int(new_y))
            
    def drag_stop(self, event):
        if self.dragged_widget:
            widget_name = self.canvas.gettags(self.dragged_widget)[0]
            print(f"{widget_name}: {self.positions[widget_name]}")
            # Update size entry with current widget's size
            self.size_var.set(str(self.widget_configs[widget_name]['size']))
        self.dragged_widget = None

    def save_positions(self):
        widget_config = "{\n"
        for name, pos in self.positions.items():
            size = self.widget_configs[name]['size']
            widget_config += f"    '{name}_value': {{\n"
            widget_config += f"        'size': {size}, 'color': '#FFFFFF', "
            widget_config += f"'position': {pos}, 'anchor': 'center'\n"
            widget_config += "    },\n"
        widget_config += "}"
        
        with open('widget_positions.py', 'w') as f:
            f.write(widget_config)
        print("Positions saved to widget_positions.py")

if __name__ == '__main__':
    root = tk.Tk()
    app = WidgetPositioner(root)
    root.mainloop()