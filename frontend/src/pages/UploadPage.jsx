import { useState, useCallback, useEffect, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import { pingHealth, uploadFiles, getJob, startRender, fetchRenderStatus, API_URL } from '../lib/api';

const LAVENDER = '#a886ddff';   // brand color you chose
const DARK_PURPLE = '#20093A';

export default function UploadPage() {
  const [files, setFiles] = useState([]);        // {file, previewUrl, id}
  const [apiOnline, setApiOnline] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadError, setUploadError] = useState('');
  const [job, setJob] = useState(null);          // {job_id,...}

  // NEW: render states
  const [renderId, setRenderId] = useState(null);
  const [renderStatus, setRenderStatus] = useState(null); // null|queued|processing|done|error
  const [renderPct, setRenderPct] = useState(0);
  const [renderErr, setRenderErr] = useState('');
  const [downloadUrl, setDownloadUrl] = useState('');
  const pollRef = useRef(null);

  // ping API once
  useEffect(() => {
    const ctrl = new AbortController();
    pingHealth(ctrl.signal).then(setApiOnline).catch(() => setApiOnline(false));
    return () => ctrl.abort();
  }, []);

  // dropzone
  const onDrop = useCallback((accepted) => {
    const mapped = accepted.map((file) => ({
      file,
      previewUrl: URL.createObjectURL(file),
      id: `${file.name}-${file.size}-${file.lastModified}`,
    }));
    setFiles((prev) => [...prev, ...mapped].slice(0, 25));
    // reset prior results
    setJob(null); setRenderId(null); setRenderStatus(null);
    setDownloadUrl(''); setRenderErr(''); setUploadError('');
    setUploadPct(0); setRenderPct(0);
  }, []);
  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop, accept: { 'image/*': [] }, maxFiles: 25, multiple: true,
  });

  // cleanup URLs
  useEffect(() => () => files.forEach(f => URL.revokeObjectURL(f.previewUrl)), [files]);

  const removeFile = (id) => setFiles((prev) => prev.filter((f) => f.id !== id));
  const clearAll = () => {
    files.forEach(f => URL.revokeObjectURL(f.previewUrl));
    setFiles([]); setJob(null); setRenderId(null);
    setRenderStatus(null); setDownloadUrl('');
    setUploadError(''); setRenderErr('');
    setUploadPct(0); setRenderPct(0);
  };

  // upload handler
  const handleUpload = async () => {
    if (!files.length || isUploading) return;
    setIsUploading(true);
    setUploadPct(0); setUploadError(''); setJob(null);
    setRenderId(null); setRenderStatus(null); setDownloadUrl('');
    try {
      const resp = await uploadFiles(files, pct => setUploadPct(pct));
      setJob(resp);
      setUploadPct(100);
    } catch (e) {
      setUploadError(e.message || 'Upload failed'); setUploadPct(0);
    } finally {
      setIsUploading(false);
    }
  };

  // start render
  const handleStartRender = async () => {
    if (!job?.job_id || renderStatus === 'processing' || renderStatus === 'queued') return;
    setRenderErr(''); setRenderPct(0);
    try {
      const r = await startRender(job.job_id);
      setRenderId(r.render_id);
      setRenderStatus(r.status || 'queued');

      // start polling every 500ms
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const s = await fetchRenderStatus(r.render_id);
          setRenderStatus(s.status);
          setRenderPct(s.progress ?? 0);
          if (s.download_url) setDownloadUrl(`${API_URL}${s.download_url}`);
          if (s.status === 'done' || s.status === 'error') {
            clearInterval(pollRef.current);
            pollRef.current = null;
            if (s.error) setRenderErr(s.error);
          }
        } catch {
          // transient fetch error — ignore; next tick will retry
        }
      }, 500);
    } catch (e) {
      setRenderErr(e.message || 'Could not start render');
    }
  };

  // stop polling on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  return (
    <div className="min-h-screen p-8" style={{ backgroundColor: LAVENDER, color: DARK_PURPLE }}>
      <div className="max-w-5xl mx-auto">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Vibello — Upload & Preview</h1>
            <p className="opacity-80">Free: up to 25 photos, with watermark later.</p>
          </div>
          <div
            className="px-3 py-1 rounded-full text-sm font-medium"
            title={apiOnline === null ? 'Checking API…' : apiOnline ? 'API online' : 'API offline'}
            style={{ background: apiOnline === null ? '#eee' : apiOnline ? '#16a34a' : '#dc2626', color: 'white' }}
          >
            API: {apiOnline === null ? 'Checking…' : apiOnline ? 'Online' : 'Offline'}
          </div>
        </header>

        <section
          {...getRootProps({ className: 'rounded-2xl border-2 border-dashed transition-all p-10 text-center cursor-pointer' })}
          style={{
            background: 'white',
            borderColor: isDragActive ? DARK_PURPLE : '#bda7e6',
            boxShadow: isDragActive ? '0 0 0 4px rgba(32,9,58,0.15)' : 'none',
          }}
        >
          <input {...getInputProps()} />
          <div className="space-y-2">
            <p className="text-xl font-semibold">
              {isDragActive ? 'Drop photos to add them' : 'Drag & drop photos here'}
            </p>
            <p className="text-sm opacity-70">…or click to browse. Images only.</p>
            <p className="text-sm font-medium">{files.length}/25 selected</p>
            {fileRejections?.length > 0 && (
              <p className="text-sm" style={{ color: '#8a1c1c' }}>
                Some files were rejected (not images or over the limit).
              </p>
            )}
          </div>
        </section>

        {files.length > 0 && (
          <>
            <div className="flex items-center justify-between mt-6 gap-3">
              <h2 className="text-xl font-semibold">Preview</h2>
              <div className="flex items-center gap-2">
                <button
                  className="px-4 py-2 rounded-xl"
                  onClick={clearAll}
                  disabled={isUploading || renderStatus === 'processing' || renderStatus === 'queued'}
                  style={{ backgroundColor: '#eee', color: DARK_PURPLE }}
                >
                  Clear all
                </button>
                <button
                  className="px-4 py-2 rounded-xl"
                  onClick={handleUpload}
                  disabled={isUploading || !files.length || !apiOnline}
                  style={{ backgroundColor: DARK_PURPLE, color: 'white', opacity: isUploading || !apiOnline ? 0.7 : 1 }}
                  title={!apiOnline ? 'Backend offline' : 'Upload selected photos'}
                >
                  {isUploading ? 'Uploading…' : `Upload ${files.length} photo(s)`}
                </button>
                <button
                  className="px-4 py-2 rounded-xl"
                  onClick={handleStartRender}
                  disabled={!job?.job_id || renderStatus === 'processing' || renderStatus === 'queued'}
                  style={{ backgroundColor: DARK_PURPLE, color: 'white', opacity: !job?.job_id ? 0.5 : 1 }}
                  title={!job?.job_id ? 'Upload first to get a job_id' : 'Render slideshow'}
                >
                  {renderStatus === 'processing' || renderStatus === 'queued' ? 'Rendering…' : 'Render slideshow'}
                </button>
              </div>
            </div>

            {/* Upload progress */}
            {(isUploading || uploadPct > 0) && (
              <div className="mt-3 bg-white rounded-xl p-3 shadow">
                <div className="text-sm mb-1">Upload progress: {uploadPct}%</div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-3" style={{ width: `${uploadPct}%`, background: DARK_PURPLE, transition: 'width 200ms' }} />
                </div>
                {uploadError && <div className="mt-2 text-sm" style={{ color: '#8a1c1c' }}>{uploadError}</div>}
              </div>
            )}

            {/* Render progress */}
            {(renderStatus && renderStatus !== 'done') && (
              <div className="mt-3 bg-white rounded-xl p-3 shadow">
                <div className="text-sm mb-1">Render status: {renderStatus} — {renderPct}%</div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-3" style={{ width: `${renderPct}%`, background: DARK_PURPLE, transition: 'width 200ms' }} />
                </div>
                {renderErr && <div className="mt-2 text-sm" style={{ color: '#8a1c1c' }}>{renderErr}</div>}
              </div>
            )}

            {/* Thumbnails */}
            <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 mt-4">
              {files.map((f) => (
                <li key={f.id} className="bg-white rounded-xl overflow-hidden shadow">
                  <div className="aspect-[4/3] overflow-hidden">
                    <img src={f.previewUrl} alt={f.file.name} className="w-full h-full object-cover" />
                  </div>
                  <div className="p-2 flex items-center justify-between">
                    <span className="text-xs truncate max-w-[70%]" title={f.file.name}>{f.file.name}</span>
                    <button
                      className="text-xs px-2 py-1 rounded-lg"
                      onClick={() => removeFile(f.id)}
                      style={{ backgroundColor: '#eee', color: DARK_PURPLE }}
                      disabled={isUploading || renderStatus === 'processing' || renderStatus === 'queued'}
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}

        {/* Download card */}
        {renderStatus === 'done' && downloadUrl && (
          <div className="mt-6 bg-white rounded-xl p-4 shadow">
            <div className="font-semibold">Render complete</div>
            <div className="text-sm mt-1">render_id: <code>{renderId}</code></div>
            <a
              className="inline-block mt-3 px-3 py-2 rounded-lg"
              href={downloadUrl}
              target="_blank" rel="noreferrer"
              style={{ backgroundColor: DARK_PURPLE, color: 'white' }}
            >
              Download MP4
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
