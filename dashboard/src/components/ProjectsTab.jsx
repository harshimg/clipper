import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, FolderOpen, Trash2, Square, Film, RefreshCw } from 'lucide-react';
import { apiFetch, apiJson } from '../lib/api';

// Self-host project manager: every job on this server's disk (output/), with
// open, cancel and delete. The Cloud edition has the History tab instead.
const STATUS_BADGE = {
  completed: ['badge-ok', 'done'],
  processing: ['badge-brass', 'processing'],
  queued: ['badge-warn', 'queued'],
  cancelled: ['badge-danger', 'cancelled'],
  failed: ['badge-danger', 'failed'],
};

const fmtSize = (bytes) => {
  if (!bytes) return '0 MB';
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${Math.max(0.1, bytes / 1e6).toFixed(1)} MB`;
};

const fmtDate = (epoch) => (epoch
  ? new Date(epoch * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  : '');

export default function ProjectsTab({ currentJobId, onOpenProject, onProjectGone }) {
  const [projects, setProjects] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);          // job_id with a request in flight
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try {
      const d = await apiJson('/api/local/projects');
      setProjects(d.projects || []);
      setError('');
    } catch {
      setError('Could not load your projects.');
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const cancel = async (jobId) => {
    setBusy(jobId);
    try {
      const res = await apiFetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      if (!res.ok) throw new Error();
      setNotice('Job cancelled.');
    } catch {
      setNotice('Could not cancel that job.');
    }
    setBusy(null);
    load();
  };

  const remove = async (jobId) => {
    setBusy(jobId);
    setConfirmDelete(null);
    try {
      const res = await apiFetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error();
      const d = await res.json();
      setNotice(`Deleted. ${fmtSize(d.freed_bytes)} freed.`);
      if (jobId === currentJobId && onProjectGone) onProjectGone();
    } catch {
      setNotice('Could not delete that job.');
    }
    setBusy(null);
    load();
  };

  const totalSize = (projects || []).reduce((s, p) => s + (p.size_bytes || 0), 0);

  if (projects === null && !error) {
    return <div className="flex justify-center py-20"><Loader2 className="animate-spin text-brass" /></div>;
  }

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-8 max-w-5xl mx-auto animate-fade">
      <p className="eyebrow mb-1.5">07 · PROJECTS</p>
      <div className="flex flex-wrap items-end justify-between gap-3 mb-2">
        <h1 className="font-display lowercase text-2xl text-ink">Your projects</h1>
        <button onClick={load} className="btn-quiet px-3 py-2 text-xs" title="Refresh">
          <RefreshCw size={14} /> refresh
        </button>
      </div>
      <p className="text-muted text-sm mb-6 lowercase">
        Every video on this computer: open one to see its clips, cancel one that is still running, or delete it to free disk space.
        {projects && projects.length > 0 && <> Using {fmtSize(totalSize)} in total.</>}
      </p>

      {error && <p className="text-danger text-sm mb-4">{error}</p>}
      {notice && <p className="text-sm text-brass mb-4">{notice}</p>}

      {projects && projects.length === 0 && (
        <div className="text-center py-20 text-muted">
          <Film size={40} className="mx-auto mb-4 text-muted" />
          <p className="lowercase">No projects yet. Generate your first short from the Clip Generator.</p>
        </div>
      )}

      <div className="space-y-3">
        {(projects || []).map((p) => {
          const [badgeClass, badgeLabel] = STATUS_BADGE[p.status] || ['badge-warn', p.status];
          const active = p.status === 'queued' || p.status === 'processing';
          const isBusy = busy === p.job_id;
          return (
            <div key={p.job_id} className={`card p-4 flex flex-col sm:flex-row sm:items-center gap-3 ${p.job_id === currentJobId ? 'border-brass/60' : ''}`}>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1 min-w-0">
                  <span className={`${badgeClass} shrink-0`}>{badgeLabel.toUpperCase()}</span>
                  <p className="text-sm text-ink font-medium truncate" title={p.source || p.title}>{p.title}</p>
                </div>
                <p className="readout">
                  {fmtDate(p.created_at)}
                  {p.clips != null && <> · {p.clips} clip{p.clips === 1 ? '' : 's'}</>}
                  {' · '}{fmtSize(p.size_bytes)}
                  {p.queue && <> · #{p.queue.position} in line</>}
                  {p.job_id === currentJobId && <> · open now</>}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                {p.status !== 'cancelled' && (
                  <button
                    onClick={() => onOpenProject(p.job_id)}
                    disabled={isBusy}
                    className="btn-ghost px-3 py-2 text-xs"
                  >
                    <FolderOpen size={14} /> open
                  </button>
                )}
                {active && (
                  <button
                    onClick={() => cancel(p.job_id)}
                    disabled={isBusy}
                    className="btn-ghost px-3 py-2 text-xs"
                    title="Stop this job. Its files stay until you delete them."
                  >
                    {isBusy ? <Loader2 size={14} className="animate-spin" /> : <Square size={14} />} cancel
                  </button>
                )}
                {confirmDelete === p.job_id ? (
                  <>
                    <button onClick={() => remove(p.job_id)} className="btn-danger px-3 py-2 text-xs">
                      <Trash2 size={14} /> yes, delete {fmtSize(p.size_bytes)}
                    </button>
                    <button onClick={() => setConfirmDelete(null)} className="btn-quiet px-3 py-2 text-xs">keep</button>
                  </>
                ) : (
                  <button
                    onClick={() => setConfirmDelete(p.job_id)}
                    disabled={isBusy}
                    className="btn-ghost px-3 py-2 text-xs"
                    title={active ? 'Cancel this job and delete its files' : 'Delete this project and its files'}
                  >
                    {isBusy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />} delete
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
