from PIL import Image
import tkinter as tk

def check_image_and_screen():
    # Check screen size
    root = tk.Tk()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.destroy()
    
    # Check image size
    image_path = "images/Final.png"
    try:
        with Image.open(image_path) as img:
            img_width, img_height = img.size
            
            print("Current dimensions:")
            print(f"Screen size: {screen_width}x{screen_height} pixels")
            print(f"Image size: {img_width}x{img_height} pixels")
            
            # Force resize to screen dimensions
            new_width = screen_width
            new_height = screen_height
            
            print("\nResizing to screen dimensions:")
            print(f"New image size: {new_width}x{new_height} pixels")
            
            # Option to resize
            response = input("\nDo you want to resize the image to match screen size? (y/n): ")
            if response.lower() == 'y':
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                resized_img.save("images/Final.png")
                print("Resized image saved as 'Final.png'")
    
    except FileNotFoundError:
        print(f"Error: Image file not found at {image_path}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_image_and_screen()