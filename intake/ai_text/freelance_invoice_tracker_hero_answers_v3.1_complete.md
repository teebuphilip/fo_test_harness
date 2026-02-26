# FounderOps Hero Questions v3.1 - Complete Answers
## Product: Freelance Invoice Tracker

**Startup ID:** freelance_invoice_tracker  
**Startup Name:** InvoiceFlow  
**Date:** 2026-02-26  
**Version:** 3.1

---

## Q1 — Problem Definition

### PROBLEM STATEMENT (2–3 sentences max):
Solo freelancers waste 3-5 hours per week manually creating invoices, tracking which clients have paid, and sending payment reminders. They lose track of overdue invoices and leave money on the table because follow-up is manual and inconsistent. Existing solutions are either too expensive (enterprise accounting software) or too manual (Word templates + Excel spreadsheets).

### WHO EXPERIENCES THIS PROBLEM:
Freelance designers, writers, developers, and consultants who bill 5-20 clients per month with project-based invoices

### CURRENT BROKEN SOLUTION:
They use Word templates or Google Docs to create invoices, Excel spreadsheets to track payments, and manual calendar reminders to follow up with late-paying clients

### ECONOMIC IMPACT:
Wastes 15-20 hours per month on admin work (worth $500-1000 of billable time) and loses $1000-2000 per month in late payments they never chase down because follow-up is too time-consuming

---

## Q2 — Primary User & Market

### PRIMARY USER (Pick ONE):
Freelance creative professionals (designers, writers, photographers) billing 5-20 clients per month with project-based invoices ranging from $500-5000

### SECONDARY USERS (Optional, max 2):
1. Solo consultants (business coaches, marketing consultants) with similar billing patterns
2. Small service providers (bookkeepers, virtual assistants) managing multiple small clients

### ECONOMIC BUYER:
The freelancer themselves (self-funded, paying with personal credit card or business debit card)

### USER SCALE ESTIMATE:
1.5 million active freelancers in US, 500K in Canada, 2 million in Europe actively billing clients monthly (total addressable market ~4 million)

---

## Q3 — Simplest Useful Version (MVP Scope)

### PRIMARY USER ACTION (One sentence):
Create a professional invoice in under 2 minutes and automatically track payment status without maintaining manual spreadsheets

### CORE FEATURES (Pick exactly 3–5):
1. Invoice generator - Fill simple form with client/project info, auto-generate branded PDF with logo and line items
2. Client database - Store client contact information and view complete invoice history per client
3. Payment tracker - Dashboard showing unpaid invoices, overdue invoices (past due date), and paid invoices with date stamps
4. Auto-reminders - System automatically sends payment reminder emails 3 days before due date and 7 days after overdue
5. Quick actions - One-click buttons to "Mark as Paid" (with payment date) and "Send Manual Reminder"

### EXPLICITLY NOT INCLUDED:
- Stripe payment processing or "Pay Now" button integration
- Recurring invoices or subscription billing features
- Multi-currency support or international tax calculations
- Team collaboration or multi-user accounts
- Expense tracking or full accounting suite features
- Time tracking integration
- Mobile native app (web-responsive only)
- Client portal where clients can view/download invoices

---

## Q4 — Happy Path Flow

### STEP-BY-STEP USER FLOW (3–7 steps):
1. User logs in and clicks "New Invoice" button in dashboard
2. User selects existing client from dropdown menu (or clicks "Add New Client" for first-time billing)
3. User enters invoice date, due date (or selects "Net 30" preset), and adds 1-5 line items with description, quantity, and rate
4. System auto-calculates subtotal, optional tax percentage, and total amount due
5. User previews generated PDF invoice with their uploaded logo and custom branding colors
6. User clicks "Send Invoice" button - system emails PDF to client's stored email address and logs invoice as "Sent, Unpaid" with auto-reminder scheduled
7. User sees new invoice appear in "Unpaid Invoices" section of dashboard with due date countdown

### SUCCESS CRITERIA:
Invoice PDF successfully delivered to client's email inbox, invoice record created in database with status "Unpaid", and automated reminder emails scheduled for 3 days before and 7 days after due date

### TIME TO COMPLETE:
Under 90 seconds for repeat clients with saved information, under 3 minutes for brand new clients including adding contact details

---

## Q5 — Required Inputs

### REQUIRED INPUTS:
- Client name: text field (50 char max)
- Client email: email address field with validation
- Invoice line items: repeatable group of {description (text), quantity (number), rate (currency)}
- Invoice due date: date picker or preset selector (Net 15, Net 30, Net 60, Due on Receipt)
- Invoice number: auto-generated sequential but user-editable text field

### OPTIONAL INPUTS:
- Client phone: text field (formatted for US/international)
- Client mailing address: multi-line text area
- Invoice notes: text area for payment instructions, thank you message, or terms (500 char max)
- Tax rate: percentage field (defaults to 0%, common presets: 5%, 8%, 10%)
- Discount: percentage or fixed dollar amount with dropdown selector

### FILE UPLOADS (if any):
- Company logo: PNG or JPG format, max 2MB file size, uploaded once in account settings and applied to all invoices

### ONE-TIME SETUP DATA:
- Business/freelancer name: text
- Business address: multi-line text
- Business email: email (for "from" field and reply-to)
- Tax ID / EIN: text field (optional, US-focused)
- Default payment terms: text (e.g., "Payment due within 30 days", "Late fees apply after 60 days")
- Invoice number prefix: text (e.g., "INV-2024-", "ACME-", defaults to "INV-")
- Brand color: hex color picker for invoice accent color

---

## Q6 — System Outputs

### PRIMARY OUTPUT:
PDF invoice document with professional formatting including:
- Header with user's logo and business information
- "Invoice" title with invoice number and date
- "Bill To" section with client information
- Itemized table with descriptions, quantities, rates, and line totals
- Subtotal, tax (if applicable), discount (if applicable), and total due
- Payment instructions and notes section
- Footer with "Thank you for your business" and payment terms

### SECONDARY OUTPUTS:
1. Email confirmation - Shows invoice was sent successfully with timestamp and recipient email
2. Invoice record - Database entry with sent date, due date, amount, client reference, and current status
3. Shareable view link - Public URL (with random token) where client can view/download invoice in browser without login

### DASHBOARD / REPORTING VIEWS:
- Unpaid invoices list: Client name, invoice number, amount, days until/past due, sorted by due date
- Overdue invoices list: Filtered view showing only invoices past due date, sorted by age (oldest first)
- Paid this month: Total dollar amount collected in current calendar month with invoice count
- Recent activity feed: Last 10 invoice actions (created, sent, paid, reminded) with timestamps
- Total outstanding: Sum of all unpaid invoice amounts across all clients
- Client detail view: Per-client page showing all invoices (paid and unpaid) with total billed lifetime

### NOTIFICATIONS (if any):
- Email to user 1 day before invoice due date: "Reminder: Invoice #123 to ClientName is due tomorrow ($1,500)"
- Email to user 7 days after invoice overdue: "Invoice #123 to ClientName is now 7 days overdue ($1,500)"
- Email to user when client views invoice via shareable link: "ClientName viewed Invoice #123 on [date/time]"
- Optional browser notification when user is logged in and invoice becomes overdue

---

## Q7 — Integrations & Data Sources

### REQUIRED FOR MVP:
- Transactional email service (SendGrid, AWS SES, or Mailgun): Send invoice delivery emails and automated payment reminder emails with PDF attachment

### PHASE 2 INTEGRATIONS:
- Stripe API: Add "Pay Invoice Online" button to enable clients to pay via credit card
- QuickBooks Online API: Sync invoices to accounting software for tax preparation
- Xero API: Alternative accounting software sync
- Zapier: Allow users to connect to 1000+ other tools they already use
- Google Calendar: Sync invoice due dates to user's calendar

### DATA SOURCES:
- User manual input: All client data, invoice line items, business settings, and brand customization
- System-generated data: Invoice numbers (sequential), sent timestamps, payment status tracking, reminder schedules

### APIs EXPECTED TO CALL:
- SendGrid API: POST /v3/mail/send endpoint for transactional invoice delivery emails
- SendGrid API: POST /v3/templates with HTML template for reminder emails
- (Phase 2) Stripe API: POST /v1/checkout/sessions for payment link generation
- (Phase 2) QuickBooks API: POST /v3/company/{realmId}/invoice for accounting sync

---

## Q8 — Revenue & Billing

### PRIMARY REVENUE MODEL:
Monthly subscription with tiered pricing based on invoice volume and features

### PRICING TIERS (if applicable):
**Tier 1 - Starter:** $15/month
- Up to 25 invoices per month
- Unlimited clients
- Email delivery and auto-reminders
- Basic invoice customization (logo + color)
- Email support (48-hour response)

**Tier 2 - Professional:** $29/month
- Unlimited invoices
- Everything in Starter plus:
- Remove "Powered by InvoiceFlow" footer branding
- Advanced customization (custom fonts, letterhead)
- CSV export of all invoice data
- Priority email support (24-hour response)

**Tier 3 - Business:** $49/month
- Everything in Professional plus:
- QuickBooks/Xero sync integration
- Stripe payment processing integration (client can pay via credit card)
- Multiple business profiles (for freelancers with multiple brands)
- Dedicated phone support
- Custom invoice templates

### PAYMENT PROCESSOR:
Stripe (handles subscription billing, automatic renewals, and payment method management)

### WHO PAYS:
The freelancer (end user) pays for their own subscription with credit card or business debit card

### TRIAL / REFUND POLICY:
- 14-day free trial, no credit card required to start trial
- Cancel anytime with no cancellation fees
- Pro-rated refunds available within 7 days of payment if user is unsatisfied
- After cancellation, account remains read-only for 30 days (can view invoices but not create new ones)

---

## Q9 — 30-Day Success Criteria

### MEASURABLE METRICS (3–5 numbers):
1. User signups: 150 registered users who completed onboarding
2. Active users: 50 users who created and sent at least 1 invoice
3. Paying subscribers: 12 users converted from free trial to paid subscription (any tier)
4. Invoices generated: 250+ total invoices created and sent through the platform
5. MRR (Monthly Recurring Revenue): $400 from paid subscriptions

### QUALITATIVE SUCCESS:
- Users successfully create their first invoice within 5 minutes of signup without needing help documentation
- At least 5 users provide feedback stating "This saves me 2+ hours per week compared to my old process"
- Zero critical bugs in invoice generation, email delivery, or payment tracking features
- At least 3 users voluntarily share the product with colleagues (tracked via referral signups or social mentions)
- User interviews reveal the auto-reminder feature is the #1 favorite (saves most time)

### MVP VALIDATION STATEMENT:
A first-time freelancer with no accounting experience can sign up, add their first client, create a professional invoice with their logo, send it via email, and see it tracked in their dashboard as "Unpaid" — all within 10 minutes and without contacting customer support or reading help documentation.

---

## Q10 — Constraints & Non-Goals

### HARD CONSTRAINTS:
- Must launch complete MVP within 45 days from project start
- Total development budget under $5,000 (including all third-party tools, APIs, and hosting for first 3 months)
- Must work reliably on desktop browsers: Chrome, Safari, Firefox, and Edge (latest 2 versions)
- Must be mobile-responsive (works on phone browsers) but no native iOS/Android app required
- Email delivery success rate must be >95% (requires proper SPF/DKIM setup with transactional email provider)

### SOFT CONSTRAINTS:
- Prefer React frontend for easier future feature development and hiring contractors
- Keep monthly operational costs under $150 total (hosting, email API, database, payment processing)
- Use established libraries for PDF generation rather than building custom (e.g., pdfkit, jsPDF, or ReportLab)
- Leverage free tiers where available (Vercel hosting, Railway database, SendGrid free tier)

### NON-GOALS:
- Will NOT build native mobile apps (iOS/Android) in v1 — mobile web browser is sufficient
- Will NOT support team collaboration or multi-user accounts where multiple people share one workspace
- Will NOT build comprehensive accounting suite (expense tracking, P&L reports, tax filing, bookkeeping)
- Will NOT integrate with 20+ accounting tools — focus on QuickBooks and Xero in phase 2 only
- Will NOT support cryptocurrencies, international wire transfers, or ACH direct debit payments
- Will NOT build client portal where clients can log in, dispute invoices, or submit payment proof
- Will NOT build time tracking functionality — user enters billable hours manually
- Will NOT support purchase orders, estimates/quotes, or contracts (invoices only)

### COMPLIANCE / LEGAL:
- Must have Terms of Service and Privacy Policy compliant with GDPR (EU users) and CCPA (California users)
- Must comply with CAN-SPAM Act requirements for automated reminder emails (unsubscribe link, physical address)
- Must use SSL/TLS encryption for all data transmission (HTTPS everywhere)
- Must allow users to export all their data in CSV format (data portability for GDPR)
- Must allow users to request complete account deletion within 30 days (GDPR right to be forgotten)
- Payment processing through Stripe means PCI compliance is handled by Stripe (we never touch card numbers)

---

## Q11 — Architecture Declaration (MANDATORY)

### AUTHENTICATION REQUIRED?
Y (users must create account and log in to create/manage invoices)

### ROLE-BASED ACCESS REQUIRED?
N (single-user accounts only, no admin vs user roles in MVP)

### MULTI-TENANT SYSTEM?
Y (each freelancer sees only their own clients and invoices, strict data isolation required)

### PERSISTENT DATABASE REQUIRED?
Y (store user accounts, clients, invoices, line items, payment status, settings)

### PAYMENTS REQUIRED?
Y (Stripe for subscription billing)

### SUBSCRIPTION BILLING?
Y (monthly recurring subscription with 3 tiers)

### DASHBOARD OR REPORTING REQUIRED?
Y (main user interface is dashboard showing unpaid/overdue/paid invoice views)

### PDF OR DOCUMENT GENERATION REQUIRED?
Y (generate professional PDF invoices with custom branding)

### EXTERNAL API INTEGRATIONS REQUIRED FOR MVP?
- SendGrid or similar (transactional email for invoice delivery and reminders)
- Stripe (subscription billing and payment processing)

### BACKGROUND JOBS / AUTOMATION REQUIRED?
Y (scheduled job to send automated payment reminder emails based on due dates)

### ADMIN PANEL REQUIRED?
N (no admin interface in MVP, just user-facing dashboard)

### EXPECTED BUILD TIMELINE:
[X] 30 days (Tier 3: Full-stack FastAPI + React)

---

## Automatic Tier Classification

**Based on Q11 Architecture Declaration:**

| Criteria | Value | Impact |
|----------|-------|--------|
| Authentication Required | Y | **Forces Tier 2+** |
| Role-Based Access | N | - |
| Multi-Tenant | Y | **Forces Tier 3** |
| Persistent Database | Y | Required for Tier 2+ |
| Payments Required | Y | **Forces Tier 3** |
| Subscription Billing | Y | **Forces Tier 3** |
| Dashboard/Reporting | Y | **Forces Tier 2+** |
| PDF Generation | Y | **Forces Tier 3** |
| External APIs | 2 APIs | **Forces Tier 3** |
| Background Jobs | Y | **Forces Tier 3** |

**TIER ASSIGNMENT: 3 (Minimum)**

**RATIONALE:**
- Multi-tenant architecture requires strict data isolation and tenant middleware
- Subscription billing requires Stripe webhook handling and entitlement logic
- Two external API integrations (SendGrid for email, Stripe for payments)
- Background job scheduler for automated reminder emails
- PDF generation requires library integration and template rendering
- Authentication + dashboard reporting combination requires session management
- Database schema includes users, clients, invoices, line_items, payment_status tables

**TECH STACK REQUIREMENT:**
- **Backend:** FastAPI (Python) with SQLAlchemy ORM
  - Multi-tenant middleware for data isolation
  - Celery or APScheduler for background jobs
  - Stripe SDK for subscription management
  - ReportLab or WeasyPrint for PDF generation
  
- **Frontend:** React 18 with React Query for API state management
  - Tailwind CSS for styling
  - React Router for client-side routing
  - Form validation with React Hook Form

- **Database:** PostgreSQL (required for production, multi-tenant row-level security)

- **Hosting:** 
  - Backend: Railway or Render (needs persistent database)
  - Frontend: Vercel
  - Email: SendGrid (free tier allows 100 emails/day)

- **NOT ELIGIBLE FOR NOCODE/LOWCODE** due to:
  - Complex multi-tenant data isolation requirements
  - Custom PDF generation with branding
  - Background job scheduling for reminders
  - Stripe webhook handling for subscription events

**BUILD TIMELINE:**
30-45 days realistic for Tier 3 complexity with stated constraints (one person, nights and weekends)

**DEPLOYMENT CHECKLIST:**
- [ ] SendGrid account with verified sender domain
- [ ] Stripe account with webhook endpoint configured
- [ ] PostgreSQL database with multi-tenant schema
- [ ] Environment variables for API keys secured
- [ ] SSL certificate configured (automatic with Vercel/Railway)
- [ ] Terms of Service and Privacy Policy pages published
- [ ] Email templates tested (invoice delivery + reminders)
- [ ] PDF generation tested across different invoice sizes
- [ ] Background job scheduler tested for reminder timing accuracy

---

## Additional Technical Notes

### Database Schema (High-Level):
```
users (id, email, business_name, logo_url, created_at)
clients (id, user_id, name, email, phone, address)
invoices (id, user_id, client_id, invoice_number, amount, due_date, status, sent_at)
line_items (id, invoice_id, description, quantity, rate, line_total)
payment_reminders (id, invoice_id, reminder_type, scheduled_date, sent_at)
subscriptions (id, user_id, stripe_subscription_id, plan_tier, status)
```

### Key API Endpoints:
```
POST /api/auth/signup
POST /api/auth/login
GET /api/clients
POST /api/clients
GET /api/invoices?status=unpaid
POST /api/invoices
PATCH /api/invoices/{id}/mark-paid
POST /api/invoices/{id}/send
GET /api/invoices/{id}/pdf
POST /api/webhooks/stripe (subscription events)
```

### Estimated API Costs Per User Per Month:
- SendGrid: $0 (free tier covers 100 emails/day, avg user sends 20-30/month)
- Stripe: 2.9% + $0.30 per subscription charge = ~$0.73 on $29/month plan
- Hosting: $0-5 (Vercel free, Railway $5 hobby tier)
- **Total per user: ~$1-2/month operational cost**

### Margin Analysis:
- Starter ($15/month): ~$13/month profit per user after costs
- Professional ($29/month): ~$27/month profit per user after costs  
- Business ($49/month): ~$47/month profit per user after costs
- **Healthy margins support freemium growth model**

---

## End of Hero Answers Document

**Status:** Ready for KEITH (Pass 1) ingestion  
**Next Step:** Feed into FounderOps intake pipeline (Block A generation)  
**Expected Output:** 
- Block A with detailed BDR summary, tech stack selection, HLD, task list, and day-by-day schedule
- Block B with KPI definitions, testing scenarios, and deployment checklist
- Automatic tier validation confirming Tier 3 assignment
- Build timeline estimate: 30-45 days

**Risk Flags for JORGE/FRANCISCO:**
- Multi-tenant data isolation must be bulletproof (test thoroughly)
- PDF generation can be finicky with fonts/formatting (allocate buffer time)
- Email deliverability depends on proper SPF/DKIM setup (critical for product success)
- Background job reliability for reminders is core feature (cannot fail silently)
