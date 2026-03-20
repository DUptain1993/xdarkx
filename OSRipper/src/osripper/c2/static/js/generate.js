// Payload Generation JavaScript

document.getElementById('payload-type').addEventListener('change', function() {
    const payloadType = this.value;
    
    // Hide all options and remove required attributes
    document.querySelectorAll('.payload-option').forEach(el => {
        el.style.display = 'none';
        // Remove required from all inputs in hidden sections
        el.querySelectorAll('input').forEach(input => {
            if (input.name === 'domain' || input.name === 'base_url') {
                input.removeAttribute('required');
            }
        });
    });
    
    // Show relevant options and add required attributes
    if (payloadType) {
        const optionDiv = document.getElementById(payloadType + '-options');
        if (optionDiv) {
            optionDiv.style.display = 'block';
            // Add required to inputs in visible section
            optionDiv.querySelectorAll('input').forEach(input => {
                // Only add required if it's a field that should be required
                if (input.name === 'domain' || input.name === 'base_url') {
                    input.setAttribute('required', 'required');
                }
            });
        }
        
        // Auto-fill certificate fingerprint for HTTPS payloads
        if (payloadType === 'https') {
            fetchCertFingerprint();
        }
    }
});

// Fetch certificate fingerprint from server
function fetchCertFingerprint() {
    const fingerprintInput = document.getElementById('cert-fingerprint-input');
    const statusDiv = document.getElementById('fingerprint-status');
    const statusText = document.getElementById('fingerprint-status-text');
    
    if (!fingerprintInput) return;
    
    fetch('/api/cert-fingerprint')
        .then(response => response.json())
        .then(data => {
            if (data.fingerprint) {
                fingerprintInput.value = data.fingerprint;
                statusDiv.style.display = 'block';
                statusText.textContent = '✓ Fingerprint auto-filled from server certificate';
                statusText.className = 'text-success';
            }
        })
        .catch(error => {
            // Server might not have HTTPS enabled, that's okay
            statusDiv.style.display = 'block';
            statusText.textContent = 'ℹ Server does not have HTTPS enabled. Enter fingerprint manually or leave empty.';
            statusText.className = 'text-info';
        });
}

// Also fetch fingerprint when base_url changes (for external servers)
document.addEventListener('DOMContentLoaded', function() {
    const baseUrlInput = document.getElementById('base-url-input');
    if (baseUrlInput) {
        let fetchTimeout;
        baseUrlInput.addEventListener('input', function() {
            const url = this.value.trim();
            const fingerprintInput = document.getElementById('cert-fingerprint-input');
            const statusDiv = document.getElementById('fingerprint-status');
            const statusText = document.getElementById('fingerprint-status-text');
            
            // Clear existing timeout
            if (fetchTimeout) {
                clearTimeout(fetchTimeout);
            }
            
            // Hide status while typing
            if (statusDiv) {
                statusDiv.style.display = 'none';
            }
            
            // Wait for user to finish typing
            fetchTimeout = setTimeout(() => {
                if (url && url.startsWith('https://') && fingerprintInput && !fingerprintInput.value) {
                    if (statusDiv) {
                        statusDiv.style.display = 'block';
                        statusText.textContent = 'Fetching certificate fingerprint...';
                        statusText.className = 'text-info';
                    }
                    
                    fetch('/api/cert-fingerprint-from-url', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ url: url })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.fingerprint) {
                            fingerprintInput.value = data.fingerprint;
                            if (statusDiv) {
                                statusText.textContent = '✓ Fingerprint auto-filled from server';
                                statusText.className = 'text-success';
                            }
                        } else {
                            if (statusDiv) {
                                statusText.textContent = '⚠ Could not fetch fingerprint. Enter manually or leave empty.';
                                statusText.className = 'text-warning';
                            }
                        }
                    })
                    .catch(error => {
                        // Failed to get fingerprint, that's okay
                        if (statusDiv) {
                            statusText.textContent = '⚠ Could not fetch fingerprint. Enter manually or leave empty.';
                            statusText.className = 'text-warning';
                        }
                    });
                }
            }, 1500); // Wait 1.5 seconds after user stops typing
        });
    }
});

// Show/hide enhanced option based on obfuscate checkbox
document.getElementById('obfuscate').addEventListener('change', function() {
    const enhancedGroup = document.getElementById('enhanced-group');
    if (this.checked) {
        enhancedGroup.style.display = 'block';
    } else {
        enhancedGroup.style.display = 'none';
        document.getElementById('enhanced').checked = false;
    }
});

// Show/hide icon option based on compile checkbox
document.getElementById('compile').addEventListener('change', function() {
    const iconGroup = document.getElementById('icon-group');
    if (this.checked) {
        iconGroup.style.display = 'block';
    } else {
        iconGroup.style.display = 'none';
    }
});


// Form submission
document.getElementById('payload-form').addEventListener('submit', function(e) {
    e.preventDefault();
    
    // Hide previous results
    document.getElementById('results').style.display = 'none';
    document.getElementById('error').style.display = 'none';
    
    // Collect form data
    const formData = new FormData(this);
    const payloadData = {};
    
    for (let [key, value] of formData.entries()) {
        if (key === 'delay' || key === 'obfuscate' || key === 'enhanced' || key === 'compile' || key === 'testing') {
            payloadData[key] = true;
        } else if (value) {
            payloadData[key] = value;
        }
    }
    
    // Show loading
    const submitBtn = this.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Generating...';
    
    // Send request
    fetch('/api/generate-payload', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payloadData)
    })
    .then(response => response.json())
    .then(data => {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
        
        if (data.success) {
            // Show success
            const resultDetails = document.getElementById('result-details');
            let html = '<p><strong>Payload Type:</strong> ' + data.payload_type.toUpperCase() + '</p>';
            html += '<p><strong>Output File:</strong> <code>' + data.output_file + '</code></p>';
            
            if (data.output_path) {
                html += '<p><strong>Location:</strong> <code>' + data.output_path + '</code></p>';
            }
            
            if (data.binary_file) {
                html += '<p><strong>Binary File:</strong> <code>' + data.binary_file + '</code></p>';
                if (data.binary_path) {
                    html += '<p><strong>Binary Location:</strong> <code>' + data.binary_path + '</code></p>';
                }
            }
            
            if (data.message) {
                html += '<p><strong>Note:</strong> ' + data.message + '</p>';
            }
            
            resultDetails.innerHTML = html;
            
            // Add download buttons
            const downloadButtons = document.getElementById('download-buttons');
            let downloadHtml = '<h6>Download:</h6>';
            
            if (data.download_url) {
                downloadHtml += '<a href="' + data.download_url + '" class="btn btn-primary me-2 mb-2" download>Download ' + data.output_file + '</a>';
            }
            
            if (data.binary_download_url) {
                downloadHtml += '<a href="' + data.binary_download_url + '" class="btn btn-success me-2 mb-2" download>Download Binary</a>';
            }
            
            downloadButtons.innerHTML = downloadHtml;
            
            document.getElementById('results').style.display = 'block';
        } else {
            // Show error
            document.getElementById('error-details').textContent = data.error || 'Unknown error occurred';
            document.getElementById('error').style.display = 'block';
        }
    })
    .catch(error => {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
        document.getElementById('error-details').textContent = 'Error: ' + error.message;
        document.getElementById('error').style.display = 'block';
    });
});

