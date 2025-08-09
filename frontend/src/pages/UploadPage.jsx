import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { pingHealth, uploadFiles, getJob } from '../lib/api';

const LAVENDER = '#a886ddff';   // your brand color
const DARK_PURPLE = '#20093A';

export default function UploadPage() {
  const [files, setFiles] = useState([]); // {file, previewUrl, id}
  const [apiOnline, setApiOnline] = useState(null); // null | true | false
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadError, setUploadError] = useState('');
  const [job, setJob] = useState(null); // {job_id, saved_count, ...}

  useEffect(() => {
    const ctrl = new AbortController();
    pingHealth(ctrl.signal)
      .then((ok) => setApiOnline(ok))
      .catch(() => setApiOnline(false));
    return () => ctrl.abort();
  }, []);

  const onDrop = useCallback((accepted) => {
    const mapped = accepted.map((file) => ({
      file,
      previewUrl: URL.createObjectURL(file),
      id: `${file.name}-${file.size}-${file.lastModified}`,
    }));
    setFiles((prev) => [...prev, ...mapped].slice(0, 25));
    setJob(null); // reset previous result
    setUploadError('');
  }, []);

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: { 'image/*': [] },
    maxFiles: 25,
    multiple: true,
  });

  useEffect(() => {
    return () => files.forEach((f) => URL.revokeObjectURL(f.previewUrl));
  }, [files]);

  const removeFile = (id) => setFiles((prev) => prev.filter((f) => f.id !== id));
  const clearAll = () => {
    files.forEach((f) => URL.revokeObjectURL(f.previewUrl));
    setFiles([]);
    setJob(null);
    setUploadError('');
    setProgress(0);
  };

  const handleUpload = async () => {
    if (!files.length || isUploading) return;
    setIsUploading(true);
    setProgress(0);
    setUploadError('');
    setJob(null);
    try {
      const resp = await uploadFiles(files, (pct) => setProgress(pct));
      setJob(resp);
      setProgress(100);
    } catch (err) {
      setUploadError(err.message || 'Upload failed');
      setProgress(0);
    } finally {
      setIsUploading(false);
    }
  };

  const checkJob = async () => {
    if (!job?.job_id) return;
    try {
      const j = await getJob(job.job_id);
      alert(`Job ${j.job_id} has ${j.files.length} files:\n` + j.files.join('\n'));
    } catch {
      alert('Could not fetch job details.');
    }
  };

  return (
    <div className="min-h-screen p-8" style={{ backgroundColor: LAVENDER, color: DARK_PURPLE }}>
      <div className="max-w-5xl mx-auto">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Vibello — Upload & Preview</h1>
            <p className="opacity-80">Free: up to 25 photos, with watermark later.</p>
          </div>
          <div
            title={apiOnline === null ? 'Checking API…' : apiOnline ? 'API online' : 'API offline'}
            className="px-3 py-1 rounded-full text-sm font-medium"
            style={{
              background: apiOnline === null ? '#eee' : apiOnline ? '#16a34a' : '#dc2626',
              color: 'white',
            }}
          >
            API: {apiOnline === null ? 'Checking…' : apiOnline ? 'Online' : 'Offline'}
          </div>
        </header>

        <section
          {...getRootProps({
            className:
              'rounded-2xl border-2 border-dashed transition-all p-10 text-center cursor-pointer',
          })}
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
                  disabled={isUploading}
                  style={{ backgroundColor: '#eee', color: DARK_PURPLE }}
                >
                  Clear all
                </button>
                <button
                  className="px-4 py-2 rounded-xl"
                  onClick={handleUpload}
                  disabled={isUploading || !files.length || !apiOnline}
                  style={{
                    backgroundColor: DARK_PURPLE,
                    color: 'white',
                    opacity: isUploading || !apiOnline ? 0.7 : 1,
                  }}
                  title={!apiOnline ? 'Backend offline' : 'Upload selected photos'}
                >
                  {isUploading ? 'Uploading…' : `Upload ${files.length} photo(s)`}
                </button>
              </div>
            </div>

            {/* Progress bar */}
            {(isUploading || progress > 0) && (
              <div className="mt-3 bg-white rounded-xl p-3 shadow">
                <div className="text-sm mb-1">Upload progress: {progress}%</div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className="h-3"
                    style={{ width: `${progress}%`, background: DARK_PURPLE, transition: 'width 200ms' }}
                  />
                </div>
                {uploadError && (
                  <div className="mt-2 text-sm" style={{ color: '#8a1c1c' }}>
                    {uploadError}
                  </div>
                )}
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
                    <span className="text-xs truncate max-w-[70%]" title={f.file.name}>
                      {f.file.name}
                    </span>
                    <button
                      className="text-xs px-2 py-1 rounded-lg"
                      onClick={() => removeFile(f.id)}
                      style={{ backgroundColor: '#eee', color: DARK_PURPLE }}
                      disabled={isUploading}
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}

        {job && (
          <div className="mt-6 bg-white rounded-xl p-4 shadow">
            <div className="font-semibold">Upload complete</div>
            <div className="text-sm mt-1">job_id: <code>{job.job_id}</code></div>
            <div className="text-sm">Saved: {job.saved_count} | Skipped: {job.skipped_count}</div>
            <button
              className="mt-3 px-3 py-2 rounded-lg"
              onClick={checkJob}
              style={{ backgroundColor: DARK_PURPLE, color: 'white' }}
            >
              Check job on server
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
