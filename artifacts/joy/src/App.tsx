import { useEffect, useState } from 'react';
import { apiUrl } from '@/lib/api';
import { AuthLoading } from '@/components/auth-loading';
import {
  ClerkProvider,
  SignIn,
  SignUp,
  useAuth,
  useClerk,
} from '@clerk/react';
import { publishableKeyFromHost } from '@clerk/react/internal';
import { shadcn } from '@clerk/themes';
import {
  Redirect,
  Route,
  Switch,
  useLocation,
  Router as WouterRouter,
} from 'wouter';
import NotFound from '@/pages/not-found';
import Home from '@/pages/home';
import PrivacyPolicyPage from '@/pages/privacy';
import TermsOfServicePage from '@/pages/terms';
import DashboardLayout from '@/pages/dashboard/layout';
import IntegrationHubPage from '@/pages/dashboard/integration-hub';
import KnowledgeBrainPage from '@/pages/dashboard/knowledge-brain';
import EmployeeRosterPage from '@/pages/dashboard/employee-roster';
import OperatorWorkbenchPage from '@/pages/dashboard/operator-workbench';

const DEFAULT_TITLE = 'JOY - Multi-Tenant Digital Workforce Platform';
const TITLES: Record<string, string> = {
  '/privacy': 'Privacy Policy | JOY Digital Workforce',
  '/terms': 'Terms of Service | JOY Digital Workforce',
  '/sign-in': 'Sign in | JOY',
  '/sign-up': 'Create account | JOY',
};

const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');
const clerkPubKey = publishableKeyFromHost(
  window.location.hostname,
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
);
const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL;

if (!clerkPubKey) {
  throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY for Clerk sign-in.');
}

const clerkAppearance = {
  theme: shadcn,
  options: {
    logoPlacement: 'inside' as const,
    logoLinkUrl: basePath || '/',
    logoImageUrl: `${window.location.origin}${basePath}/logo.svg`,
  },
  variables: {
    colorPrimary: '#16856B',
    colorForeground: '#18181B',
    colorMutedForeground: '#71717A',
    colorDanger: '#B42318',
    colorBackground: '#FFFFFF',
    colorInput: '#FFFFFF',
    colorInputForeground: '#18181B',
    colorNeutral: '#E4E4E7',
    fontFamily: '"Geist", system-ui, sans-serif',
    borderRadius: '0.75rem',
  },
};

function TitleSync() {
  const [location] = useLocation();
  useEffect(() => {
    document.title = TITLES[location] ?? DEFAULT_TITLE;
  }, [location]);
  return null;
}

type OwnerAccess = 'checking' | 'owner' | 'forbidden' | 'error';

function DashboardAccess({ authRequired }: { authRequired: boolean | null }) {
  const { isLoaded, isSignedIn } = useAuth();
  const [ownerAccess, setOwnerAccess] = useState<OwnerAccess>('checking');

  useEffect(() => {
    if (!authRequired) {
      setOwnerAccess('owner');
      return;
    }
    if (!isLoaded) return;
    if (!isSignedIn) {
      setOwnerAccess('checking');
      return;
    }

    const controller = new AbortController();
    setOwnerAccess('checking');
    fetch(apiUrl('/api/auth/me'), {
      credentials: 'include',
      signal: controller.signal,
    })
      .then((response) => {
        if (response.status === 401 || response.status === 403) {
          setOwnerAccess('forbidden');
          return;
        }
        if (!response.ok) {
          throw new Error('Unable to verify administrator access.');
        }
        setOwnerAccess('owner');
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === 'AbortError') return;
        setOwnerAccess('error');
      });

    return () => controller.abort();
  }, [authRequired, isLoaded, isSignedIn]);

  if (authRequired === false) return <Dashboard />;
  if (authRequired === null || !isLoaded || (isSignedIn && ownerAccess === 'checking')) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center bg-surface px-4">
        <AuthLoading label="Checking secure access…" />
      </div>
    );
  }
  if (!isSignedIn) return <Redirect to="/sign-in" />;
  if (ownerAccess === 'forbidden') {
    return (
      <AccessNotice
        title="This account does not have JOY owner access"
        message="Sign in with the email configured for the JOY owner account, or contact the workspace owner."
      />
    );
  }
  if (ownerAccess === 'error') {
    return (
      <AccessNotice
        title="We couldn’t verify your access"
        message="Please retry in a moment. Your dashboard remains protected while sign-in verification is unavailable."
      />
    );
  }
  return <Dashboard />;
}

function AccessNotice({ title, message }: { title: string; message: string }) {
  const { signOut } = useClerk();
  return (
    <main className="flex min-h-[70vh] items-center justify-center bg-surface px-6">
      <section className="w-full max-w-md rounded-2xl border border-border bg-white p-8 text-center shadow-sm">
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
          <span className="text-lg font-black">J</span>
        </div>
        <h1 className="text-xl font-bold text-foreground">{title}</h1>
        <p className="mt-3 text-sm leading-6 text-muted">{message}</p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-foreground hover:bg-surface"
            onClick={() => window.location.reload()}
          >
            Retry
          </button>
          <button
            type="button"
            className="rounded-lg bg-foreground px-4 py-2 text-sm font-semibold text-white hover:bg-foreground/90"
            onClick={() => signOut({ redirectUrl: basePath || '/' })}
          >
            Sign out
          </button>
        </div>
      </section>
    </main>
  );
}

function SignInPage() {
  const { isLoaded, isSignedIn } = useAuth();
  if (isLoaded && isSignedIn) return <Redirect to="/dashboard/integration-hub" />;
  return (
    <main className="flex min-h-[100dvh] items-center justify-center bg-surface px-4 py-10">
      {!isLoaded ? <AuthLoading /> : <SignIn
        routing="path"
        path={`${basePath}/sign-in`}
        signUpUrl={`${basePath}/sign-up`}
        appearance={clerkAppearance}
      />}
    </main>
  );
}

function SignUpPage() {
  const { isLoaded, isSignedIn } = useAuth();
  if (isLoaded && isSignedIn) return <Redirect to="/dashboard/integration-hub" />;
  return (
    <main className="flex min-h-[100dvh] items-center justify-center bg-surface px-4 py-10">
      {!isLoaded ? <AuthLoading /> : <SignUp
        routing="path"
        path={`${basePath}/sign-up`}
        signInUrl={`${basePath}/sign-in`}
        appearance={clerkAppearance}
      />}
    </main>
  );
}

function HomeRoute({ authRequired }: { authRequired: boolean | null }) {
  const { isLoaded, isSignedIn } = useAuth();
  if (authRequired && isLoaded && isSignedIn) {
    return <Redirect to="/dashboard/integration-hub" />;
  }
  return <Home />;
}

function ClerkRoutes({ authRequired }: { authRequired: boolean | null }) {
  const [, setLocation] = useLocation();
  return (
    <ClerkProvider
      publishableKey={clerkPubKey}
      proxyUrl={clerkProxyUrl}
      appearance={clerkAppearance}
      signInUrl={`${basePath}/sign-in`}
      signUpUrl={`${basePath}/sign-up`}
      routerPush={(to) =>
        setLocation(basePath && to.startsWith(basePath) ? to.slice(basePath.length) || '/' : to)
      }
      routerReplace={(to) =>
        setLocation(
          basePath && to.startsWith(basePath) ? to.slice(basePath.length) || '/' : to,
          { replace: true },
        )
      }
    >
      <TitleSync />
      <Switch>
        <Route path="/" component={() => <HomeRoute authRequired={authRequired} />} />
        <Route path="/sign-in/*?" component={SignInPage} />
        <Route path="/sign-up/*?" component={SignUpPage} />
        <Route path="/privacy" component={PrivacyPolicyPage} />
        <Route path="/terms" component={TermsOfServicePage} />
        <Route path="/dashboard">
          <Redirect to="/dashboard/integration-hub" />
        </Route>
        <Route path="/dashboard/:rest*">
          <DashboardAccess authRequired={authRequired} />
        </Route>
        <Route component={NotFound} />
      </Switch>
    </ClerkProvider>
  );
}

function Dashboard() {
  return (
    <DashboardLayout>
      <Switch>
        <Route path="/dashboard/integration-hub" component={IntegrationHubPage} />
        <Route path="/dashboard/knowledge-brain" component={KnowledgeBrainPage} />
        <Route path="/dashboard/employee-roster" component={EmployeeRosterPage} />
        <Route path="/dashboard/operator-workbench" component={OperatorWorkbenchPage} />
        <Route component={NotFound} />
      </Switch>
    </DashboardLayout>
  );
}

function App() {
  const [adminAccess, setAdminAccess] = useState<{
    disabled: boolean;
    requiresSignIn: boolean;
  } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);
    fetch(apiUrl('/api/healthz'), { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('Health check failed');
        const health = await response.json();
        if (typeof health.administration_available !== 'boolean' ||
            typeof health.administration_requires_sign_in !== 'boolean') {
          throw new Error('Invalid health check response');
        }
        return health;
      })
      .then((health) =>
        setAdminAccess({
          disabled: health.administration_available === false,
          requiresSignIn: health.administration_requires_sign_in === true,
        }),
      )
      .catch(() =>
        setAdminAccess({
          disabled: true,
          requiresSignIn: true,
        }),
      )
      .finally(() => window.clearTimeout(timer));
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, []);
  return (
    <WouterRouter base={basePath}>
      {adminAccess?.disabled && (
        <div
          role="alert"
          className="border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm text-amber-900"
        >
          Administration is temporarily unavailable because secure sign-in is not configured.
        </div>
      )}
      <ClerkRoutes authRequired={adminAccess?.requiresSignIn ?? null} />
    </WouterRouter>
  );
}

export default App;
