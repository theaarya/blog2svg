from flask import Flask, render_template, request, jsonify
import os
import time
import traceback
import requests
from bs4 import BeautifulSoup
import sys

# Import functions from svg.py
from svg import (
    is_url, 
    extract_content_from_html, 
    generate_blog_svgs_overview,
    # We won't use save_svg_file or OUTPUT_DIR
)

app = Flask(__name__)

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/convert', methods=['POST'])
def convert():
    """API endpoint to handle conversion requests"""
    try:
        data = request.json
        input_type = data.get('inputType')
        content = data.get('content')
        
        # Validate input
        if not input_type or not content:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        # Process based on input type
        if input_type == 'url':
            # Validate URL
            if not is_url(content):
                return jsonify({'success': False, 'error': 'Invalid URL format'}), 400
            
            # Fetch URL content
            try:
                response = requests.get(content, timeout=10)
                response.raise_for_status()
                html_content = response.text
                blog_text = extract_content_from_html(html_content)
            except requests.RequestException as e:
                return jsonify({'success': False, 'error': f'Failed to fetch URL: {str(e)}'}), 400
        
        elif input_type == 'html':
            # Process HTML directly
            blog_text = extract_content_from_html(content)
        
        else:
            return jsonify({'success': False, 'error': 'Invalid input type'}), 400
        
        # Check if we have content to process
        if not blog_text or len(blog_text.strip()) < 50:
            return jsonify({'success': False, 'error': 'Could not extract enough content from the input'}), 400
        
        # Generate SVGs without saving files
        svgs, _ = generate_blog_svgs_overview(blog_text, save_files=False)
        
        # Prepare response with just the SVGs
        result = {
            'success': True,
            'svgs': svgs
        }
        
        return jsonify(result)
    
    except Exception as e:
        print(f"Error processing request: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Run the app
    app.run(debug=True, port=5000)