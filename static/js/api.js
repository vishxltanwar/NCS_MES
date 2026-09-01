/**
 * Shared API and Utility functions for Napino MES
 */

const API = {
    async fetchStats() {
        try {
            const res = await fetch('/api/stats');
            await requireOk(res, 'Unable to load production statistics');
            return await res.json();
        } catch (err) {
            console.error('Error fetching stats:', err);
            return null;
        }
    },

    async fetchSerials() {
        try {
            const res = await fetch('/api/serials');
            await requireOk(res, 'Unable to load serial records');
            return await res.json();
        } catch (err) {
            console.error('Error fetching serials:', err);
            return [];
        }
    },

    async markDone(serial) {
        try {
            const res = await fetch('/api/mark-done', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ serial: serial })
            });
            await requireOk(res, 'Unable to update serial status');
            return await res.json();
        } catch (err) {
            console.error('Error marking done:', err);
            return { success: false };
        }
    },

    // ── Balancing APIs ──────────────────────────────────────────────────────────

    async fetchBalancingRecords(type) {
        try {
            const endpoint = type === 'stator' ? 'stator-testing' : `${type}-balancing`;
            const res = await fetch(`/api/${endpoint}/`);
            await requireOk(res, `Unable to load ${type} records`);
            const data = await res.json();
            return Array.isArray(data) ? data : data.results;
        } catch (err) {
            console.error(`Error fetching ${type} records:`, err);
            return [];
        }
    },

    async importBalancingFile(type, file, btnId) {
        const formData = new FormData();
        formData.append('file', file);
        UI.setLoading(btnId, true);
        try {
            const endpoint = type === 'stator' ? 'stator-testing' : `${type}-balancing`;
            const res = await fetch(`/api/${endpoint}/import/`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            return { ok: res.ok, data };
        } catch (err) {
            console.error(`Error importing ${type} file:`, err);
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
