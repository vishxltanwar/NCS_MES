/**
 * Shared API and Utility functions for Napino MES
 */

const API = {
    async fetchStats() {
        try {
            const res = await fetch('/api/stats');
            return await res.json();
        } catch (err) {
            console.error('Error fetching stats:', err);
            return null;
        }
    },

    async fetchSerials() {
        try {
            const res = await fetch('/api/serials');
            return await res.json();
        } catch (err) {
            console.error('Error fetching serials:', err);
            return [];
        }
    },

    async deleteSerial(id) {
        if (!confirm("Are you sure you want to delete this serial record?")) return false;
        try {
            const res = await fetch(`/api/serials/${id}`, { method: 'DELETE' });
            return res.ok;
        } catch (err) {
            console.error('Error deleting serial:', err);
            return false;
        }
    },

    async markDone(serial) {
        try {
            const res = await fetch('/api/mark-done', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ serial: serial })
            });
            return await res.json();
        } catch (err) {
            console.error('Error marking done:', err);
            return { success: false };
        }
    },

    // ── Balancing APIs ──────────────────────────────────────────────────────────

    async fetchBalancingRecords(type) {
        try {
            const res = await fetch(`/api/${type}-balancing/`);
            return await res.json();
        } catch (err) {
            console.error(`Error fetching ${type} balancing records:`, err);
            return [];
        }
    },

    async deleteBalancingRecord(type, id) {
        if (!confirm("Are you sure you want to delete this record?")) return false;
        try {
            const res = await fetch(`/api/${type}-balancing/${id}/`, { method: 'DELETE' });
            return res.ok;
        } catch (err) {
            console.error(`Error deleting ${type} balancing record:`, err);
            return false;
        }
    },

    async importBalancingFile(type, file, btnId) {
        const formData = new FormData();
        formData.append('file', file);
        UI.setLoading(btnId, true);
        try {
            const res = await fetch(`/api/${type}-balancing/import/`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            return { ok: res.ok, data };
        } catch (err) {
            console.error(`Error importing ${type} balancing file:`, err);
            return { ok: false, data: { detail: 'Connection failed' } };
        } finally {
            UI.setLoading(btnId, false);
        }
    }
};

/**
 * Common UI helpers
 */
const UI = {
    setLoading(btnId, isLoading, originalHtml) {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        if (isLoading) {
            btn.disabled = true;
            btn.dataset.originalHtml = btn.innerHTML;
            btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-lg">progress_activity</span> Processing...';
        } else {
            btn.disabled = false;
            btn.innerHTML = originalHtml || btn.dataset.originalHtml || 'Submit';
        }
    }
};
