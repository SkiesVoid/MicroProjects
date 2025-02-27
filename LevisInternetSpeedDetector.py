import subprocess
import tkinter as tk
from tkinter import messagebox

def test_internet_speed():
    # Run the speedtest-cli command and capture its output
    result = subprocess.run(['speedtest-cli', '--simple'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Check if the command was successful
    if result.returncode == 0:
        output = result.stdout
    else:
        output = f"Error: {result.stderr}"
    
    return output

def display_result():
    # Get the result of the speed test
    speed_test_result = test_internet_speed()  # Get internet speed result
    
    # Display the result in the output text box
    output_text.delete(1.0, tk.END)  # Clear the previous output
    output_text.insert(tk.END, speed_test_result)

# Create the main window
root = tk.Tk()
root.title("Levi's Internet Speed Tester")

# Create and place a button to start the speed test
test_button = tk.Button(root, text="Test Internet Speed", command=display_result)
test_button.pack(pady=10)

# Create and place a Text widget to display the result
output_text = tk.Text(root, height=10, width=30)
output_text.pack(pady=10)

# Create and place a Text widget for the disclaimer
disclaimer_text = tk.Text(root, height=3, width=50, wrap=tk.WORD)
disclaimer_text.pack(pady=10)
disclaimer_text.insert(tk.END, "To show the network info, go into the CMD prompt and type: netsh wlan show interfaces")
disclaimer_text.config(state=tk.DISABLED)  # Make the disclaimer text box read-only

# Start the main event loop
root.mainloop()
