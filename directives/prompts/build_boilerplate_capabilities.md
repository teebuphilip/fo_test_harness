**BOILERPLATE CAPABILITY LIBRARY — 44 BUILT-IN FUNCTIONS:**

You have access to 44 pre-built SaaS capabilities. **Scan the intake and USE applicable ones.** Do NOT build these from scratch. Each entry shows: what it does | exact import | key function(s).

---

**CORE MODULES** (`saas-boilerplate/backend/core/`)

**[AUTH] Authentication & RBAC** — always use for any protected route
```python
from core.rbac import get_current_user, require_role, require_any_role
# get_current_user returns: {"sub": "auth0|...", "email": "...", "roles": {...}, "tenant_id": "..."}
# Use current_user["sub"] as the user ID — NEVER hardcode it
async def my_route(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user["sub"]
# Role guard (admin-only route):
async def admin_route(current_user: dict = Depends(require_role("admin"))): ...
```

**[TENANCY] Multi-Tenancy** — use when app has per-user or per-org data isolation
```python
from core.tenancy import TenantMixin, get_tenant_db
# Add TenantMixin to any model that needs tenant isolation:
class Report(TenantMixin, Base):
    __tablename__ = "reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # tenant_id column added automatically by TenantMixin
# Tenant-scoped DB session (auto-filters all queries by tenant_id):
def my_route(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    tenant_id = current_user["tenant_id"]
    tenant_db = get_tenant_db(db, tenant_id)
    return tenant_db.query(Report).all()  # auto-filtered to this tenant
```

**[ENTITLEMENTS] Feature Gating** — use when features differ by subscription tier
```python
from core.entitlements import require_entitlement, has_entitlement, get_entitlements
# Gate a route to users with a specific feature:
async def premium_route(current_user: dict = Depends(require_entitlement("feature:reports"))): ...
# Check programmatically:
if has_entitlement(current_user["sub"], "feature:exports", db): ...
```

**[USAGE] Usage Limits & Quota** — use when app has metered features (AI calls, exports, posts, etc.)
```python
from core.usage_limits import check_and_increment, get_usage_summary
# Check + increment in one call (raises UsageLimitExceeded if over limit):
check_and_increment(db, tenant_id=current_user["tenant_id"], feature="ai_generations", tier="pro")
# Get usage dashboard:
summary = get_usage_summary(db, tenant_id, tier="pro")
```

**[AI] AI Calls with Cost Tracking & Budget** — use whenever the app calls Claude or OpenAI
```python
from core.ai_governance import call_ai, route_model, check_budget
# Call AI with automatic cost tracking, budget enforcement, model routing:
result = call_ai(
    db=db,
    tenant_id=current_user["tenant_id"],
    task_type="summarization",       # routes to appropriate model by tier
    prompt="...",
    system="...",
    tier=current_user.get("tier", "pro")
)
# result: {"content": "...", "model": "...", "cost_usd": 0.002, "tokens_in": 100, "tokens_out": 50}
# Manual model routing:
model = route_model(task_type="analysis", tenant_tier="pro")  # returns e.g. "claude-haiku-4-5"
```

**[ONBOARDING] Onboarding Flow** — use when app has a setup wizard or first-run experience
```python
from core.onboarding import get_or_create_onboarding, mark_step_complete, is_onboarding_complete
# Get or create onboarding state:
state = get_or_create_onboarding(db, current_user["sub"])
# Complete a step:
mark_step_complete(db, current_user["sub"], step="profile_setup")
# Check completion:
if is_onboarding_complete(db, current_user["sub"]): ...
```

**[TRIAL] Trial Management** — use when app has a free trial period
```python
from core.trial import start_trial, is_trial_active, mark_trial_converted, get_expiring_trials
start_trial(db, current_user["sub"], trial_days=14)
if is_trial_active(db, current_user["sub"]): ...
mark_trial_converted(db, current_user["sub"])
```

**[ACTIVATION] Activation Tracking** — use to record first meaningful actions
```python
from core.activation import record_activation, is_activated
# Idempotent — safe to call on every action, only records first occurrence:
record_activation(db, current_user["sub"], event_name="first_report_generated")
# Track: first_ai_generation, first_listing_created, first_api_call, profile_completed, etc.
```

**[LISTINGS] Listing CRUD** — use for any marketplace, directory, or catalog feature
```python
from core.listings import create_listing, get_listing, list_listings, update_listing, delete_listing
listing = create_listing(db, owner_id=current_user["sub"], tenant_id=current_user["tenant_id"],
    title="...", description="...", price_cents=2999, listing_type="service")
results = list_listings(db, tenant_id=current_user["tenant_id"], listing_type="service")
```

**[PURCHASE] Purchase Delivery** — use for one-time purchases, digital product delivery
```python
from core.purchase_delivery import deliver_purchase, has_purchased, get_purchases_for_buyer
deliver_purchase(db, buyer_id=current_user["sub"], listing_id=listing_id,
    delivery_method="entitlement", delivery_payload={"feature": "pro_report"})
if has_purchased(db, buyer_id=current_user["sub"], listing_id=listing_id): ...
```

**[SOCIAL] Social Media Posting** — use when app publishes content to social platforms
```python
from core.posting import post_to_reddit, post_to_twitter, post_twitter_thread, post_to_linkedin, post_to_discord, post_to_all_platforms
result = post_to_reddit(title="...", content="...", subreddit="r/example")
result = post_to_twitter(content="...")
results = post_twitter_thread(["tweet 1", "tweet 2", "tweet 3"])
result = post_to_linkedin(content="...")
# Post everywhere at once:
results = post_to_all_platforms({"reddit": {...}, "twitter": {...}, "linkedin": {...}})
# result: PostResult(success=True, post_id="...", url="...")
```

**[LEGAL] Privacy Consent & ToS** — use for any app with ToS/Privacy policy
```python
from core.legal_consent import record_consent, require_fresh_consent, get_consent_status
# Record user accepting ToS:
record_consent(db, current_user["sub"], doc_type="terms_of_service", version="1.0", client_ip=request.client.host)
# Gate route behind fresh consent:
async def protected(current_user: dict = Depends(get_current_user), _=Depends(require_fresh_consent)): ...
```

**[OFFBOARDING] Cancellation Flow** — use when app has subscription cancellation
```python
from core.offboarding import initiate_offboarding, complete_offboarding
initiate_offboarding(db, current_user["sub"], reason="too_expensive", feedback="...")
```

**[CLOSURE] Account Closure & GDPR Purge** — use for account deletion
```python
from core.account_closure import initiate_closure, cancel_closure
initiate_closure(db, current_user["sub"], reason="user_requested")
```

**[FRAUD] Fraud & Abuse Detection** — use when app has AI or API usage susceptible to abuse
```python
from core.fraud import detect_ai_abuse, detect_api_abuse, lock_account, record_fraud_event
if detect_ai_abuse(db, current_user["sub"]): lock_account(db, current_user["sub"], reason="ai_abuse")
from core.ip_throttle import IPThrottleMiddleware  # register in main.py: app.add_middleware(IPThrottleMiddleware)
```

**[FINANCIAL] Financial Governance** — use for operator P&L/accounting visibility
```python
from core.financial_governance import record_stripe_transaction, get_gross_margin
from core.expense_tracking import log_expense, get_pl_summary
log_expense(db, category="ai_api", amount_usd=0.05, description="Claude call", tenant_id=...)
```

---

**SHARED LIBS** (`teebu-shared-libs/lib/` — load from config file)

**[STRIPE] Billing** — use for subscriptions, payments, invoicing
```python
from lib.stripe_lib import load_stripe_lib
stripe = load_stripe_lib("config/stripe_config.json")
# Key methods:
stripe.create_subscription_product(name, description, prices=[{"amount": 2900, "interval": "month"}])
stripe.create_payment_link(price_id, success_url, cancel_url)
stripe.cancel_subscription(subscription_id)
stripe.create_trial_subscription(customer_id, price_id, trial_days=14)
stripe.create_coupon(percent_off=20, duration="once", name="LAUNCH20")
# Split payments (marketplace):
from lib.stripe_lib import load_stripe_connect_lib
connect = load_stripe_connect_lib("config/stripe_config.json")
connect.create_payment_intent_with_split(amount=5000, connected_account_id=..., application_fee=500)
```

**[EMAIL] Transactional & Marketing Email** — use for welcome emails, notifications, campaigns
```python
from lib.mailerlite_lib import load_mailerlite_lib
mailer = load_mailerlite_lib("config/mailerlite_config.json")
# Transactional:
mailer.send_welcome_email(subscriber_email, subscriber_name)
mailer.send_subscription_confirmation(subscriber_email, plan_name, amount)
mailer.send_payment_failed_notification(subscriber_email)
mailer.send_subscription_cancelled(subscriber_email)
# Marketing:
mailer.add_subscriber(email, name, fields={"company": "Acme"})
mailer.add_subscriber_to_group(subscriber_id, group_id)
mailer.list_campaigns()
```

**[ANALYTICS] Product Analytics (PostHog/GA4)** — use for tracking user behavior
```python
from lib.analytics_lib import load_analytics_lib
analytics = load_analytics_lib("config/analytics_config.json")
analytics.track_signup(user_id, email, plan="pro")
analytics.track_event(user_id, "report_generated", {"report_type": "executive"})
analytics.track_purchase(user_id, amount_usd=29.0, product_name="Pro Plan")
analytics.track_subscription_start(user_id, plan="pro", amount_usd=29.0)
```

**[SEARCH] Full-Text Search (MeiliSearch)** — use for searchable content, listings, users
```python
from lib.meilisearch_lib import load_meilisearch_lib
search = load_meilisearch_lib("config/meilisearch_config.json")
search.add_documents(index="reports", documents=[{"id": "...", "title": "...", "content": "..."}])
results = search.search(index="reports", query="workforce transformation", limit=10)
search.delete_document(index="reports", document_id="...")
```

---

**HOW TO USE THIS:**
1. Read the intake — identify which capabilities the app needs.
2. Import and USE those capabilities in your business routes — do not reimplement them.
3. If the intake mentions AI generation → use `call_ai`. Social → use `posting`. Email → use `mailerlite`. Search → use `meilisearch`. Payments → use `stripe`. Multi-user data → use `TenantMixin`. Metered features → use `check_and_increment`. First-run wizard → use `onboarding`. Trial → use `trial`. Marketplace → use `listings` + `purchase_delivery`.
4. NEVER build a custom version of any capability listed above.
