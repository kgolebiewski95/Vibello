import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';

const LAVENDER = '#a886ddff';   // your brand color
const DARK_PURPLE = '#20093A';

export default function UploadPage() {
  const [files, setFiles] = useState([]); // {file, previewUrl}

  const onDrop = useCallback((accepted) => {
    const mapped = accepted.map((file) => ({
      file,
      previewUrl: URL.createObjectURL(file),
      id: `${file.name}-${file.size}-${file.lastModified}`,
    }));
    // cap at 25 for free tier
    setFiles((prev) => [...prev, ...mapped].slice(0, 25));
  }, []);

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: { 'image/*': [] },
    maxFiles: 25,
    multiple: true,
  });

  // Clean up object URLs to avoid memory leaks
  useEffect(() => {
    return () => {
      files.forEach((f) => URL.revokeObjectURL(f.previewUrl));
    };
  }, [files]);

  const removeFile = (id) => setFiles((prev) => prev.filter((f) => f.id !== id));
  const clearAll = () => {
    files.forEach((f) => URL.revokeObjectURL(f.previewUrl));
    setFiles([]);
  };

  return (
    <div
      className="min-h-screen p-8"
      style={{ backgroundColor: LAVENDER, color: DARK_PURPLE }}
    >
      <div className="max-w-5xl mx-auto">
        <header className="mb-6">
          <h1 className="text-3xl font-bold">Vibello — Upload & Preview</h1>
          <p className="opacity-80">Free: up to 25 photos, with watermark later.</p>
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
            <div className="flex items-center justify-between mt-6">
              <h2 className="text-xl font-semibold">Preview</h2>
              <button
                className="px-4 py-2 rounded-xl"
                onClick={clearAll}
                style={{ backgroundColor: DARK_PURPLE, color: 'white' }}
              >
                Clear all
              </button>
            </div>

            <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 mt-4">
              {files.map((f) => (
                <li key={f.id} className="bg-white rounded-xl overflow-hidden shadow">
                  <div className="aspect-[4/3] overflow-hidden">
                    <img
                      src={f.previewUrl}
                      alt={f.file.name}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="p-2 flex items-center justify-between">
                    <span className="text-xs truncate max-w-[70%]" title={f.file.name}>
                      {f.file.name}
                    </span>
                    <button
                      className="text-xs px-2 py-1 rounded-lg"
                      onClick={() => removeFile(f.id)}
                      style={{ backgroundColor: '#eee', color: DARK_PURPLE }}
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
