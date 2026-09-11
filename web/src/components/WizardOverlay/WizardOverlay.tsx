import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useFocusTrap } from './useFocusTrap';
import { useWizardStore } from '../../stores/useWizardStore';
import { writeWizardFlags } from '../../lib/wizardStorage';
import { WelcomeStep } from './WelcomeStep';
import { UploadStep } from './UploadStep';
import { QuestionStep } from './QuestionStep';
import { FinishStep } from './FinishStep';

export function WizardOverlay() {
  const navigate = useNavigate();
  const closeWizard = useWizardStore((state) => state.closeWizard);
  
  const [currentStep, setCurrentStep] = useState<'welcome' | 'upload' | 'question' | 'finish'>('welcome');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);
  const [uploadAbortController, _setUploadAbortController] = useState<AbortController | null>(null);
  
  const dialogRef = useRef<HTMLDivElement>(null);
  const skipButtonRef = useRef<HTMLButtonElement>(null);

  const handleSkip = useCallback(() => {
    // Abort any in-flight upload
    if (uploadAbortController) {
      uploadAbortController.abort();
    }
    
    // Persist skipped state
    writeWizardFlags({ wizardSkipped: true });
    
    // Close wizard
    closeWizard(true);
  }, [uploadAbortController, closeWizard]);

  const handleUploadSuccess = useCallback((newSessionId: string) => {
    setSessionId(newSessionId);
    setCurrentStep('question');
  }, []);

  const handleQuestionSelect = useCallback((question: string) => {
    setSelectedQuestion(question);
    setCurrentStep('finish');
  }, []);

  const handleFinish = useCallback(() => {
    // Persist completed state
    writeWizardFlags({ wizardComplete: true });
    
    // Close wizard
    closeWizard(true);
    
    // Navigate to chat with suggested question
    if (sessionId) {
      navigate(`/app/chat/${sessionId}`, {
        state: { suggestedQuestion: selectedQuestion },
      });
    }
  }, [sessionId, selectedQuestion, closeWizard, navigate]);

  // Set up focus trap
  useFocusTrap(dialogRef, skipButtonRef, handleSkip);

  // Render current step
  const renderStep = () => {
    switch (currentStep) {
      case 'welcome':
        return <WelcomeStep onSkip={handleSkip} onNext={() => setCurrentStep('upload')} />;
      case 'upload':
        return (
          <UploadStep
            onSkip={handleSkip}
            onNext={handleUploadSuccess}
          />
        );
      case 'question':
        return (
          <QuestionStep
            onSkip={handleSkip}
            onNext={handleQuestionSelect}
          />
        );
      case 'finish':
        return <FinishStep onSkip={handleSkip} onFinish={handleFinish} />;
      default:
        return null;
    }
  };

  // Set skip button ref for focus trap
  useEffect(() => {
    // Skip button should be first focusable on every step
    // We update the ref target when step changes
    if (skipButtonRef.current) {
      skipButtonRef.current.focus();
    }
  }, [currentStep]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="First-run wizard"
        style={{
          background: 'white',
          borderRadius: '8px',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)',
          maxWidth: '700px',
          width: '90%',
          maxHeight: '90vh',
          overflow: 'auto',
          position: 'relative',
        }}
        tabIndex={-1}
      >
        {/* Progress indicator */}
        <div style={{
          display: 'flex',
          padding: '16px 32px',
          borderBottom: '1px solid #eee',
          background: '#f9f9f9',
        }}>
          {['welcome', 'upload', 'question', 'finish'].map((step, index) => (
            <div
              key={step}
              style={{
                flex: 1,
                textAlign: 'center',
                padding: '8px',
                color: currentStep === step ? '#007acc' : '#999',
                fontWeight: currentStep === step ? 'bold' : 'normal',
                borderBottom: currentStep === step ? '2px solid #007acc' : 'none',
                fontSize: '0.9em',
              }}
            >
              Step {index + 1}: {step.charAt(0).toUpperCase() + step.slice(1)}
            </div>
          ))}
        </div>
        
        {renderStep()}
        
        {/* Hidden skip button for focus trap (first focusable element) */}
        <button
          ref={skipButtonRef}
          style={{
            position: 'absolute',
            width: '1px',
            height: '1px',
            padding: 0,
            margin: '-1px',
            overflow: 'hidden',
            clip: 'rect(0, 0, 0, 0)',
            whiteSpace: 'nowrap',
            border: 0,
          }}
          aria-hidden="true"
          tabIndex={-1}
        >
          Skip (hidden for accessibility)
        </button>
      </div>
    </div>
  );
}