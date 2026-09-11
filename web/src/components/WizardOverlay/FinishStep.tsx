interface FinishStepProps {
  onSkip: () => void;
  onFinish: () => void;
}

export function FinishStep({ onSkip, onFinish }: FinishStepProps) {
  return (
    <div style={{ padding: '32px', maxWidth: '600px' }}>
      <h2 style={{ marginTop: 0, marginBottom: '16px' }}>
        Ready to analyze
      </h2>
      
      <p style={{ marginBottom: '24px', lineHeight: 1.5 }}>
        Your dataset is uploaded and ready. When you click Finish, you'll be taken to the chat interface where you can ask questions about your data.
      </p>

      <p style={{ 
        marginBottom: '32px',
        padding: '16px',
        background: '#f5f5f5',
        borderRadius: '4px',
        fontSize: '0.9em',
        color: '#666',
      }}>
        You can always reopen this wizard from the empty chat screen if you need guidance.
      </p>

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
        
        <button
          onClick={onFinish}
          style={{
            background: '#28a745',
            color: 'white',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          Finish
        </button>
      </div>
    </div>
  );
}