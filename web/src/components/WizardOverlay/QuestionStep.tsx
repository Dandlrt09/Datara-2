import { useMemo, useState } from 'react';
import { useProfile } from '../../queries/useFiles';
import { buildSuggestions } from './suggestions';

interface QuestionStepProps {
  onSkip: () => void;
  onNext: (selectedQuestion: string) => void;
  fileId: number | null;
}

export function QuestionStep({ onSkip, onNext, fileId }: QuestionStepProps) {
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);
  const { data: profile } = useProfile(fileId);
  // Deterministic, LLM-free derivation from the already-uploaded profile. While
  // the profile is loading (or absent) this returns the generic fallbacks, so
  // the step never flashes dataset-specific copy that does not match.
  const suggestions = useMemo(() => buildSuggestions(profile ?? null), [profile]);

  const handleSelect = (question: string) => {
    setSelectedQuestion(question);
  };

  const handleNext = () => {
    if (selectedQuestion) {
      onNext(selectedQuestion);
    }
  };

  return (
    <div style={{ padding: '32px', maxWidth: '600px' }}>
      <h2 style={{ marginTop: 0, marginBottom: '16px' }}>
        What would you like to know?
      </h2>
      
      <p style={{ marginBottom: '24px', lineHeight: 1.5 }}>
        Choose a suggested question to get started. The question will be added to your chat input.
      </p>

      <div style={{ marginBottom: '32px' }}>
        {suggestions.map((question, index) => (
          <button
            key={index}
            onClick={() => handleSelect(question)}
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              marginBottom: '12px',
              padding: '16px',
              border: `1px solid ${selectedQuestion === question ? '#007acc' : '#ddd'}`,
              borderRadius: '4px',
              background: selectedQuestion === question ? '#e6f3ff' : 'transparent',
              cursor: 'pointer',
              fontSize: '1em',
              lineHeight: 1.4,
            }}
          >
            {question}
          </button>
        ))}
      </div>

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
          onClick={handleNext}
          disabled={!selectedQuestion}
          style={{
            background: selectedQuestion ? '#007acc' : '#ccc',
            color: 'white',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '4px',
            cursor: selectedQuestion ? 'pointer' : 'not-allowed',
          }}
        >
          Next
        </button>
      </div>
    </div>
  );
}