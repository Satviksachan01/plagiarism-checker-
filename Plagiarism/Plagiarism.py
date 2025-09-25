
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import sqlite3
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import requests
import PyPDF2
import threading
import openai

# ---- CONFIG ----
DB_NAME = "plagiarism_checker.db"
API_KEY = "AIzaSyCqIelwmxzbPi24dFOsh--hGvrLvhT2BTk"           # Replace with your Google API key
SEARCH_ENGINE_ID = "329542aa2afe74c5b"  # Replace with your Search Engine ID
OPENAI_API_KEY = "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"       # Replace with your OpenAI API key

openai.api_key = OPENAI_API_KEY

# ------------------ DATABASE ------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS submissions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        content TEXT)''')
    conn.commit()
    conn.close()

def save_submission(title, content):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO submissions (title, content) VALUES (?, ?)", (title, content))
    conn.commit()
    conn.close()

def load_submissions():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM submissions", conn)
    conn.close()
    return df

# ------------------ CHECKERS ------------------
def check_similarity(new_text, old_texts):
    if not old_texts:
        return []
    vectorizer = CountVectorizer().fit_transform([new_text] + old_texts)
    vectors = vectorizer.toarray()
    similarities = cosine_similarity(vectors)[0][1:]
    return [round(score * 100, 2) for score in similarities]

def check_online(snippet):
    try:
        query = '+'.join(snippet.strip().split())
        url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={API_KEY}&cx={SEARCH_ENGINE_ID}"
        response = requests.get(url)
        results = response.json()
        return bool(results.get('items'))
    except Exception as e:
        print("Error in online check:", e)
        return False

# ------------------ FILE IMPORT ------------------
def browse_file():
    file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("PDF files", "*.pdf")])
    if not file_path:
        return
    if file_path.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            input_text.delete(1.0, tk.END)
            input_text.insert(tk.END, f.read())
    elif file_path.endswith(".pdf"):
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text = "\n".join(page.extract_text() or '' for page in reader.pages)
            input_text.delete(1.0, tk.END)
            input_text.insert(tk.END, text)

# ------------------ EXPORT ------------------
def export_results():
    file_path = filedialog.asksaveasfilename(defaultextension=".txt",
                                             filetypes=[("Text files", "*.txt")])
    if file_path:
        content = output_area.get(1.0, tk.END)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        messagebox.showinfo("Export", "Results exported successfully!")

# ------------------ REWRITE FUNCTION ------------------
def rewrite_text(text):
    """Use OpenAI GPT to paraphrase the input text."""
    try:
        prompt = (
            "Paraphrase the following text to make it unique and not detectable as plagiarism, "
            "while keeping the original meaning:\n\n" + text
        )
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.7,
        )
        rewritten = response['choices'][0]['message']['content'].strip()
        return rewritten
    except Exception as e:
        print("Error in rewriting:", e)
        return None

# ------------------ MAIN PROCESS ------------------
def process_submission():
    title = title_entry.get().strip()
    content = input_text.get("1.0", tk.END).strip()
    if not title or not content:
        messagebox.showwarning("Input Error", "Please enter both title and content.")
        progress_bar.stop()
        submit_btn.config(state=tk.NORMAL)
        return

    output_area.delete(1.0, tk.END)
    output_area.insert(tk.END, "🔄 Checking plagiarism, please wait...\n\n")

    # Local DB similarity check
    old_data = load_submissions()
    old_texts = old_data['content'].tolist() if not old_data.empty else []
    similarity_scores = check_similarity(content, old_texts)

    result_text = "📁 Local Database Results:\n"
    if not similarity_scores:
        result_text += "No previous submissions to compare.\n"
    else:
        for i, score in enumerate(similarity_scores):
            title_compared = old_data.iloc[i]['title']
            result_text += f"  • Similarity with '{title_compared}': {score}%\n"
        overall = round(sum(similarity_scores)/len(similarity_scores), 2)
        result_text += f"\n🧮 Overall Similarity Score: {overall}%\n"

    # Online check (top 3 long lines)
    result_text += "\n🌐 Web Results:\n"
    lines = [line for line in content.split("\n") if len(line.strip()) > 30][:3]
    for line in lines:
        if check_online(line):
            result_text += f"  ➤ Online match found for: \"{line.strip()[:100]}...\"\n"
        else:
            result_text += f"  ✖ No match found for: \"{line.strip()[:100]}...\"\n"

    # Save original submission
    save_submission(title, content)

    # Now rewrite the text to remove plagiarism
    output_area.delete(1.0, tk.END)
    output_area.insert(tk.END, result_text + "\n\n♻️ Rewriting text to avoid plagiarism...\n")
    
    rewritten = rewrite_text(content)
    if rewritten:
        output_area.insert(tk.END, "\n✅ Rewritten Content:\n")
        output_area.insert(tk.END, rewritten)
    else:
        output_area.insert(tk.END, "\n❌ Failed to rewrite content. Please try again.")

    progress_bar.stop()
    submit_btn.config(state=tk.NORMAL)

def submit_content():
    submit_btn.config(state=tk.DISABLED)
    progress_bar.start()
    threading.Thread(target=process_submission, daemon=True).start()

# ------------------ REWRITE ONLY FUNCTION ------------------
def rewrite_only_text():
    content = input_text.get("1.0", tk.END).strip()
    if not content:
        messagebox.showwarning("Input Error", "Please enter some content to rewrite.")
        return

    output_area.delete(1.0, tk.END)
    output_area.insert(tk.END, "♻️ Rewriting text to avoid plagiarism...\n")
    rewritten = rewrite_text(content)
    if rewritten:
        output_area.insert(tk.END, "\n✅ Rewritten Content:\n")
        output_area.insert(tk.END, rewritten)
    else:
        output_area.insert(tk.END, "\n❌ Failed to rewrite content. Please try again.")

# ------------------ DARK MODE & LIGHT MODE ------------------
def toggle_dark_mode():
    global is_dark
    is_dark = not is_dark
    if is_dark:
        bg_color = "#121212"
        fg_color = "#eeeeee"
        entry_bg = "#1e1e1e"
        btn_bg = "#bb86fc"
        btn_fg = "#000000"
        progress_color = "#bb86fc"
        canvas_bg_color = "#121212"
    else:
        bg_color = light_orange_bg
        fg_color = "#202020"
        entry_bg = "#fff5e6"
        btn_bg = "#c76100"
        btn_fg = "white"
        progress_color = "#c76100"
        canvas_bg_color = light_orange_bg

    root.config(bg=bg_color)
    title_label.config(bg=bg_color, fg=fg_color)
    title_entry.config(bg=entry_bg, fg=fg_color, insertbackground=fg_color)
    input_label.config(bg=bg_color, fg=fg_color)
    input_text.config(bg=entry_bg, fg=fg_color, insertbackground=fg_color)
    output_label.config(bg=bg_color, fg=fg_color)
    output_area.config(bg=entry_bg, fg=fg_color, insertbackground=fg_color)
    btn_frame.config(bg=bg_color)

    for btn in [upload_btn, submit_btn, export_btn, dark_mode_btn]:
        btn.config(bg=btn_bg, fg=btn_fg, activebackground=btn_fg, activeforeground=btn_bg)

    progress_bar.config(style="colored.Horizontal.TProgressbar")
    style.configure("colored.Horizontal.TProgressbar", troughcolor=entry_bg, background=progress_color)

    # Update background canvas colors for light mode artistic background
    if not is_dark:
        create_art_background(canvas_bg_color)
    else:
        canvas.delete("all")
        canvas.config(bg=canvas_bg_color)

# ------------------ TOOLTIP CLASS ------------------
class CreateToolTip(object):
    """Create a tooltip for a given widget"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        widget.bind("<Enter>", self.enter)
        widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(700, self.showtip)

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_:
            self.widget.after_cancel(id_)

    def showtip(self, event=None):
        if self.tipwindow:
            return
        x, y, cx, cy = self.widget.bbox("insert") if self.widget.winfo_ismapped() else (0,0,0,0)
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("tahoma", "9", "normal"))
        label.pack(ipadx=4, ipady=2)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

# ------------------ BUTTON HOVER EFFECT ------------------
def on_enter(e):
    btn = e.widget
    if is_dark:
        btn['background'] = '#d1aaff'  # lighter purple on hover
    else:
        btn['background'] = '#e67300'  # brighter orange on hover

def on_leave(e):
    btn = e.widget
    if is_dark:
        btn['background'] = '#bb86fc'
    else:
        btn['background'] = '#c76100'  # original orange

# ------------------ ARTISTIC LIGHT ORANGE BACKGROUND ------------------
def create_art_background(base_color):
    canvas.delete("all")
    canvas.config(bg=base_color)

    height = 800
    width = 900
    for i in range(0, height, 5):
        r = 255
        g = 200 - int(i / 6)
        b = 150 - int(i / 8)
        g = max(min(g, 255), 100)
        b = max(min(b, 255), 100)
        hex_color = f'#{r:02x}{g:02x}{b:02x}'
        canvas.create_rectangle(0, i, width, i + 5, outline="", fill=hex_color)

    for x, y, r, c in [(150, 150, 90, "#ff6600"), (700, 200, 140, "#cc5200"), (450, 600, 120, "#ff8533")]:
        canvas.create_oval(x - r, y - r, x + r, y + r, outline="", fill=c, stipple='gray50')

    canvas.create_arc(200, 400, 600, 700, start=0, extent=120, fill="#ffad66", outline="")
    canvas.create_arc(300, 500, 700, 800, start=180, extent=100, fill="#ffaa33", outline="")

# ------------------ MAIN UI ------------------
init_db()
root = tk.Tk()
root.title("✨ AI Plagiarism Checker & Rewriter ✨")
root.geometry("900x800")
root.resizable(False, False)

light_orange_bg = "#fff0cc"

style = ttk.Style(root)
style.theme_use('clam')
style.configure("TButton", padding=6, font=("Segoe UI", 11, "bold"), borderwidth=0)
style.configure("TLabel", font=("Segoe UI", 12))
style.configure("colored.Horizontal.TProgressbar", troughcolor="#dcdcdc", background="#c76100", thickness=20)

canvas = tk.Canvas(root, width=900, height=800, highlightthickness=0)
canvas.place(x=0, y=0)

create_art_background(light_orange_bg)

# Title
title_label = tk.Label(root, text="Enter Title:", font=("Segoe UI", 14, "bold"))
title_label.pack(pady=(15, 5))
title_entry = tk.Entry(root, width=70, font=("Consolas", 13))
title_entry.pack(pady=(0, 15))

# Input Box
input_label = tk.Label(root, text="Paste or Upload Your Text:", font=("Segoe UI", 14, "bold"))
input_label.pack()
input_text = scrolledtext.ScrolledText(root, width=100, height=15, wrap=tk.WORD, font=("Consolas", 12))
input_text.pack(padx=15, pady=10)

# Buttons Frame
btn_frame = tk.Frame(root, bg=light_orange_bg)
btn_frame.pack(pady=15)

upload_btn = tk.Button(btn_frame, text="📂 Upload File", command=browse_file, width=15, bg="#c76100", fg="white")
upload_btn.grid(row=0, column=0, padx=12)

submit_btn = tk.Button(btn_frame, text="🚀 Submit & Check + Rewrite", command=submit_content, width=24, bg="#c76100", fg="white")
submit_btn.grid(row=0, column=1, padx=12)

export_btn = tk.Button(btn_frame, text="💾 Export Results", command=export_results, width=15, bg="#c76100", fg="white")
export_btn.grid(row=0, column=2, padx=12)

dark_mode_btn = tk.Button(btn_frame, text="🌓 Toggle Dark Mode", command=toggle_dark_mode, width=18, bg="#c76100", fg="white")
dark_mode_btn.grid(row=0, column=3, padx=12)

# Optional rewrite only button:
# rewrite_btn = tk.Button(btn_frame, text="🔄 Rewrite Only", command=rewrite_only_text, width=15, bg="#c76100", fg="white")
# rewrite_btn.grid(row=0, column=4, padx=12)

# Progress Bar
progress_bar = ttk.Progressbar(root, mode='indeterminate', length=700, style="colored.Horizontal.TProgressbar")
progress_bar.pack(pady=(5, 15))

# Output Box
output_label = tk.Label(root, text="🔍 Plagiarism Check & Rewrite Results:", font=("Segoe UI", 14, "bold"))
output_label.pack()
output_area = scrolledtext.ScrolledText(root, width=100, height=15, wrap=tk.WORD, font=("Consolas", 12))
output_area.pack(padx=15, pady=(5, 15))

# Tooltips
CreateToolTip(title_entry, "Enter a unique title or name for your submission.")
CreateToolTip(input_text, "Paste or upload your text here. Supported: .txt and .pdf files.")
CreateToolTip(upload_btn, "Click to upload a text or PDF file to check plagiarism.")
CreateToolTip(submit_btn, "Start plagiarism check comparing with local and online sources and rewrite.")
CreateToolTip(export_btn, "Save the plagiarism report and rewritten text to a text file.")
CreateToolTip(dark_mode_btn, "Toggle between Dark and Light (orange-themed) modes.")
CreateToolTip(output_area, "View detailed plagiarism check results and rewritten text here.")
# CreateToolTip(rewrite_btn, "Rewrite the input text only, without checking plagiarism.")  # Uncomment if rewrite_btn enabled

# Button hover bindings
for btn in [upload_btn, submit_btn, export_btn, dark_mode_btn]:
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)

# Bind Enter key (Return) to submit_content function
def on_enter_key(event):
    submit_content()
root.bind('<Return>', on_enter_key)

# Initial mode
is_dark = False
toggle_dark_mode()

root.mainloop()
