import time
import re
import os
import base64
import requests
import sys
from io import BytesIO
from lxml import etree
from PIL import Image
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# === Configuration ===
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

GEMINI_API_URL    = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + GEMINI_API_KEY
TIMEOUT_SECONDS   = 120            # Increased timeout slightly
MAX_RETRIES       = 2              # per-image retries
NUM_IMAGES        = 2              # number of SVGs to generate
VIEWBOX           = "0 0 800 600"  # SVG viewBox dimensions
LOGO_PATH         = "logo.png"     # Path to the logo image
LOGO_SCALE_PCT    = 0.10           # logo width as % of SVG width
LOGO_PADDING_PX   = 10             # padding from edges
OUTPUT_DIR        = "output"       # Directory for saving SVGs

# === Helpers ===

def call_gemini_api(prompt):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        response = requests.post(GEMINI_API_URL, json=payload)
        response.raise_for_status()  # Raise exception for non-200 status codes
        
        # Parse response JSON
        data = response.json()
        
        # Handle potential error structures
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown API error")
            raise RuntimeError(f"Gemini API error: {error_msg}")
        
        # Check for expected response structure
        if not (data.get("candidates") and len(data["candidates"]) > 0 and 
                data["candidates"][0].get("content") and 
                data["candidates"][0]["content"].get("parts") and 
                len(data["candidates"][0]["content"]["parts"]) > 0):
            raise RuntimeError("Unexpected API response structure")
        
        # Extract text from first candidate
        text = data["candidates"][0]["content"]["parts"][0].get("text", "")
        if not text:
            raise RuntimeError("Empty text response from API")
        
        return text
        
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API request failed: {e}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Error parsing API response: {e}")

def extract_svg_block(text):
    match = re.search(r"<svg.*?</svg>", text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        # Add the problematic text to the error for easier debugging
        preview_len = 200
        text_preview = text[:preview_len] + ('...' if len(text) > preview_len else '')
        raise ValueError(f"No valid <svg>...</svg> block found in LLM output. Start of text was: '{text_preview}'")
    return match.group(0)

def extract_blog_prompt(blog_text):
    prompt = f"""
You are a professional concept artist working for a top design agency.
Read this blog text and provide a concise prompt that captures its overall themes and key summary in few sentences.
Try to keep the prompt simple and clear, avoiding complex or technical language.
The prompt should be suitable for generating a simple yet effective SVG illustration.
Output ONLY the prompt text, nothing else.

BLOG TEXT:
"{blog_text}"
"""
    prompt_text = call_gemini_api(prompt)
    return prompt_text.strip()

def make_overview_svg_prompt(prompt, idx):
    """Prompt to generate a full-post overview SVG based on the prompt."""
    return f"""
You are a master SVG artist.

Generate a clean, minimalist SVG illustration (viewBox="{VIEWBOX}") based on the following prompt. The prompt a high level overview of a blog post, the SVG should visually represnt the blog post's main themes and ideas as depicted in the prompt.

“{prompt}”

Requirements:
- Image #{idx}, visually distinct from the other image(s).
- No CSS, JS, or external fonts.
- Use dark theme colors (dark background, light foreground).
- Leave the bottom-right area (approximately x > {int(VIEWBOX.split()[2]) - LOGO_PADDING_PX - int(float(VIEWBOX.split()[2])*LOGO_SCALE_PCT)}, y > {int(VIEWBOX.split()[3]) - LOGO_PADDING_PX - 50}) empty for a logo overlay. Precise coordinates: x={int(VIEWBOX.split()[2]) * (1-LOGO_SCALE_PCT) - LOGO_PADDING_PX} to {VIEWBOX.split()[2]}, y={int(VIEWBOX.split()[3]) - 50 - LOGO_PADDING_PX} to {VIEWBOX.split()[3]}.
- Avoid clutter: use at most 100 graphic elements in total.
- Output ONLY the raw SVG code block, starting exactly with "<svg" and ending exactly with "</svg>". Do not include any explanations, markdown formatting (like ```svg ... ```), or any other text before or after the SVG code.
"""

def validate_svg(svg):
    if not svg.strip().startswith("<svg"):
        return False, "Does not start with <svg>"
    try:
        parser = etree.XMLParser(recover=False, remove_blank_text=True)
        root = etree.fromstring(svg.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as e:
        return False, f"XML syntax error: {e} (line {e.lineno}, column {e.offset})"
    except Exception as e:
        return False, f"XML parsing error: {e}"

    expected_tag = "{http://www.w3.org/2000/svg}svg"
    if root.tag != expected_tag:
         if root.tag == 'svg':
             return False, f"Root element is <svg> but missing the required xmlns namespace declaration ('{expected_tag}')"
         else:
             return False, f"Root element is not <svg> (found <{root.tag}> instead of '{expected_tag}')"

    vb = root.get("viewBox")
    if vb != VIEWBOX:
        return False, f"Unexpected viewBox ('{vb}') vs expected '{VIEWBOX}'"

    # Define the SVG namespace for XPath queries
    ns = {'svg': 'http://www.w3.org/2000/svg'}

    # Refining the XPath to be more precise and namespace-aware
    xpath_query = " | ".join([f".//svg:{name}" for name in ['path', 'rect', 'circle', 'line', 'polygon', 'ellipse', 'polyline', 'text']])
    try:
        # Use the defined namespace prefix 'svg'
        elems = root.xpath(xpath_query, namespaces=ns)
    except etree.XPathSyntaxError as e:
         return False, f"Internal error: Invalid XPath query: {e}" # Should not happen
    except etree.XPathEvalError as e:
         return False, f"XPath evaluation error: {e}"

    # Check for style attributes containing overflow:visible (more robust)
    # Using namespace-aware XPath
    style_elements = root.xpath(".//@style[contains(., 'overflow:visible')]", namespaces=ns)
    if style_elements:
        return False, "Contains style attribute with 'overflow:visible'"

    # Check for <style> tags containing overflow:visible (less common but possible)
    # Using namespace-aware XPath
    style_tags = root.xpath(".//svg:style[contains(text(), 'overflow:visible')]", namespaces=ns)
    if style_tags:
         return False, "Contains <style> tag with 'overflow:visible'"

    return True, "SVG valid"

def add_logo_to_svg(svg):
    try:
        with Image.open(LOGO_PATH) as img:
            w, h = img.size
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            uri = f"data:image/png;base64,{b64}"
    except FileNotFoundError:
        raise FileNotFoundError(f"Logo file not found at {LOGO_PATH}")
    except Exception as e:
        raise RuntimeError(f"Error processing logo image: {e}")

    # parse SVG
    parser = etree.XMLParser(remove_blank_text=True)
    try:
        root = etree.fromstring(svg.encode("utf-8"), parser)
    except etree.XMLSyntaxError as e:
         # This shouldn't happen if validate_svg passed, but defensive check
        raise ValueError(f"Invalid SVG passed to add_logo_to_svg: {e}")

    # compute sizes
    viewbox_parts = root.get("viewBox")
    if not viewbox_parts:
         raise ValueError("SVG missing viewBox attribute")
    try:
        _, _, svg_w, svg_h = map(float, viewbox_parts.split())
    except (ValueError, IndexError):
        raise ValueError(f"Invalid viewBox format: '{viewbox_parts}'")

    logo_w = svg_w * LOGO_SCALE_PCT
    logo_h = h * (logo_w / w) # Calculate height based on aspect ratio
    x = svg_w - logo_w - LOGO_PADDING_PX
    y = svg_h - logo_h - LOGO_PADDING_PX

    # create image element with proper namespace
    # Define the SVG namespace
    SVG_NS = "http://www.w3.org/2000/svg"
    XLINK_NS = "http://www.w3.org/1999/xlink" # Often needed for href, though modern browsers might handle 'href' directly
    NSMAP = {None: SVG_NS, # Default namespace
             'xlink': XLINK_NS}

    img_el = etree.Element("{" + SVG_NS + "}image", nsmap=NSMAP) # Use Clark notation for namespace
    img_el.set("href", uri) # Standard attribute name
    # Consider adding xlink:href for older compatibility if needed:
    # img_el.set("{" + XLINK_NS + "}href", uri)
    img_el.set("width",  str(logo_w))
    img_el.set("height", str(logo_h))
    img_el.set("x",      str(x))
    img_el.set("y",      str(y))
    root.append(img_el)
    
    # Use lxml's recommended way to serialize with XML declaration
    return etree.tostring(root, encoding="unicode", pretty_print=True, xml_declaration=False)

def save_svg_file(svg_content, filename):
    """Save SVG content to a file in the output directory"""
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    
    print(f"SVG saved to: {filepath}")
    return filepath

# === Main Pipeline ===

def generate_blog_svgs_overview(blog_text):
    start = time.monotonic()
    svgs = []
    saved_files = []

    # 1. Get full-post prompt
    print("Generating prompt...")
    try:
        prompt = extract_blog_prompt(blog_text)
        print(f"Prompt generated: \"{prompt}\"")
    except Exception as e:
        print(f"Failed to generate prompt: {e}")
        raise  # Stop if prompt fails

    # 2. Generate overview SVGs
    for idx in range(1, NUM_IMAGES + 1):
        print(f"\nGenerating Overview SVG #{idx}...")
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"  Attempt {attempt}/{MAX_RETRIES}...")
            if time.monotonic() - start > TIMEOUT_SECONDS:
                raise TimeoutError(f"Exceeded total time limit ({TIMEOUT_SECONDS}s)")

            try:
                svg_prompt = make_overview_svg_prompt(prompt, idx)
                # Get raw text response
                raw_response_text = call_gemini_api(svg_prompt)

                # Extract the SVG block
                raw_svg = extract_svg_block(raw_response_text)

                # Validate the extracted SVG
                ok, msg = validate_svg(raw_svg)
                if not ok:
                    print(f"  [Attempt {attempt}] Validation failed: {msg}")
                    if attempt == MAX_RETRIES:
                         raise RuntimeError(f"Failed to generate valid overview SVG #{idx} after {MAX_RETRIES} attempts. Last error: {msg}")
                    continue  # Try again

                print(f"  [Attempt {attempt}] SVG validated successfully.")
                branded = add_logo_to_svg(raw_svg)
                svgs.append(branded)
                
                # Save the SVG to a file
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"blog_svg_{idx}_{timestamp}.svg"
                saved_path = save_svg_file(branded, filename)
                saved_files.append(saved_path)
                
                print(f"  [Attempt {attempt}] Logo added and SVG saved.")
                break  # Success for this image index, move to the next
            
            except ValueError as e:  # Catch specific errors
                print(f"  [Attempt {attempt}] Error during generation/extraction: {e}")
                if attempt == MAX_RETRIES:
                    raise RuntimeError(f"Failed to generate valid overview SVG #{idx} after {MAX_RETRIES} attempts. Last error: {e}")
                continue

            except Exception as e:  # Catch unexpected errors
                 print(f"  [Attempt {attempt}] Unexpected error: {e}")
                 if attempt == MAX_RETRIES:
                    raise RuntimeError(f"Failed to generate overview SVG #{idx} due to unexpected error: {e}")
                 continue

    if len(svgs) != NUM_IMAGES:
         raise RuntimeError(f"Pipeline finished but only generated {len(svgs)}/{NUM_IMAGES} SVGs.")

    return svgs, saved_files

# === Input Processing Functions ===

def is_url(text):
    """Check if the input string is a URL."""
    try:
        result = urlparse(text.strip())
        return all([result.scheme, result.netloc]) and result.scheme in ['http', 'https']
    except:
        return False

def extract_content_from_html(html_content):
    """Extract the main article content from HTML with improved extraction techniques."""
    # Try using a more robust parser
    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except:
        soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove elements that definitely don't contain content
    for element in soup(['script', 'style', 'noscript', 'iframe', 'svg', 'form', 'header', 'footer', 'nav']):
        element.decompose()
    
    # More comprehensive list of article selectors, ordered by specificity
    article_selectors = [
        'article', 'main', 
        '.post-content', '.entry-content', '.post', '.article', '.blog-post',
        'div.article-body', '.content-area', '#primary', '#main',
        '.single-post', '.post-detail', '.post-body', '.blog-content',
        '.story-content', '.post-text', '.blog-post-content',
        '[itemprop="articleBody"]', '[itemprop="blogPost"]',
        '.story', '.blog-entry', '.blog',
        'section.content', 'div.content', '#content', '.main-content',
        '.page-content', '.entry'
    ]
    
    # First attempt: Try to find article containers
    for selector in article_selectors:
        elements = soup.select(selector)
        for element in elements:
            # Check that we have enough content and it's not just navigation/sidebar
            content = element.get_text(separator='\n\n', strip=True)
            # Longer minimum length for containers
            if len(content) > 300 and contains_paragraphs(element):
                print(f"Found content using selector: {selector}")
                return clean_extracted_content(content)
    
    # Second attempt: Look for clusters of paragraphs
    paragraphs = soup.find_all(['p'])
    if paragraphs and len(paragraphs) > 3:
        # Filter paragraphs with reasonable content
        meaningful_paragraphs = [p for p in paragraphs if len(p.get_text(strip=True)) > 40]
        
        if len(meaningful_paragraphs) >= 3:
            content = '\n\n'.join(p.get_text(strip=True) for p in meaningful_paragraphs)
            if len(content) > 150:
                print("Extracted content from paragraph clusters")
                return clean_extracted_content(content)
    
    # Third attempt: Extract all headers and following paragraphs
    content_sections = []
    headers = soup.find_all(['h1', 'h2', 'h3'])
    for header in headers:
        section_text = [header.get_text(strip=True)]
        next_elem = header.find_next_sibling()
        while next_elem and next_elem.name in ['p', 'ul', 'ol', 'blockquote']:
            section_text.append(next_elem.get_text(strip=True))
            next_elem = next_elem.find_next_sibling()
        if len(''.join(section_text)) > 100:
            content_sections.append('\n\n'.join(section_text))
    
    if content_sections:
        content = '\n\n'.join(content_sections)
        print("Extracted content by header sections")
        return clean_extracted_content(content)
    
    # Fourth attempt: Get all paragraphs and headers directly from body
    body = soup.body
    if body:
        elements = body.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'blockquote'])
        if elements:
            content = '\n\n'.join(el.get_text(strip=True) for el in elements if len(el.get_text(strip=True)) > 20)
            if len(content) > 200:
                print("Using direct body elements extraction")
                return clean_extracted_content(content)
    
    # Final attempt: use the full text, but try to clean it up
    full_text = soup.get_text(separator='\n\n')
    print("Fallback to full HTML text")
    return clean_extracted_content(full_text)

def contains_paragraphs(element):
    """Check if element contains actual paragraphs or just short links/buttons."""
    paragraphs = element.find_all('p')
    if not paragraphs:
        return False
    # Need at least a few reasonable paragraphs
    meaningful_paragraphs = [p for p in paragraphs if len(p.get_text(strip=True)) > 30]
    return len(meaningful_paragraphs) >= 2

def clean_extracted_content(text):
    """Clean up extracted content by removing excessive whitespace and duplicated lines."""
    # Fix excess whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    # Remove duplicate consecutive lines
    unique_lines = []
    for line in lines:
        if not unique_lines or line != unique_lines[-1]:
            unique_lines.append(line)
    
    cleaned_text = '\n\n'.join(unique_lines)
    print(f"Extracted {len(cleaned_text)} characters of content")
    return cleaned_text

def fetch_url_content(url):
    """Fetch content from a URL with improved error handling and content extraction"""
    print(f"Fetching content from URL: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        response = requests.get(url, headers=headers, timeout=15)  # Slightly longer timeout
        response.raise_for_status()
        
        print("Extracting article content...")
        content_type = response.headers.get('Content-Type', '').lower()
        
        # Only process HTML content
        if 'text/html' in content_type:
            extracted_content = extract_content_from_html(response.text)
            
            if not extracted_content or len(extracted_content.strip()) < 100:
                return False, "Could not extract meaningful content from URL"
            
            return True, extracted_content
        else:
            return False, f"URL does not contain HTML content (found {content_type})"
    
    except requests.exceptions.RequestException as e:
        return False, f"Error fetching URL: {str(e)}"
    except Exception as e:
        return False, f"Error processing URL content: {str(e)}"

# === Main Execution ===
if __name__ == "__main__":
    print("Welcome to Blog2SVG Generator!")
    print("Enter your blog content or a URL below.")
    print("(For multiline text, keep typing and press Enter twice on a blank line when done)")
    
    # Collect input from user (support multiline input)
    print("\nEnter text or URL:")
    lines = []
    
    while True:
        line = input()
        if not line and not lines:
            # If first line is empty, ask again
            print("Please enter some content or a URL:")
            continue
        elif not line and lines:
            # Empty line after content means we're done
            break
        lines.append(line)
    
    user_input = "\n".join(lines)
    blog_text = None
    
    # Process the input
    if is_url(user_input):
        print(f"Detected URL: {user_input}")
        success, result = fetch_url_content(user_input)
        
        if success:
            blog_text = result
            print(f"Successfully extracted content ({len(blog_text)} characters)")
        else:
            print(f"Error: {result}")
            sys.exit(1)
    else:
        # Treat as direct text input
        print("Processing provided text input...")
        blog_text = user_input
    
    # Ensure we have content to process
    if not blog_text or len(blog_text.strip()) < 50:
        print("Error: Not enough content to process. Please provide more text or a different URL.")
        sys.exit(1)
    
    # Process the blog text
    try:
        svgs, saved_files = generate_blog_svgs_overview(blog_text)
        print("\nGeneration complete! Generated SVGs:")
        for i, path in enumerate(saved_files):
            print(f"  {i+1}. {path}")
    except Exception as e:
        print(f"\nError during SVG generation: {e}")
        sys.exit(1)
