// GitHub API Base URL
const GITHUB_API_BASE = 'https://api.github.com';

// State
let currentConfig = {
    token: '',
    owner: '',
    repo: ''
};

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    loadLocalConfig();
    // Default tab
    openTab('config');
});

// Tab Navigation
function openTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    
    document.getElementById(tabId).classList.add('active');
    document.querySelector(`button[onclick="openTab('${tabId}')"]`).classList.add('active');
}

// Config Management
function loadLocalConfig() {
    currentConfig.token = localStorage.getItem('gh_token') || '';
    currentConfig.owner = localStorage.getItem('gh_owner') || '';
    currentConfig.repo = localStorage.getItem('gh_repo') || '';

    document.getElementById('github-token').value = currentConfig.token;
    document.getElementById('github-owner').value = currentConfig.owner;
    document.getElementById('github-repo').value = currentConfig.repo;
}

function saveLocalConfig() {
    currentConfig.token = document.getElementById('github-token').value;
    currentConfig.owner = document.getElementById('github-owner').value;
    currentConfig.repo = document.getElementById('github-repo').value;

    localStorage.setItem('gh_token', currentConfig.token);
    localStorage.setItem('gh_owner', currentConfig.owner);
    localStorage.setItem('gh_repo', currentConfig.repo);
}

function getHeaders() {
    return {
        'Authorization': `token ${currentConfig.token}`,
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
    };
}

// Helper: Show Toast
function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// --- GitHub API Interactions ---

// 1. Load .env
async function loadEnvFromRepo() {
    if (!currentConfig.token || !currentConfig.repo) return showToast('Please configure GitHub settings first.');
    
    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/contents/.env`;
        const response = await fetch(url, { headers: getHeaders() });
        
        if (!response.ok) throw new Error('Failed to fetch .env');
        
        const data = await response.json();
        const content = atob(data.content); // Decode Base64
        document.getElementById('env-content').value = content;
        // Store sha for updates
        document.getElementById('env-content').dataset.sha = data.sha;
        
        showToast('.env loaded successfully');
    } catch (error) {
        console.error(error);
        showToast('Error loading .env: ' + error.message);
    }
}

// 2. Save .env
async function saveEnvToRepo() {
    if (!currentConfig.token || !currentConfig.repo) return showToast('Please configure GitHub settings first.');
    
    const content = document.getElementById('env-content').value;
    const sha = document.getElementById('env-content').dataset.sha;
    
    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/contents/.env`;
        const body = {
            message: 'Update .env via Dashboard',
            content: btoa(content),
            sha: sha // Required for updates
        };
        
        const response = await fetch(url, {
            method: 'PUT',
            headers: getHeaders(),
            body: JSON.stringify(body)
        });
        
        if (!response.ok) throw new Error('Failed to save .env');
        
        const data = await response.json();
        document.getElementById('env-content').dataset.sha = data.content.sha;
        showToast('.env saved successfully');
    } catch (error) {
        console.error(error);
        showToast('Error saving .env: ' + error.message);
    }
}

// 3. Trigger Scraper
async function triggerScraper() {
    if (!currentConfig.token || !currentConfig.repo) return showToast('Please configure GitHub settings first.');
    
    const htmlContent = document.getElementById('chapters-html-content').value;
    
    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/actions/workflows/scraper.yml/dispatches`;
        const body = {
            ref: 'main', // Or master, make configurable if needed
            inputs: {
                html_content: htmlContent
            }
        };
        
        const response = await fetch(url, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify(body)
        });
        
        if (!response.ok) throw new Error('Failed to trigger scraper');
        
        showToast('Scraper workflow triggered!');
        checkWorkflowStatus();
    } catch (error) {
        console.error(error);
        showToast('Error triggering scraper: ' + error.message);
    }
}

// 4. Trigger Translator
async function triggerTranslator() {
    if (!currentConfig.token || !currentConfig.repo) return showToast('Please configure GitHub settings first.');
    
    const batchSize = document.getElementById('batch-size').value;
    const force = document.getElementById('force-translate').checked;
    
    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/actions/workflows/translator.yml/dispatches`;
        const body = {
            ref: 'main',
            inputs: {
                batch_size: batchSize,
                force: force.toString()
            }
        };
        
        const response = await fetch(url, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify(body)
        });
        
        if (!response.ok) throw new Error('Failed to trigger translator');
        
        showToast('Translator workflow triggered!');
        checkWorkflowStatus();
    } catch (error) {
        console.error(error);
        showToast('Error triggering translator: ' + error.message);
    }
}

// 5. Check Status
async function checkWorkflowStatus() {
    if (!currentConfig.token || !currentConfig.repo) return;
    
    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/actions/runs?per_page=5`;
        const response = await fetch(url, { headers: getHeaders() });
        const data = await response.json();
        
        const list = document.getElementById('workflow-status-list');
        list.innerHTML = '';
        
        data.workflow_runs.forEach(run => {
            const div = document.createElement('div');
            div.className = 'status-item';
            div.innerHTML = `
                <span>${run.name} #${run.run_number}</span>
                <span class="status-${run.conclusion || 'pending'}">${run.status}: ${run.conclusion || 'running'}</span>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error(error);
    }
}

// 6. File Browser
async function loadFileList() {
    if (!currentConfig.token || !currentConfig.repo) return showToast('Please configure GitHub settings first.');
    
    const folder = document.getElementById('folder-select').value;
    // We need to find the actual path. The user config might have a different base dir.
    // But for browsing, we can assume the structure relative to repo root.
    // Let's try to list the folder directly.
    // Note: If BOOK_BASE_DIR is variable, we might need to guess or ask user.
    // For now, let's assume standard structure: bjXRF/raw_chinese or similar.
    // Actually, the user might want to browse the whole repo?
    // Let's try to list 'bjXRF/' + folder first, or just search?
    // To keep it simple, let's list the root and find the folder?
    // Or just ask user to input path?
    // Let's try a recursive search or just hardcode 'bjXRF' for now based on previous context, 
    // BUT better: list root, if 'bjXRF' exists, go in there.
    
    // Simplified: Just list the folder provided in the dropdown, assuming it's at root or we know the prefix.
    // The previous context showed 'bjXRF' and 'biqu59096'.
    // Let's try to fetch the folder content directly. If 404, maybe prompt user or try to find it.
    
    // Let's try to read the .env first to get BOOK_BASE_DIR?
    // We already loaded .env content into the textarea. We can parse it.
    let baseDir = 'bjXRF'; // Default
    const envContent = document.getElementById('env-content').value;
    if (envContent) {
        const match = envContent.match(/BOOK_BASE_DIR=(.*)/);
        if (match) baseDir = match[1].trim();
    }
    
    const path = `${baseDir}/${folder}`;
    
    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/contents/${path}`;
        const response = await fetch(url, { headers: getHeaders() });
        
        if (!response.ok) throw new Error('Folder not found');
        
        const files = await response.json();
        const list = document.getElementById('file-list');
        list.innerHTML = '';
        
        files.forEach(file => {
            if (file.type === 'file') {
                const li = document.createElement('li');
                li.textContent = file.name;
                li.onclick = () => loadFileContent(file.path);
                list.appendChild(li);
            }
        });
    } catch (error) {
        console.error(error);
        showToast('Error loading files: ' + error.message);
    }
}

async function loadFileContent(path) {
    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/contents/${path}`;
        const response = await fetch(url, { headers: getHeaders() });
        const data = await response.json();
        
        // Decode content (UTF-8 safe decode)
        const content = decodeURIComponent(escape(atob(data.content)));
        document.getElementById('file-content-display').textContent = content;
    } catch (error) {
        console.error(error);
        showToast('Error loading file content');
    }
}
