# Blog2SVG

A tool to convert blog text or URLs into SVG visualizations using Gemini API.

---

## Features

- Accepts either blog text or a blog URL as input.
- Uses Google’s Gemini API to summarize and structure content.
- Outputs a basic SVG visualization based on the result.

---

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/blog2svg.git
    cd blog2svg
    ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Create a `.env` file in the root directory with your Gemini API key:
    ```
    GEMINI_API_KEY="Your API KEY"
    ```

---

## Usage

Run the script:
```bash
python3 svg.py
```

You'll be prompted to:
- Enter a URL of a blog post, OR
- Paste the blog text directly

The script will generate an SVG visualization based on the content.
The resulting SVG will be saved as output.svg in the same directory.

---

## Notes on Visualization Quality

Despite experimenting with various prompts, I've found that the Gemini (2.0 Flash) API doesn't consistently produce visually appealing results for this use case. In comparison, tests with Claude AI (via claude.ai/chats) produced significantly better visualizations for the same inputs.
