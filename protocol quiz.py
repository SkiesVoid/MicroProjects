import tkinter as tk
from tkinter import messagebox
import random

# Quiz data: Each question contains the protocol, question text, a list of options, and the correct answer.
quiz_data = [
    # SSH questions
    {"protocol": "SSH", "question": "What is the role of SSH?", 
     "options": ["Secure remote access", "File transfer", "Email service", "Web browsing"], 
     "answer": "Secure remote access"},
    {"protocol": "SSH", "question": "How is SSH typically used?", 
     "options": ["Remote server management", "DNS resolution", "Network time synchronization", "Directory lookup"], 
     "answer": "Remote server management"},
    {"protocol": "SSH", "question": "Which port is SSH commonly run on?", 
     "options": ["22", "80", "443", "25"], 
     "answer": "22"},
    
    # DNS questions
    {"protocol": "DNS", "question": "What is the role of DNS?", 
     "options": ["Translating domain names to IP addresses", "Encrypting communication", "Transferring files", "Monitoring network devices"], 
     "answer": "Translating domain names to IP addresses"},
    {"protocol": "DNS", "question": "How is DNS used in networks?", 
     "options": ["To resolve domain names", "To synchronize time", "For secure remote access", "For email transmission"], 
     "answer": "To resolve domain names"},
    {"protocol": "DNS", "question": "Which type of DNS record maps a domain name to an IP address?", 
     "options": ["A record", "MX record", "CNAME record", "TXT record"], 
     "answer": "A record"},
    
    # DHCP questions
    {"protocol": "DHCP", "question": "What is the role of DHCP?", 
     "options": ["Automatically assigns IP addresses", "Encrypts web traffic", "Manages user directories", "Handles file transfers"], 
     "answer": "Automatically assigns IP addresses"},
    {"protocol": "DHCP", "question": "How is DHCP typically used?", 
     "options": ["For automated network configuration", "For remote command execution", "For file sharing", "For email management"], 
     "answer": "For automated network configuration"},
    {"protocol": "DHCP", "question": "What does a DHCP lease time determine?", 
     "options": ["Duration an IP address is assigned", "The speed of data transfer", "Encryption duration", "Network routing efficiency"], 
     "answer": "Duration an IP address is assigned"},
    
    # LDAP questions
    {"protocol": "LDAP", "question": "What is the role of LDAP?", 
     "options": ["Accessing and managing directory services", "Encrypting communications", "Monitoring network performance", "Resolving domain names"], 
     "answer": "Accessing and managing directory services"},
    {"protocol": "LDAP", "question": "How is LDAP typically used?", 
     "options": ["For centralized user management", "For secure file transfers", "For network time synchronization", "For remote access"], 
     "answer": "For centralized user management"},
    {"protocol": "LDAP", "question": "LDAP is commonly used for managing which of the following?", 
     "options": ["User and group information", "Network routing", "Web traffic encryption", "IP addressing"], 
     "answer": "User and group information"},
    
    # SNMP questions
    {"protocol": "SNMP", "question": "What is the role of SNMP?", 
     "options": ["Monitoring and managing network devices", "Translating domain names", "Encrypting data", "Transferring files"], 
     "answer": "Monitoring and managing network devices"},
    {"protocol": "SNMP", "question": "How is SNMP typically used?", 
     "options": ["For network monitoring", "For secure remote access", "For file transfers", "For email transmission"], 
     "answer": "For network monitoring"},
    {"protocol": "SNMP", "question": "SNMP operates on which network layer?", 
     "options": ["Application layer", "Transport layer", "Data link layer", "Physical layer"], 
     "answer": "Application layer"},
    
    # NTP questions
    {"protocol": "NTP", "question": "What is the role of NTP?", 
     "options": ["Synchronizing clocks across devices", "Transferring files", "Managing network addresses", "Accessing directories"], 
     "answer": "Synchronizing clocks across devices"},
    {"protocol": "NTP", "question": "How is NTP typically used?", 
     "options": ["For time synchronization", "For DNS resolution", "For remote command access", "For file sharing"], 
     "answer": "For time synchronization"},
    {"protocol": "NTP", "question": "Which port does NTP usually use?", 
     "options": ["123", "80", "53", "22"], 
     "answer": "123"},
    
    # IP/TCP/UDP questions
    {"protocol": "IP/TCP/UDP", "question": "What is the role of IP/TCP/UDP?", 
     "options": ["Core protocols for routing and data transmission", "Managing user directories", "Monitoring network performance", "Encrypting web traffic"], 
     "answer": "Core protocols for routing and data transmission"},
    {"protocol": "IP/TCP/UDP", "question": "How are IP/TCP/UDP typically used?", 
     "options": ["For routing, connection establishment, and fast data transfer", "For DNS resolution", "For directory services", "For network time synchronization"], 
     "answer": "For routing, connection establishment, and fast data transfer"},
    {"protocol": "IP/TCP/UDP", "question": "Which protocol among IP, TCP, and UDP is connectionless?", 
     "options": ["UDP", "TCP", "IP", "HTTP"], 
     "answer": "UDP"},
    
    # HTTP/HTTPS questions
    {"protocol": "HTTP/HTTPS", "question": "What is the role of HTTP/HTTPS?", 
     "options": ["Transferring web pages and securing web traffic", "Managing remote access", "Synchronizing network time", "Translating domain names"], 
     "answer": "Transferring web pages and securing web traffic"},
    {"protocol": "HTTP/HTTPS", "question": "How is HTTP/HTTPS typically used?", 
     "options": ["For web browsing and accessing admin consoles", "For file sharing", "For directory management", "For monitoring network devices"], 
     "answer": "For web browsing and accessing admin consoles"},
    {"protocol": "HTTP/HTTPS", "question": "Which protocol ensures encrypted communication over the web?", 
     "options": ["HTTPS", "HTTP", "FTP", "SMTP"], 
     "answer": "HTTPS"}
]

# Randomize the order of all questions in the quiz
random.shuffle(quiz_data)

class QuizApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Network Protocols Quiz")
        self.current_question = 0
        self.score = 0

        # Create a frame for the quiz content
        self.frame = tk.Frame(root, padx=20, pady=20)
        self.frame.pack()

        # Label to show the question text and later feedback
        self.question_label = tk.Label(self.frame, text="", wraplength=500, justify="left", font=("Helvetica", 14))
        self.question_label.pack(pady=(0, 10))

        # Variable to hold the selected answer
        self.selected_answer = tk.StringVar()

        # Radio buttons for options
        self.option_buttons = []
        for i in range(4):
            rb = tk.Radiobutton(self.frame, text="", variable=self.selected_answer, value="", font=("Helvetica", 12))
            rb.pack(anchor="w")
            self.option_buttons.append(rb)

        # Button to submit answer
        self.submit_button = tk.Button(self.frame, text="Submit Answer", command=self.submit_answer, font=("Helvetica", 12))
        self.submit_button.pack(pady=(10, 0))

        # Start the quiz by displaying the first question
        self.display_question()

    def display_question(self):
        """Display the current question and its shuffled options."""
        if self.current_question < len(quiz_data):
            q_data = quiz_data[self.current_question]
            protocol = q_data["protocol"]
            question_text = f"[{protocol}] {q_data['question']}"
            self.question_label.config(text=question_text)
            self.selected_answer.set(None)
            
            # Shuffle options before displaying
            options = q_data["options"].copy()
            random.shuffle(options)
            
            # Update radio buttons with shuffled options
            for i, option in enumerate(options):
                self.option_buttons[i].config(text=option, value=option, state=tk.NORMAL)
            # Enable the submit button
            self.submit_button.config(state=tk.NORMAL)
        else:
            self.end_quiz()

    def submit_answer(self):
        """Check the selected answer, update score, display feedback, and proceed after 2 seconds."""
        selected = self.selected_answer.get()
        if not selected:
            messagebox.showwarning("No selection", "Please select an answer before submitting.")
            return

        # Disable the options and submit button to prevent further input during feedback
        for btn in self.option_buttons:
            btn.config(state=tk.DISABLED)
        self.submit_button.config(state=tk.DISABLED)

        correct_answer = quiz_data[self.current_question]["answer"]
        if selected == correct_answer:
            self.score += 1
            feedback = "Correct!"
        else:
            feedback = "Incorrect!"
        
        # Display feedback message
        self.question_label.config(text=feedback)
        # Wait for 2 seconds before moving to the next question
        self.root.after(2000, self.next_question)

    def next_question(self):
        """Increment question counter and display the next question."""
        self.current_question += 1
        self.display_question()

    def end_quiz(self):
        """Display the final score and a retry button."""
        self.frame.destroy()
        self.result_frame = tk.Frame(self.root, padx=20, pady=20)
        self.result_frame.pack()
        result_label = tk.Label(self.result_frame, text=f"Quiz Complete!\nYour Score: {self.score} out of {len(quiz_data)}", font=("Helvetica", 16))
        result_label.pack(pady=(0, 10))
        retry_button = tk.Button(self.result_frame, text="Retry", command=self.retry_quiz, font=("Helvetica", 12))
        retry_button.pack()

    def retry_quiz(self):
        """Reset quiz variables and restart the quiz."""
        self.current_question = 0
        self.score = 0
        self.result_frame.destroy()
        # Recreate the quiz frame
        self.frame = tk.Frame(self.root, padx=20, pady=20)
        self.frame.pack()

        self.question_label = tk.Label(self.frame, text="", wraplength=500, justify="left", font=("Helvetica", 14))
        self.question_label.pack(pady=(0, 10))

        self.selected_answer = tk.StringVar()

        self.option_buttons = []
        for i in range(4):
            rb = tk.Radiobutton(self.frame, text="", variable=self.selected_answer, value="", font=("Helvetica", 12))
            rb.pack(anchor="w")
            self.option_buttons.append(rb)

        self.submit_button = tk.Button(self.frame, text="Submit Answer", command=self.submit_answer, font=("Helvetica", 12))
        self.submit_button.pack(pady=(10, 0))
        self.display_question()

if __name__ == "__main__":
    root = tk.Tk()
    app = QuizApp(root)
    root.mainloop()
