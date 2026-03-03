# BOILERPLATE SAMPLE CODE — 44 CAPABILITIES

Every snippet below is a **complete, correct usage pattern** drawn from the actual boilerplate source.
Copy these exactly. Do NOT reimplement any of these from scratch.

---

## BACKEND CAPABILITIES

---

### [1] AUTH — Protected Route (core.rbac)

```python
# business/backend/routes/reports.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from core.rbac import get_current_user, require_role

router = APIRouter()

@router.get("/reports")
async def list_reports(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user["sub"]          # Auth0 user ID — use this as owner/consultant ID
    tenant_id = current_user["tenant_id"]  # tenant scope
    email = current_user["email"]
    # ...

@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: str,
    current_user: dict = Depends(require_role("admin")),  # admin-only
    db: Session = Depends(get_db)
):
    # ...
```

---

### [2] TENANCY — Tenant-Scoped DB (core.tenancy)

```python
# business/models/Assessment.py
import uuid
from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.orm import Session
from datetime import datetime
from core.database import Base
from core.tenancy import TenantMixin  # adds tenant_id column automatically

class Assessment(TenantMixin, Base):
    __tablename__ = "assessments"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String, nullable=False)
    owner_id = Column(String, nullable=False)
    data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
```

```python
# business/backend/routes/assessments.py — using tenant-scoped queries
from core.tenancy import get_tenant_db

@router.get("/assessments")
async def list_assessments(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_db = get_tenant_db(db, current_user["tenant_id"])  # auto-filters by tenant
    return tenant_db.query(Assessment).filter(
        Assessment.owner_id == current_user["sub"]
    ).all()

@router.post("/assessments", status_code=201)
async def create_assessment(
    data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_db = get_tenant_db(db, current_user["tenant_id"])
    data["owner_id"] = current_user["sub"]  # inject from JWT — never trust client
    record = Assessment(**data)
    tenant_db.add(record)
    tenant_db.commit()
    tenant_db.refresh(record)
    return record
```

---

### [3] ENTITLEMENTS — Feature Gating (core.entitlements)

```python
# business/backend/routes/exports.py
from core.entitlements import require_entitlement, has_entitlement

@router.get("/exports/csv")
async def export_csv(
    current_user: dict = Depends(require_entitlement("feature:exports")),  # gate entire route
    db: Session = Depends(get_db)
):
    # only reaches here if user has "feature:exports" entitlement
    return generate_csv(db, current_user["sub"])

@router.get("/reports/{id}/pdf")
async def get_pdf(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # programmatic check (e.g. to show UI state vs hard gate)
    if not has_entitlement(current_user["sub"], "feature:pdf_reports", db):
        raise HTTPException(status_code=403, detail="PDF reports require Pro plan")
    # ...
```

---

### [4] USAGE LIMITS — Quota Enforcement (core.usage_limits)

```python
# business/backend/routes/ai_analysis.py
from core.usage_limits import check_and_increment, get_usage_summary, UsageLimitExceeded

@router.post("/analysis/generate")
async def generate_analysis(
    data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Check + increment quota in one atomic call
        check_and_increment(
            db,
            tenant_id=current_user["tenant_id"],
            feature="ai_generations",
            tier=current_user.get("tier", "pro")
        )
    except UsageLimitExceeded as e:
        raise HTTPException(status_code=429, detail=f"Monthly limit reached: {e.feature}")
    # proceed with AI generation...

@router.get("/usage")
async def get_usage(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_usage_summary(db, current_user["tenant_id"], tier="pro")
```

---

### [5] AI GOVERNANCE — Cost-Tracked AI Calls (core.ai_governance)

```python
# business/services/AnalysisService.py
from core.ai_governance import call_ai, route_model, check_budget, BudgetExceededError

class AnalysisService:
    def generate_insights(self, db, current_user: dict, data: dict) -> dict:
        try:
            check_budget(db, current_user["tenant_id"])  # raises if over budget
        except BudgetExceededError:
            return {"error": "Monthly AI budget exceeded"}

        result = call_ai(
            db=db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["sub"],
            feature="workforce_analysis",
            task_type="analysis",
            prompt=f"Analyze this workforce data: {data}",
            system_prompt="You are a workforce analytics expert.",
            tier=current_user.get("tier", "pro"),
            max_tokens=1024
        )
        # result: {"content": "...", "model": "...", "cost_usd": 0.002, "tokens_in": 100, "tokens_out": 50}
        return {"insight": result["content"], "model_used": result["model"]}

    def get_model(self, task_type: str, tier: str) -> str:
        return route_model(task_type=task_type, tenant_tier=tier)
        # returns e.g. "claude-haiku-4-5" for "analysis" + "pro"
```

---

### [6] ONBOARDING — Setup Wizard (core.onboarding)

```python
# business/backend/routes/onboarding.py
from core.onboarding import get_or_create_onboarding, mark_step_complete, is_onboarding_complete

@router.get("/onboarding")
async def get_onboarding_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    state = get_or_create_onboarding(db, current_user["sub"], current_user["tenant_id"])
    return {"steps": state.get_steps(), "is_complete": state.is_complete}

@router.post("/onboarding/steps/{step}")
async def complete_step(
    step: str,  # e.g. "profile_setup", "first_client_added", "integration_connected"
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    state = mark_step_complete(db, current_user["sub"], step)
    return {"steps": state.get_steps(), "is_complete": state.is_complete}
```

---

### [7] TRIAL — Free Trial Management (core.trial)

```python
# business/backend/routes/subscriptions.py
from core.trial import start_trial, is_trial_active, mark_trial_converted, get_expiring_trials

@router.post("/trial/start")
async def begin_trial(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if is_trial_active(db, current_user["sub"]):
        raise HTTPException(status_code=400, detail="Trial already active")
    record = start_trial(db, current_user["sub"], current_user["tenant_id"], trial_days=14)
    return {"trial_end": record.trial_end_at.isoformat()}

@router.get("/trial/status")
async def trial_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    active = is_trial_active(db, current_user["sub"])
    return {"active": active}
```

---

### [8] ACTIVATION — First-Action Tracking (core.activation)

```python
# Record inside any route where a meaningful first action occurs
from core.activation import record_activation, is_activated

@router.post("/reports")
async def create_report(data: dict, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    # ... create report ...
    # Idempotent — safe to call every time; only records first occurrence
    record_activation(db, current_user["sub"], current_user["tenant_id"],
                      event_name="first_report_generated")
    return report
```

---

### [9] LISTINGS — Marketplace CRUD (core.listings)

```python
# business/backend/routes/marketplace.py
from core.listings import create_listing, list_listings, update_listing, delete_listing, get_listing

@router.post("/listings", status_code=201)
async def new_listing(data: dict, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_listing(
        db,
        tenant_id=current_user["tenant_id"],
        seller_id=current_user["sub"],
        title=data["title"],
        price_usd=data["price_usd"],
        description=data.get("description"),
        category=data.get("category"),
        status="draft"
    )

@router.get("/listings")
async def browse_listings(
    category: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return list_listings(db, tenant_id=current_user["tenant_id"], category=category, status="active")
```

---

### [10] PURCHASE DELIVERY — Grant Buyer Access (core.purchase_delivery)

```python
# business/backend/routes/purchases.py
from core.purchase_delivery import deliver_purchase, has_purchased, get_purchases_for_buyer

@router.post("/listings/{listing_id}/purchase")
async def purchase(
    listing_id: int,
    data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if has_purchased(db, current_user["sub"], listing_id):
        raise HTTPException(status_code=400, detail="Already purchased")
    record = deliver_purchase(
        db,
        buyer_auth0_id=current_user["sub"],
        listing_id=listing_id,
        tenant_id=current_user["tenant_id"],
        stripe_payment_intent_id=data.get("payment_intent_id")
    )
    return {"delivered_at": record.delivered_at.isoformat()}
```

---

### [11] SOCIAL POSTING — Multi-Platform Publishing (core.posting)

```python
# business/services/PublishingService.py
from core.posting import post_to_twitter, post_twitter_thread, post_to_reddit, post_to_linkedin, post_to_discord, post_to_all_platforms

class PublishingService:
    def publish_announcement(self, content: str) -> dict:
        result = post_to_twitter(content=content[:280])
        return {"success": result.success, "url": result.url}

    def publish_thread(self, tweets: list) -> list:
        results = post_twitter_thread(tweets)  # list of PostResult
        return [{"tweet": t, "url": r.url, "success": r.success} for t, r in zip(tweets, results)]

    def publish_reddit(self, title: str, body: str, subreddit: str) -> dict:
        result = post_to_reddit(title=title, content=body, subreddit=subreddit)
        return {"success": result.success, "url": result.url}

    def publish_everywhere(self, content: dict) -> dict:
        # content = {"twitter": "...", "reddit": {"title": "...", "content": "...", "subreddit": "..."}, "linkedin": "..."}
        results = post_to_all_platforms(content)
        return {platform: {"success": r.success, "url": r.url} for platform, r in results.items()}
```

---

### [12] LEGAL CONSENT — ToS & Privacy (core.legal_consent)

```python
# business/backend/routes/consent.py
from core.legal_consent import record_consent, get_consent_status, require_fresh_consent

@router.get("/consent/status")
async def consent_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_consent_status(db, current_user["sub"])
    # returns: {"requires_reacceptance": bool, "terms": {...}, "privacy": {...}}

@router.post("/consent")
async def accept_consent(
    data: dict,  # {"doc_type": "terms_of_service", "version": "1.0"}
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record_consent(db, current_user["sub"], data["doc_type"], data["version"],
                   client_ip=request.client.host)
    return {"accepted": True}

# Gate any route behind fresh consent:
@router.get("/dashboard/premium")
async def premium_dashboard(
    current_user: dict = Depends(get_current_user),
    _consent = Depends(require_fresh_consent),  # raises 403 if consent stale
    db: Session = Depends(get_db)
):
    # ...
```

---

### [13] OFFBOARDING — Cancellation Flow (core.offboarding)

```python
# business/backend/routes/account.py
from core.offboarding import initiate_offboarding, complete_offboarding

@router.post("/account/cancel")
async def cancel_subscription(
    data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = initiate_offboarding(
        db,
        auth0_user_id=current_user["sub"],
        tenant_id=current_user["tenant_id"],
        reason=data.get("reason", "not_specified"),
        feedback=data.get("feedback"),
        cancel_at_period_end=True
    )
    return {"cancellation_scheduled": True, "initiated_at": record.initiated_at.isoformat()}
```

---

### [14] ACCOUNT CLOSURE — GDPR Deletion (core.account_closure)

```python
# business/backend/routes/account.py
from core.account_closure import initiate_closure, cancel_closure

@router.post("/account/delete")
async def request_deletion(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = initiate_closure(db, current_user["sub"], current_user["tenant_id"],
                               reason="user_requested")
    return {"purge_at": record.purge_at.isoformat(), "status": record.status}

@router.post("/account/delete/cancel")
async def cancel_deletion(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = cancel_closure(db, current_user["sub"])
    return {"cancelled": success}
```

---

### [15] FRAUD DETECTION — Abuse Prevention (core.fraud)

```python
# Call inside AI or high-value routes
from core.fraud import detect_ai_abuse, lock_account, record_fraud_event, is_account_locked

@router.post("/analysis/generate")
async def generate(data: dict, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if is_account_locked(db, current_user["sub"]):
        raise HTTPException(status_code=403, detail="Account locked")

    if detect_ai_abuse(db, current_user["sub"], minutes=60, threshold=50):
        lock_account(db, current_user["sub"], current_user["tenant_id"], reason="ai_abuse")
        record_fraud_event(db, current_user["sub"], current_user["tenant_id"],
                           event_type="ai_abuse", severity="high", source="rate_detector")
        raise HTTPException(status_code=429, detail="Abuse detected")
    # proceed...
```

---

### [16] FINANCIAL GOVERNANCE — Stripe Fee Tracking (core.financial_governance)

```python
# Call after Stripe webhook confirms payment
from core.financial_governance import record_stripe_transaction, get_gross_margin

def after_payment_succeeded(db, tenant_id: str, gross_usd: float, fee_usd: float, payment_intent_id: str):
    record_stripe_transaction(
        db,
        tenant_id=tenant_id,
        gross_usd=gross_usd,
        fee_usd=fee_usd,
        transaction_type="charge",
        stripe_payment_intent_id=payment_intent_id
    )

@router.get("/admin/margin")
async def margin_report(period: str, current_user: dict = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return get_gross_margin(db, current_user["tenant_id"], period_key=period, revenue_usd=0.0)
```

---

### [17] EXPENSE TRACKING — Cost Attribution & P&L (core.expense_tracking)

```python
# Log AI call costs, infra costs, etc.
from core.expense_tracking import log_expense, get_pl_summary

def after_ai_call(db, tenant_id: str, cost_usd: float, description: str):
    log_expense(db, tenant_id=tenant_id, category="ai_api", amount_usd=cost_usd,
                source="claude_api", description=description, is_recurring=False)

@router.get("/admin/pl")
async def pl_report(month: str, current_user: dict = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return get_pl_summary(db, current_user["tenant_id"], month_key=month, revenue_usd=0.0)
```

---

### [18] MONITORING — Sentry Error Tracking (core.monitoring)

```python
# business/backend/main.py (register in main.py only — NOT in business routes)
from core.monitoring import init_monitoring

app = FastAPI()
init_monitoring(app)  # registers Sentry + middleware

# In business routes — capture specific errors:
from core.monitoring import capture_error, capture_message, set_tenant_context

@router.post("/reports/{id}/generate")
async def generate(report_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    set_tenant_context(current_user["tenant_id"])
    try:
        # ...
    except Exception as e:
        capture_error(e, context={"report_id": report_id})
        raise HTTPException(status_code=500, detail="Report generation failed")
```

---

### [19] IP THROTTLE — Rate Limiting (core.ip_throttle)

```python
# business/backend/main.py (register in main.py)
from core.ip_throttle import IPThrottleMiddleware, auth_rate_limit_dependency

app = FastAPI()
app.add_middleware(IPThrottleMiddleware)  # global IP rate limiting

# Tight rate limit on auth routes:
@router.post("/auth/login")
async def login(_=Depends(auth_rate_limit_dependency)):
    # ...
```

---

### [20] WEBHOOK ENTITLEMENTS — Stripe → Entitlement Sync (core.webhook_entitlements)

```python
# business/backend/main.py — register the webhook router
from core.webhook_entitlements import router as stripe_webhook_router

app.include_router(stripe_webhook_router)
# Handles: checkout.session.completed → grant entitlement
#          customer.subscription.deleted → revoke entitlement
#          invoice.payment_failed → notify
```

---

### [21] DATA RETENTION — Lifecycle Policies (core.data_retention)

```python
# Background job / admin route
from core.data_retention import set_retention_policy, purge_expired_logs, request_data_deletion

# Setup retention policies (run once on startup or admin route):
set_retention_policy(db, data_type="ai_cost_logs", retention_days=90, description="90-day AI cost log retention")
set_retention_policy(db, data_type="activation_events", retention_days=365)

# Scheduled purge job:
def nightly_purge(db):
    counts = purge_expired_logs(db)  # returns {"ai_cost_logs": 42, ...}

# GDPR deletion request:
@router.post("/account/data-export-request")
async def gdpr_request(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    req = request_data_deletion(db, current_user["tenant_id"], requested_by=current_user["sub"])
    return {"sla_deadline": req.sla_deadline.isoformat()}
```

---

### [22] CAPABILITY REGISTRY — Feature Flags (core.capability_loader)

```python
# Check if a capability is enabled for this tenant/tier:
from core.capability_loader import is_capability_enabled, require_capability, get_platform_status

@router.get("/features/search")
async def search_results(
    q: str,
    current_user: dict = Depends(require_capability("search")),  # 403 if disabled
    db: Session = Depends(get_db)
):
    # only reaches here if "search" capability is enabled
    ...

# Programmatic check:
if is_capability_enabled("social_posting", tenant_id=current_user["tenant_id"], tier="pro"):
    # show social posting UI
```

---

## SHARED LIBRARY CAPABILITIES

---

### [23] STRIPE — Subscriptions & Payments (lib.stripe_lib)

```python
# business/backend/routes/billing.py
from lib.stripe_lib import load_stripe_lib

stripe = load_stripe_lib("config/stripe_config.json")

@router.post("/billing/checkout")
async def create_checkout(data: dict, current_user: dict = Depends(get_current_user)):
    session = stripe.create_checkout_session(
        price_id=data["price_id"],
        customer_email=current_user["email"],
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/pricing"
    )
    return {"checkout_url": session["url"]}

@router.post("/billing/trial")
async def start_trial_subscription(data: dict, current_user: dict = Depends(get_current_user)):
    result = stripe.create_trial_subscription(
        customer_id=data["stripe_customer_id"],
        price_id=data["price_id"],
        trial_days=14
    )
    return {"subscription_id": result["id"]}
```

---

### [24] STRIPE CONNECT — Marketplace Split Payments (lib.stripe_lib)

```python
# business/backend/routes/marketplace_payments.py
from lib.stripe_lib import load_stripe_connect_lib

connect = load_stripe_connect_lib("config/stripe_config.json")

@router.post("/marketplace/pay")
async def marketplace_payment(data: dict, current_user: dict = Depends(get_current_user)):
    result = connect.create_payment_intent_with_split(
        amount=data["amount_cents"],
        connected_account_id=data["seller_stripe_account"],
        application_fee=int(data["amount_cents"] * 0.10)  # 10% platform fee
    )
    return {"client_secret": result["client_secret"]}
```

---

### [25] EMAIL — Transactional & Marketing (lib.mailerlite_lib)

```python
# business/services/NotificationService.py
from lib.mailerlite_lib import load_mailerlite_lib

mailer = load_mailerlite_lib("config/mailerlite_config.json")

class NotificationService:
    def on_signup(self, email: str, name: str):
        mailer.send_welcome_email(email, name)
        mailer.add_subscriber(email, fields={"name": name})

    def on_subscription_started(self, email: str, name: str, plan: str):
        mailer.send_subscription_confirmation(email, name, plan_name=plan)

    def on_payment_failed(self, email: str, name: str, amount: float):
        mailer.send_payment_failed_notification(email, name, amount=amount)

    def on_cancellation(self, email: str, name: str):
        mailer.send_subscription_cancelled(email, name)
```

---

### [26] ANALYTICS — Event Tracking (lib.analytics_lib)

```python
# business/services/AnalyticsService.py
from lib.analytics_lib import load_analytics_lib

analytics = load_analytics_lib("config/analytics_config.json")

class AnalyticsService:
    def track_signup(self, user_id: str, email: str, plan: str):
        analytics.track_signup(user_id, signup_method="email", user_properties={"email": email, "plan": plan})

    def track_feature_used(self, user_id: str, feature: str, metadata: dict = None):
        analytics.track_event(user_id, f"feature_used_{feature}", event_params=metadata or {})

    def track_purchase(self, user_id: str, amount_usd: float, product: str):
        analytics.track_purchase(
            transaction_id=str(uuid.uuid4()),
            value=amount_usd,
            user_id=user_id,
            items=[{"name": product, "price": amount_usd}]
        )

    def track_subscription_start(self, user_id: str, plan: str, amount: float):
        analytics.track_subscription_start(
            subscription_id=str(uuid.uuid4()),
            plan_name=plan,
            value=amount,
            user_id=user_id
        )
```

---

### [27] SEARCH — Full-Text Search (lib.meilisearch_lib)

```python
# business/services/SearchService.py
from lib.meilisearch_lib import load_meilisearch_lib

search = load_meilisearch_lib()  # reads MEILISEARCH_HOST + MEILISEARCH_API_KEY from env

class SearchService:
    INDEX = "reports"

    def index_report(self, report: dict):
        search.add_documents(self.INDEX, documents=[{
            "id": report["id"], "title": report.get("title", ""), "content": report.get("executive_summary", "")
        }])

    def search_reports(self, query: str, limit: int = 20) -> list:
        results = search.search(self.INDEX, query=query, limit=limit)
        return results.get("hits", [])

    def remove_report(self, report_id: str):
        search.delete_document(self.INDEX, document_id=report_id)
```

---

### [28] UPTIME MONITORING — Health Checks (lib.betteruptime_lib)

```python
# Register in main.py or a separate health route — NOT in business routes
# BetterUptime pings the /health endpoint; boilerplate handles this automatically.
# You do NOT need to implement uptime monitoring in business routes.
```

---

## FRONTEND CAPABILITIES

---

### [29] AUTH0 — Authentication Hook (CORRECT PATTERN)

```jsx
// CORRECT: destructure getAccessTokenSilently from useAuth0 — it is NOT on the user object
import { useAuth0 } from '@auth0/auth0-react';

export default function MyPage() {
  const { user, isLoading, getAccessTokenSilently } = useAuth0();

  const fetchData = async () => {
    const token = await getAccessTokenSilently();   // ← call directly, NOT user.getAccessTokenSilently()
    const response = await fetch('/api/my-endpoint', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    return response.json();
  };

  if (isLoading) return <div>Loading...</div>;
  if (!user) return null;

  return <div>Welcome, {user.name} ({user.email}) — ID: {user.sub}</div>;
}
```

**WRONG (never do this):**
```jsx
// user.getAccessTokenSilently() — DOES NOT EXIST. user is a profile object only.
const token = await user.getAccessTokenSilently();  // ← throws at runtime
```

---

### [30] PROTECTED ROUTE — Auth Guard Component

```jsx
// Wrap any page that requires login
import ProtectedRoute from '../components/ProtectedRoute';

// In your router or page:
export default function Dashboard() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}
```

---

### [31] CONSENT GATE — ToS Enforcement Component

```jsx
// Wrap app root to enforce ToS acceptance before access
import ConsentGate from '../components/ConsentGate';

export default function App() {
  return (
    <ConsentGate>
      <MainContent />
    </ConsentGate>
  );
  // ConsentGate checks /api/legal/consent/status on mount
  // Shows modal if user needs to re-accept; blocks content until accepted
}
```

---

### [32] API HELPER — Authenticated Axios Instance

```jsx
// Use api.js for all backend calls — handles auth token automatically
import api from '../utils/api';

const fetchReports = async () => {
  const response = await api.get('/reports');
  return response.data;
};

const createReport = async (data) => {
  const response = await api.post('/reports', data);
  return response.data;
};

// api.js reads auth_token from localStorage and adds Authorization header automatically
// On 401, redirects to /login automatically
```

---

### [33] ANALYTICS HOOK — Frontend Event Tracking

```jsx
// Track user actions in any page component
import useAnalytics from '../hooks/useAnalytics';

export default function Dashboard() {
  const { trackEvent, trackPageView } = useAnalytics();

  useEffect(() => {
    trackPageView('/dashboard', 'Dashboard');
  }, []);

  const handleGenerateReport = async () => {
    trackEvent('report_generated', { report_type: 'executive', source: 'dashboard' });
    // ... generate report
  };

  return <button onClick={handleGenerateReport}>Generate Report</button>;
}
```

---

### [34] FETCH WITH TOKEN — Calling Protected Backend Routes

```jsx
// Full pattern: Auth0 token + fetch + error handling
import { useAuth0 } from '@auth0/auth0-react';

export default function ClientList() {
  const { getAccessTokenSilently } = useAuth0();
  const [clients, setClients] = useState([]);

  useEffect(() => {
    const loadClients = async () => {
      try {
        const token = await getAccessTokenSilently();
        const res = await fetch('/api/clients', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setClients(await res.json());
      } catch (err) {
        console.error('Failed to load clients:', err);
      }
    };
    loadClients();
  }, [getAccessTokenSilently]);

  return <ul>{clients.map(c => <li key={c.id}>{c.name}</li>)}</ul>;
}
```

---

### [35] FEATURE FLAG CHECK — Entitlements in Frontend

```jsx
// Check entitlements from backend before showing premium features
import { useState, useEffect } from 'react';
import { useAuth0 } from '@auth0/auth0-react';

export default function PremiumFeature() {
  const { getAccessTokenSilently } = useAuth0();
  const [hasAccess, setHasAccess] = useState(false);

  useEffect(() => {
    const checkAccess = async () => {
      const token = await getAccessTokenSilently();
      const res = await fetch('/api/entitlements', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const entitlements = await res.json();
      setHasAccess(entitlements.includes('feature:pdf_reports'));
    };
    checkAccess();
  }, [getAccessTokenSilently]);

  if (!hasAccess) return <div>Upgrade to Pro for this feature</div>;
  return <PremiumContent />;
}
```

---

### [36] USAGE DISPLAY — Show Quota in UI

```jsx
// Fetch usage summary and show meter in dashboard
import { useEffect, useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';

export default function UsageMeter() {
  const { getAccessTokenSilently } = useAuth0();
  const [usage, setUsage] = useState(null);

  useEffect(() => {
    const loadUsage = async () => {
      const token = await getAccessTokenSilently();
      const res = await fetch('/api/usage', { headers: { 'Authorization': `Bearer ${token}` } });
      setUsage(await res.json());
    };
    loadUsage();
  }, [getAccessTokenSilently]);

  if (!usage) return null;
  return (
    <div>
      AI Generations: {usage.ai_generations?.used || 0} / {usage.ai_generations?.limit || '∞'} this month
    </div>
  );
}
```

---

### [37] ONBOARDING WIZARD — Multi-Step Setup

```jsx
// Pattern: check onboarding steps, mark complete on each step
import { useState, useEffect } from 'react';
import { useAuth0 } from '@auth0/auth0-react';

export default function OnboardingWizard() {
  const { getAccessTokenSilently } = useAuth0();
  const [steps, setSteps] = useState([]);

  const completeStep = async (step) => {
    const token = await getAccessTokenSilently();
    const res = await fetch(`/api/onboarding/steps/${step}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await res.json();
    setSteps(data.steps);
    if (data.is_complete) window.location.href = '/dashboard';
  };

  return (
    <div>
      <button onClick={() => completeStep('profile_setup')}>Complete Profile</button>
    </div>
  );
}
```

---

### [38] TRIAL BANNER — Show Trial Status

```jsx
import { useEffect, useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';

export default function TrialBanner() {
  const { getAccessTokenSilently } = useAuth0();
  const [trial, setTrial] = useState(null);

  useEffect(() => {
    const checkTrial = async () => {
      const token = await getAccessTokenSilently();
      const res = await fetch('/api/trial/status', { headers: { 'Authorization': `Bearer ${token}` } });
      setTrial(await res.json());
    };
    checkTrial();
  }, [getAccessTokenSilently]);

  if (!trial?.active) return null;
  return <div className="bg-blue-50 p-3">Free trial active — upgrade before {trial.trial_end}</div>;
}
```

---

## QA REFERENCE — CORRECT PATTERNS (DO NOT FLAG)

The following patterns are ALL correct boilerplate usage. **Do not flag any of these as defects:**

| Pattern | Correct? | Notes |
|---------|----------|-------|
| `from core.rbac import get_current_user` | ✅ | Correct auth import |
| `Depends(get_current_user)` in route | ✅ | Correct auth enforcement |
| `Depends(require_role("admin"))` | ✅ | Admin role gate |
| `from core.tenancy import TenantMixin, get_tenant_db` | ✅ | Correct tenancy |
| `class Foo(TenantMixin, Base)` | ✅ | Correct tenant-scoped model |
| `tenant_db = get_tenant_db(db, current_user["tenant_id"])` | ✅ | Correct tenant session |
| `from core.database import Base, get_db` | ✅ | Correct DB imports |
| `Depends(get_db)` in route | ✅ | Correct DB injection |
| `from core.ai_governance import call_ai` | ✅ | Correct AI calls — do NOT flag "no AI implementation" |
| `call_ai(db=db, tenant_id=..., feature=..., ...)` | ✅ | Correct AI governance usage |
| `result["content"]` after call_ai | ✅ | Correct result access (content key always present on success) |
| `from core.usage_limits import check_and_increment` | ✅ | Correct quota enforcement |
| `check_and_increment(db, tenant_id=..., feature=..., tier=...)` | ✅ | Correct quota call |
| `from core.entitlements import require_entitlement` | ✅ | Correct feature gating |
| `Depends(require_entitlement("feature:..."))` | ✅ | Correct entitlement gate |
| `from lib.mailerlite_lib import load_mailerlite_lib` | ✅ | Correct email — do NOT flag "missing email" |
| `from lib.stripe_lib import load_stripe_lib` | ✅ | Correct billing — do NOT flag "missing payments" |
| `from lib.analytics_lib import load_analytics_lib` | ✅ | Correct analytics |
| `from lib.meilisearch_lib import load_meilisearch_lib` | ✅ | Correct search |
| `from core.posting import post_to_*` | ✅ | Correct social posting |
| `const { user, isLoading, getAccessTokenSilently } = useAuth0()` | ✅ | Correct Auth0 destructuring |
| `const token = await getAccessTokenSilently()` | ✅ | Correct token fetch |
| `` `Bearer ${token}` `` in Authorization header | ✅ | Correct auth header |
| `current_user["sub"]` as user/owner/consultant ID | ✅ | Correct ID source — do NOT flag "hardcoded" |

**Patterns that ARE bugs (flag these):**
| Pattern | Bug | Correct Fix |
|---------|-----|-------------|
| `user.getAccessTokenSilently()` | ❌ not a method on user | destructure `getAccessTokenSilently` from `useAuth0()` |
| `const { user } = useAuth0()` then call token | ❌ getAccessTokenSilently not destructured | add it: `const { user, getAccessTokenSilently } = useAuth0()` |
| `items_db = {}` or `data_store = []` | ❌ in-memory storage | use SQLAlchemy model + `get_db` |
| `id = len(db) + 1` | ❌ sequential int ID | `id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))` |
| `from flask import Blueprint, jsonify` | ❌ Flask in FastAPI app | use `from fastapi import APIRouter` |
| `consultant_id = 'consultant_1'` | ❌ hardcoded ID | `current_user["sub"]` |
