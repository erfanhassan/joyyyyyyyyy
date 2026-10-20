import { useEffect, useState } from 'react';
import { apiUrl } from '@/lib/api';
import { Redirect, Route, Switch, useLocation, Router as WouterRouter } from 'wouter';
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
};

function TitleSync() {
  const [location] = useLocation();
  useEffect(() => {
    document.title = TITLES[location] ?? DEFAULT_TITLE;
  }, [location]);
  return null;
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
  const [administrationDisabled, setAdministrationDisabled] = useState(false);
  useEffect(() => {
    fetch(apiUrl('/api/healthz'))
      .then((response) => response.json())
      .then((health) => setAdministrationDisabled(health.administration_available === false))
      .catch(() => {});
  }, []);
  return (
    <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      {administrationDisabled && (
        <div role="alert" className="bg-amber-50 border-b border-amber-200 px-6 py-3 text-sm text-amber-900">
          Administration is disabled in this public deployment until secure, tenant-authorized sign-in is configured. Use the workspace preview to access the imported dashboard.
        </div>
      )}
      <TitleSync />
      <Switch>
        <Route path="/" component={Home} />
        <Route path="/privacy" component={PrivacyPolicyPage} />
        <Route path="/terms" component={TermsOfServicePage} />
        <Route path="/dashboard">
          <Redirect to="/dashboard/integration-hub" />
        </Route>
        <Route path="/dashboard/:rest*" component={Dashboard} />
        <Route component={NotFound} />
      </Switch>
    </WouterRouter>
  );
}

export default App;
