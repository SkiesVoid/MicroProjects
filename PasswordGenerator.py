import tkinter as tk
import random
import string

def generate_string():
    num_sets = int(dropdown_var.get())
    characters = string.ascii_letters + string.digits + string.punctuation
    random_strings = '\n'.join(''.join(random.choices(characters, k=12)) for _ in range(num_sets))
    text_box.delete("1.0", tk.END)
    text_box.insert(tk.END, random_strings)

# Create the main window
root = tk.Tk()
root.title("Levi's Password Generator")
root.geometry("600x600")

# Create a dropdown menu for number of sets
dropdown_var = tk.StringVar(value="1")
dropdown = tk.OptionMenu(root, dropdown_var, *[str(i) for i in range(1, 11)])
dropdown.pack(pady=10)

# Create a button to generate the string
button = tk.Button(root, text="Generate 12 Character Password", command=generate_string)
button.pack(pady=10)

# Create a text box to display the generated strings
text_box = tk.Text(root, height=20, width=30, font=("Arial", 12))
text_box.pack(pady=10)

# Run the GUI event loop
root.mainloop()