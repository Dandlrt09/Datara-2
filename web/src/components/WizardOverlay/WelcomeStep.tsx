import { useWizardStore } from '../../stores/useWizardStore';

interface WelcomeStepProps {
  onSkip: () => void;
  onNext: () => void;
}

export function WelcomeStep({ onSkip, onNext }: WelcomeStepProps) {
  const setEngaged = useWizardStore((state) => state.setEngaged);

  const handleGetStarted = () => {
    setEngaged();
    onNext();
  };

  return (
    <div style={{ padding: '32px', maxWidth: '600px' }}>
      <h2 style={{ marginTop: 0, marginBottom: '16px' }}>
        Welcome to Datara
      </h2>
      
      <p style={{ marginBottom: '24px', lineHeight: 1.5 }}>
        Datara helps you analyze your data through natural conversation.
        Let's get started by uploading your first dataset and asking a question.
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
          onClick={handleGetStarted}
          style={{
            background: '#007acc',
            color: 'white',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '4px',
cursor: 'pointer',
        }}
      >
          Get started
        </button>
      </div>
    </div>
  );
}