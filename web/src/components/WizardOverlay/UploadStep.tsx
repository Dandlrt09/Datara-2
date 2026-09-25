import { useCallback, useState, type MutableRefObject } from 'react';
import { useDropzone } from 'react-dropzone';
import { useCreateSession } from '../../queries/useSessions';
import { useUploadFile } from '../../queries/useFiles';
import { SheetPicker } from '../SheetPicker';
import { UPLOAD_ACCEPT_MAP } from '../../lib/uploadFormats';

interface UploadStepProps {
  onSkip: () => void;
  onNext: (sessionId: string) => void;
  /** Shared abort channel owned by the parent wizard. */
  abortRef: MutableRefObject<AbortController | null>;
}

export function UploadStep({ onSkip, onNext, abortRef }: UploadStepProps) {
  const [createdSessionId, setCreatedSessionId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  // Set when the upload resolved to a multi-sheet workbook: the picker is
  // shown before advancing so the first sheet never silently wins.
  const [pendingSheets, setPendingSheets] = useState<{
    fileId: number;
    sheets: string[];
    sheetName: string | null;
  } | null>(null);

  const createSessionMut = useCreateSession();
  const uploadFileMut = useUploadFile();

  const isUploadPending = uploadFileMut.isPending || createSessionMut.isPending;

  const handleCancelUpload = useCallback(() => {
    abortRef.current?.abort();
  }, [abortRef]);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!acceptedFiles.length || isUploadPending) return;

      const file = acceptedFiles[0];
      setUploadError(null);

      // Create the controller synchronously, before the first await, so a Skip /
      // Escape / unmount during session creation still has something to abort.
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        // Create session if not already created in this wizard run
        let sessionId = createdSessionId;
        if (!sessionId) {
          try {
            const result = await createSessionMut.mutateAsync(undefined);
            if (controller.signal.aborted) return; // wizard left during creation
            sessionId = result.id;
            setCreatedSessionId(sessionId);
          } catch (err) {
            setUploadError(`Failed to create session: ${err instanceof Error ? err.message : 'Unknown error'}`);
            return;
          }
        }

        // Upload file
        if (sessionId && !controller.signal.aborted) {
          try {
            const result = await uploadFileMut.mutateAsync({
              sessionId,
              file,
              signal: controller.signal,
            });

            if (result?.sheets && result.sheets.length > 1) {
              // Multi-sheet workbook: surface the picker before advancing.
              setPendingSheets({
                fileId: result.id,
                sheets: result.sheets,
                sheetName: result.sheet_name ?? null,
              });
            } else {
              // Success - move to next step
              onNext(sessionId);
            }
          } catch (err) {
            if (err instanceof Error && err.name === 'AbortError') {
              // Upload cancelled - don't show error
              return;
            }
            setUploadError(`Upload failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
          }
        }
      } finally {
        // Only clear if this is still the current controller (never clobber a newer one).
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [createdSessionId, createSessionMut, uploadFileMut, onNext, isUploadPending, abortRef]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    disabled: isUploadPending,
    accept: UPLOAD_ACCEPT_MAP,
    maxFiles: 1,
  });

  const uploadAborted = uploadFileMut.isError && uploadFileMut.error instanceof Error && 
    uploadFileMut.error.name === 'AbortError';

  return (
    <div style={{ padding: '32px', maxWidth: '600px' }}>
      <h2 style={{ marginTop: 0, marginBottom: '16px' }}>
        Upload your dataset
      </h2>
      
      <p style={{ marginBottom: '24px', lineHeight: 1.5 }}>
        Upload a CSV, XLSX, JSON, or TSV file to analyze. We'll create a chat session for you automatically.
      </p>

      <div
        {...getRootProps()}
        style={{
          border: '2px dashed #ccc',
          borderRadius: '8px',
          padding: '32px',
          textAlign: 'center',
          cursor: isUploadPending ? 'not-allowed' : 'pointer',
          background: isDragActive ? '#e3f2fd' : 'transparent',
          marginBottom: '24px',
          opacity: isUploadPending ? 0.5 : 1,
        }}
      >
        <input {...getInputProps()} disabled={isUploadPending} />
        {isUploadPending ? (
          <p>Uploading...</p>
        ) : isDragActive ? (
          <p>Drop file here...</p>
        ) : (
          <p>Drag and drop a file here, or click to select</p>
        )}
      </div>

      {/* Upload status with cancel */}
      {isUploadPending && (
        <div role="status" style={{ marginBottom: '16px' }}>
          <span style={{ marginRight: '8px' }}>
            {createSessionMut.isPending ? 'Creating session...' : 'Uploading file...'}
          </span>
          <button onClick={handleCancelUpload}>Cancel</button>
        </div>
      )}

      {/* Upload error */}
      {uploadError && (
        <div role="alert" style={{ marginBottom: '16px', color: 'red' }}>
          <p style={{ marginTop: 0, marginBottom: '8px' }}>{uploadError}</p>
          <button
            onClick={() => setUploadError(null)}
            style={{
              background: 'transparent',
              border: '1px solid #ccc',
              padding: '6px 12px',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
        </div>
      )}

      {/* Cancelled upload message */}
      {uploadAborted && (
        <p style={{ color: '#555', marginBottom: '16px' }}>
          Upload cancelled
        </p>
      )}

      {/* Multi-sheet workbook: pick a sheet, then advance. */}
      {pendingSheets && (
        <SheetPicker
          fileId={pendingSheets.fileId}
          sheets={pendingSheets.sheets}
          currentSheet={pendingSheets.sheetName}
          onSelected={() => {
            setPendingSheets(null);
            if (createdSessionId) onNext(createdSessionId);
          }}
        />
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button
          onClick={onSkip}
          style={{
            background: 'transparent',
            border: '1px solid #ccc',
            color: '#666',
            padding: '10px 20px',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          Skip
        </button>
        
        <div style={{ color: '#999', fontSize: '0.9em' }}>
          {createdSessionId ? 'Session created' : 'No file uploaded yet'}
        </div>
      </div>
    </div>
  );
}