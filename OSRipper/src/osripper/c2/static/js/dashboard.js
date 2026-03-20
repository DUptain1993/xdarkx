// Dashboard JavaScript
function formatLastSeen(lastSeenStr) {
    if (!lastSeenStr) return 'Never';
    try {
        const lastSeen = new Date(lastSeenStr);
        const now = new Date();
        const diffMs = now - lastSeen;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        
        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return lastSeen.toLocaleDateString();
    } catch (e) {
        return lastSeenStr;
    }
}

function getStatusBadge(lastSeenStr) {
    if (!lastSeenStr) return '<span class="badge bg-secondary">Unknown</span>';
    try {
        const lastSeen = new Date(lastSeenStr);
        const now = new Date();
        const diffMs = now - lastSeen;
        const diffMins = Math.floor(diffMs / 60000);
        
        if (diffMins < 5) {
            return '<span class="badge bg-success">Active</span>';
        } else if (diffMins < 60) {
            return '<span class="badge bg-warning">Recent</span>';
        } else {
            return '<span class="badge bg-secondary">Inactive</span>';
        }
    } catch (e) {
        return '<span class="badge bg-secondary">Unknown</span>';
    }
}

function deleteSession(sessionId) {
    if (!confirm('Are you sure you want to delete this session? The agent will terminate on its next check-in.')) {
        return;
    }
    
    fetch(`/api/session/${sessionId}`, {
        method: 'DELETE'
    })
    .then(response => {
        if (response.ok) {
            refreshSessions();
        } else {
            alert('Failed to delete session');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error deleting session');
    });
}

function refreshSessions() {
    fetch('/api/sessions')
        .then(response => response.json())
        .then(data => {
            const tbody = document.getElementById('sessions-table');
            const emptyState = document.querySelector('.empty-state-container');
            
            if (!tbody) return;
            
            // Update count badge if it exists
            const countBadge = document.querySelector('.session-count-badge .badge');
            if (countBadge) {
                countBadge.textContent = `${data.length} Active`;
            }
            
            if (data.length === 0) {
                // Show empty state if it exists
                if (emptyState) {
                    emptyState.style.display = 'block';
                }
                tbody.innerHTML = '';
                return;
            }
            
            // Hide empty state
            if (emptyState) {
                emptyState.style.display = 'none';
            }
            
            tbody.innerHTML = '';
            
            data.forEach(session => {
                const row = tbody.insertRow();
                row.innerHTML = `
                    <td><code class="session-id-small">${session.session_id.substring(0, 16)}...</code></td>
                    <td>${session.hostname || 'N/A'}</td>
                    <td>${session.username || 'N/A'}</td>
                    <td class="small-text">${session.platform || 'N/A'}</td>
                    <td>${formatLastSeen(session.last_seen)}</td>
                    <td>${getStatusBadge(session.last_seen)}</td>
                    <td>
                        <a href="/session/${session.session_id}" class="btn btn-sm btn-primary me-1">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="me-1" style="display: inline-block; vertical-align: middle;">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                                <circle cx="12" cy="12" r="3"></circle>
                            </svg>
                            View
                        </a>
                        <button onclick="deleteSession('${session.session_id}')" class="btn btn-sm btn-danger">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="me-1" style="display: inline-block; vertical-align: middle;">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                            Delete
                        </button>
                    </td>
                `;
            });
        })
        .catch(error => console.error('Error:', error));
}

// Auto-refresh every 5 seconds
setInterval(refreshSessions, 5000);

// Initial load
document.addEventListener('DOMContentLoaded', refreshSessions);

