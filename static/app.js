document.addEventListener('DOMContentLoaded', () => {
    // Navigation elements
    const tabChat = document.getElementById('tab-chat');
    const tabUpload = document.getElementById('tab-upload');
    const panelChat = document.getElementById('panel-chat');
    const panelUpload = document.getElementById('panel-upload');

    // Chat elements
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');

    // Upload elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const uploadStatus = document.getElementById('upload-status');
    const progressBar = document.getElementById('progress-bar');
    const statusText = document.getElementById('status-text');

    // Sidebar document elements
    const documentList = document.getElementById('document-list');

    // ----------------------------------------------------
    // Tab Navigation Logic
    // ----------------------------------------------------
    tabChat.addEventListener('click', () => {
        tabChat.classList.add('active');
        tabChat.setAttribute('aria-selected', 'true');
        tabUpload.classList.remove('active');
        tabUpload.setAttribute('aria-selected', 'false');

        panelChat.style.display = 'flex';
        panelUpload.style.display = 'none';
    });

    tabUpload.addEventListener('click', () => {
        tabUpload.classList.add('active');
        tabUpload.setAttribute('aria-selected', 'true');
        tabChat.classList.remove('active');
        tabChat.setAttribute('aria-selected', 'false');

        panelUpload.style.display = 'flex';
        panelChat.style.display = 'none';
    });

    // ----------------------------------------------------
    // Document List Logic
    // ----------------------------------------------------
    async function loadDocuments() {
        try {
            const res = await fetch('/api/documents');
            if (!res.ok) throw new Error('Failed to fetch documents');
            const docs = await res.json();
            
            if (docs.length === 0) {
                documentList.innerHTML = '<li class="loading-docs">No documents indexed yet.</li>';
                return;
            }

            documentList.innerHTML = '';
            docs.forEach(doc => {
                const li = document.createElement('li');
                li.innerHTML = `
                    <div class="doc-name" title="${doc.filename}">${doc.filename}</div>
                    <div class="doc-date">Uploaded: ${doc.uploaded_at}</div>
                `;
                documentList.appendChild(li);
            });
        } catch (err) {
            console.error(err);
            documentList.innerHTML = '<li class="loading-docs" style="color: #ff5252;">Error loading documents</li>';
        }
    }

    // Initial load
    loadDocuments();

    // ----------------------------------------------------
    // Chat Logic
    // ----------------------------------------------------
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query) return;

        // Clear input
        chatInput.value = '';

        // Append user message
        appendMessage('user', query);

        // Append assistant loading message
        const loadingId = appendMessage('assistant', 'Thinking...', true);

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || 'Failed to generate answer');
            }

            const data = await res.json();
            
            // Remove loading state and update with result
            removeLoadingMessage(loadingId, data.result, data.source_documents);
        } catch (err) {
            console.error(err);
            updateMessageContent(loadingId, `Error: ${err.message}`, true);
        }
    });

    function appendMessage(sender, text, isLoading = false) {
        const id = 'msg-' + Math.random().toString(36).substr(2, 9);
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        messageDiv.id = id;

        if (isLoading) {
            messageDiv.classList.add('loading');
        }

        messageDiv.innerHTML = `
            <div class="message-bubble">${text}</div>
        `;

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return id;
    }

    function updateMessageContent(id, text, isError = false) {
        const messageDiv = document.getElementById(id);
        if (messageDiv) {
            const bubble = messageDiv.querySelector('.message-bubble');
            if (bubble) {
                bubble.textContent = text;
                if (isError) bubble.style.color = '#ff5252';
            }
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    function removeLoadingMessage(id, text, citations) {
        const messageDiv = document.getElementById(id);
        if (messageDiv) {
            messageDiv.classList.remove('loading');
            const bubble = messageDiv.querySelector('.message-bubble');
            if (bubble) {
                // Configure marked options
                marked.setOptions({
                    breaks: true,
                    gfm: true
                });
                bubble.innerHTML = marked.parse(text);
            }

            // Append citations if available
            if (citations && citations.length > 0) {
                const citationsDiv = document.createElement('div');
                citationsDiv.classList.add('message-citations');
                
                // Group by page number to avoid redundant badges
                const uniqueCitations = [];
                const seen = new Set();
                citations.forEach(c => {
                    const key = `${c.filename}-page-${c.page_number}`;
                    if (!seen.has(key)) {
                        seen.add(key);
                        uniqueCitations.push(c);
                    }
                });

                uniqueCitations.forEach(cit => {
                    const badge = document.createElement('span');
                    badge.classList.add('citation-badge');
                    badge.textContent = `${cit.filename} (Pg ${cit.page_number})`;
                    badge.title = cit.content_preview;
                    citationsDiv.appendChild(badge);
                });
                messageDiv.appendChild(citationsDiv);
            }

            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    // ----------------------------------------------------
    // Upload Logic
    // ----------------------------------------------------
    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'));
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type === 'application/pdf') {
            uploadFile(files[0]);
        } else {
            alert('Please drop a valid PDF file.');
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            uploadFile(fileInput.files[0]);
        }
    });

    function uploadFile(file) {
        uploadStatus.style.display = 'block';
        progressBar.style.width = '0%';
        statusText.textContent = `Uploading and processing '${file.name}'...`;
        statusText.style.color = 'var(--text-secondary)';

        const formData = new FormData();
        formData.append('file', file);

        // Simple progress simulation for UX
        let progress = 0;
        const interval = setInterval(() => {
            if (progress < 90) {
                progress += 10;
                progressBar.style.width = `${progress}%`;
            }
        }, 1500);

        fetch('/api/upload', {
            method: 'POST',
            body: formData
        })
        .then(async res => {
            clearInterval(interval);
            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || 'Failed to process file');
            }
            return res.json();
        })
        .then(data => {
            progressBar.style.width = '100%';
            statusText.textContent = `Successfully indexed '${file.name}'!`;
            statusText.style.color = 'var(--success)';
            
            // Reload documents in sidebar
            loadDocuments();
            
            // Auto switch to Chat tab after 1.5 seconds
            setTimeout(() => {
                uploadStatus.style.display = 'none';
                progressBar.style.width = '0%';
                tabChat.click();
            }, 1500);
        })
        .catch(err => {
            clearInterval(interval);
            progressBar.style.width = '0%';
            statusText.textContent = `Error: ${err.message}`;
            statusText.style.color = '#ff5252';
        });
    }
});
