import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface OnboardingContextType {
  hasCompletedOnboarding: boolean;
  currentStep: number;
  totalSteps: number;
  completeOnboarding: () => void;
  resetOnboarding: () => void;
  setStep: (step: number) => void;
  skipOnboarding: () => void;
}

const OnboardingContext = createContext<OnboardingContextType | undefined>(undefined);

const ONBOARDING_STORAGE_KEY = 'repolens_onboarding_completed';

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [hasCompletedOnboarding, setHasCompletedOnboarding] = useState<boolean>(() => {
    const stored = localStorage.getItem(ONBOARDING_STORAGE_KEY);
    return stored === 'true';
  });
  const [currentStep, setCurrentStep] = useState(0);
  const totalSteps = 5;

  useEffect(() => {
    localStorage.setItem(ONBOARDING_STORAGE_KEY, hasCompletedOnboarding.toString());
  }, [hasCompletedOnboarding]);

  const completeOnboarding = () => {
    setHasCompletedOnboarding(true);
    setCurrentStep(0);
  };

  const resetOnboarding = () => {
    setHasCompletedOnboarding(false);
    setCurrentStep(0);
    localStorage.removeItem(ONBOARDING_STORAGE_KEY);
  };

  const skipOnboarding = () => {
    setHasCompletedOnboarding(true);
    setCurrentStep(0);
  };

  const setStep = (step: number) => {
    if (step >= 0 && step < totalSteps) {
      setCurrentStep(step);
    }
  };

  return (
    <OnboardingContext.Provider
      value={{
        hasCompletedOnboarding,
        currentStep,
        totalSteps,
        completeOnboarding,
        resetOnboarding,
        setStep,
        skipOnboarding,
      }}
    >
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const context = useContext(OnboardingContext);
  if (context === undefined) {
    throw new Error('useOnboarding must be used within OnboardingProvider');
  }
  return context;
}
