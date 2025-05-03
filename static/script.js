document.addEventListener('DOMContentLoaded', function() {
    // Tab switching
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all buttons and contents
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Add active class to clicked button and corresponding content
            button.classList.add('active');
            const tabId = button.getAttribute('data-tab');
            document.getElementById(`${tabId}-content`).classList.add('active');
        });
    });
    
    // Handle URL form submission
    document.getElementById('url-form').addEventListener('submit', function(e) {
        e.preventDefault();
        const url = document.getElementById('blog-url').value;
        processContent('url', url);
    });
    
    // Handle HTML form submission
    document.getElementById('html-form').addEventListener('submit', function(e) {
        e.preventDefault();
        const html = document.getElementById('blog-html').value;
        processContent('html', html);
    });

    // Function to process content and make API call
    function processContent(inputType, content) {
        // Show loading indicator
        document.getElementById('loading').style.display = 'flex';
        
        // Hide any previous results
        document.getElementById('result-section').style.display = 'none';
        
        // Create request data
        const requestData = {
            inputType: inputType,
            content: content
        };
        
        // Make API call
        fetch('/api/convert', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || 'Failed to convert content');
                });
            }
            return response.json();
        })
        .then(data => {
            // Process successful response
            displayResults(data);
        })
        .catch(error => {
            // Show error
            showError(error.message);
        })
        .finally(() => {
            // Hide loading indicator
            document.getElementById('loading').style.display = 'none';
        });
    }

    // Function to display SVG results
    function displayResults(data) {
        const resultSection = document.getElementById('result-section');
        const gallery = document.getElementById('svg-gallery');
        
        // Clear previous results
        gallery.innerHTML = '';
        
        // Add each SVG to the gallery
        data.svgs.forEach((svg, index) => {
            const card = document.createElement('div');
            card.className = 'svg-card';
            
            const preview = document.createElement('div');
            preview.className = 'svg-preview';
            preview.innerHTML = svg;
            
            const actions = document.createElement('div');
            actions.className = 'svg-actions';
            
            // Create download button that generates file on-the-fly
            const downloadBtn = document.createElement('a');
            downloadBtn.className = 'btn';
            downloadBtn.textContent = 'Download';
            downloadBtn.href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
            downloadBtn.download = `blog-svg-${index+1}.svg`;
            
            const viewBtn = document.createElement('button');
            viewBtn.className = 'btn';
            viewBtn.textContent = 'View Full Size';
            viewBtn.onclick = function() {
                showFullSizeModal(svg, `SVG ${index+1}`);
            };
            
            actions.appendChild(downloadBtn);
            actions.appendChild(viewBtn);
            
            card.appendChild(preview);
            card.appendChild(actions);
            
            gallery.appendChild(card);
        });
        
        // Show result section
        resultSection.style.display = 'block';
        
        // Scroll to results
        resultSection.scrollIntoView({ behavior: 'smooth' });
    }
    
    // Function to show errors
    function showError(message) {
        // Create alert element
        const alert = document.createElement('div');
        alert.className = 'alert error';
        alert.innerHTML = `<p><strong>Error:</strong> ${message}</p>`;
        
        // Add to page
        const resultSection = document.getElementById('result-section');
        resultSection.innerHTML = '';
        resultSection.appendChild(alert);
        resultSection.style.display = 'block';
        
        // Scroll to error
        resultSection.scrollIntoView({ behavior: 'smooth' });
    }
    
    // Create a modal for full-size view
    function showFullSizeModal(svgContent, title) {
        // Create modal elements
        const modal = document.createElement('div');
        modal.className = 'modal';
        
        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';
        
        const closeBtn = document.createElement('span');
        closeBtn.className = 'close-btn';
        closeBtn.innerHTML = '&times;';
        closeBtn.onclick = function() {
            document.body.removeChild(modal);
        };
        
        const modalHeader = document.createElement('div');
        modalHeader.className = 'modal-header';
        modalHeader.innerHTML = `<h2>${title}</h2>`;
        
        const modalBody = document.createElement('div');
        modalBody.className = 'modal-body';
        modalBody.innerHTML = svgContent;
        
        // Assemble modal
        modalHeader.appendChild(closeBtn);
        modalContent.appendChild(modalHeader);
        modalContent.appendChild(modalBody);
        modal.appendChild(modalContent);
        
        // Add to page
        document.body.appendChild(modal);
        
        // Close when clicking outside
        window.onclick = function(event) {
            if (event.target === modal) {
                document.body.removeChild(modal);
            }
        };
    }
});