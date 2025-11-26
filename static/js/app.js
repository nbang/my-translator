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
// Config Management
function loadLocalConfig() {
    currentConfig.token = localStorage.getItem('gh_token') || '';
    currentConfig.owner = localStorage.getItem('gh_owner') || '';
    currentConfig.repo = localStorage.getItem('gh_repo') || '';

    document.getElementById('github-token').value = currentConfig.token;
    document.getElementById('github-owner').value = currentConfig.owner;
    document.getElementById('github-repo').value = currentConfig.repo;

    document.getElementById('config-url').value = localStorage.getItem('config_url') || '';
    document.getElementById('config-base-dir').value = localStorage.getItem('config_base_dir') || '';
}

function saveLocalConfig() {
    currentConfig.token = document.getElementById('github-token').value;
    currentConfig.owner = document.getElementById('github-owner').value;
    currentConfig.repo = document.getElementById('github-repo').value;

    localStorage.setItem('gh_token', currentConfig.token);
    localStorage.setItem('gh_owner', currentConfig.owner);
    localStorage.setItem('gh_repo', currentConfig.repo);

    localStorage.setItem('config_url', document.getElementById('config-url').value);
    localStorage.setItem('config_base_dir', document.getElementById('config-base-dir').value);
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

// 3. Trigger Scraper
async function triggerScraper() {
    if (!currentConfig.token || !currentConfig.repo) return showToast('Please configure GitHub settings first.');

    const htmlContent = document.getElementById('chapters-html-content').value;
    const sourceUrl = document.getElementById('config-url').value;
    const baseDir = document.getElementById('config-base-dir').value;

    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/actions/workflows/scraper.yml/dispatches`;
        const body = {
            ref: 'main',
            inputs: {
                html_content: htmlContent,
                book_source_url: sourceUrl,
                book_base_dir: baseDir
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
    const baseDir = document.getElementById('config-base-dir').value;

    try {
        const url = `${GITHUB_API_BASE}/repos/${currentConfig.owner}/${currentConfig.repo}/actions/workflows/translator.yml/dispatches`;
        const body = {
            ref: 'main',
            inputs: {
                batch_size: batchSize,
                force: force.toString(),
                book_base_dir: baseDir
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

    // Try to get baseDir from the config input, or default
    let baseDir = document.getElementById('config-base-dir').value || 'bjXRF';

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
