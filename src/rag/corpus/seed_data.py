"""
RAG Corpus Seed Data
====================

Initial knowledge base documents for Smartacus agents.

4 Corpus:
- Rules: Amazon policies, compliance, SOP
- Ops: Sourcing, QC, incoterms, negotiation
- Templates: RFQ, follow-ups, clauses
- Memory: (populated by system during operation)
"""

from typing import List, Dict, Any

# =============================================================================
# RULES CORPUS - Amazon policies, compliance, SOP
# =============================================================================

RULES_DOCUMENTS = [
    {
        "title": "Amazon FBA Product Requirements",
        "domain": "compliance",
        "content": """
# Amazon FBA Product Requirements

## General Requirements

All products sold via FBA must comply with:

1. **Product Safety Standards**
   - Must meet applicable safety regulations (CE, FCC, etc.)
   - No recalled or prohibited products
   - Proper labeling required

2. **Packaging Requirements**
   - Products must be properly packaged to prevent damage
   - Poly bags must have suffocation warnings if opening > 5"
   - Fragile items need "FRAGILE" labels

3. **Barcode Requirements**
   - Each unit needs a scannable barcode (UPC, EAN, or Amazon FNSKU)
   - FNSKU preferred for FBA
   - Barcode must be visible and scannable

## Category-Specific Requirements

### Electronics
- FCC certification required for devices that emit radio frequencies
- CE marking for EU sales
- Must include proper safety certifications

### Toys
- CPSC compliance required
- Age grading labels mandatory
- Small parts warnings for items with choking hazards

### Food & Grocery
- FDA registration required
- Expiration dates must be clearly visible
- Minimum 105 days shelf life remaining at check-in

## Prohibited Products

Never source or sell:
- Counterfeit or replica items
- Products violating intellectual property rights
- Hazardous materials (without proper certification)
- Recalled products
- Expired food/consumables
""",
        "expiry_days": 365,
        "confidence": 1.0,
    },
    {
        "title": "Amazon Listing Optimization Rules",
        "domain": "listing",
        "content": """
# Amazon Listing Optimization Best Practices

## Title Rules

1. **Character Limit**: 200 characters max (80 recommended for mobile)
2. **Format**: Brand + Model + Key Features + Size/Color
3. **Avoid**: ALL CAPS, promotional phrases, special characters

## Bullet Points

- Maximum 5 bullet points
- 500 characters each (200 recommended)
- Start with capital letter
- Focus on benefits, not just features
- Include keywords naturally

## Product Images

1. **Main Image Requirements**:
   - Pure white background (RGB 255,255,255)
   - Product fills 85% of frame
   - No text, logos, or watermarks
   - Minimum 1000x1000 pixels (1500x1500 recommended)

2. **Additional Images** (up to 8 total):
   - Lifestyle shots
   - Size/scale reference
   - Feature callouts
   - Package contents
   - Instructions if complex

## Backend Keywords

- 250 bytes limit
- No commas needed (space-separated)
- No brand names or ASINs
- No subjective claims
- Include misspellings and synonyms

## A+ Content

- Available to Brand Registry sellers
- Can increase conversion 3-10%
- Use comparison charts for variants
- Include lifestyle imagery
""",
        "expiry_days": 365,
        "confidence": 1.0,
    },
    {
        "title": "Amazon Pricing Strategy Rules",
        "domain": "pricing",
        "content": """
# Amazon Pricing Strategy

## FBA Fee Structure

### Fulfillment Fees (per unit)
- Small Standard: $3.22
- Large Standard: $3.86 - $6.85 (by weight)
- Small Oversize: $9.73+
- Large Oversize: $15.13+

### Storage Fees
- January-September: $0.87/cubic ft
- October-December: $2.40/cubic ft (peak)
- Aged inventory surcharge: 180+ days

## Pricing Guidelines

1. **Minimum Viable Price**
   - Formula: (COGS + Shipping + FBA Fees + Amazon Referral) / (1 - Target Margin)
   - Never price below total landed cost + 15% margin

2. **Competitive Positioning**
   - Within 2-5% of Buy Box price
   - Avoid race to bottom
   - Value differentiation > price wars

3. **Price Elasticity**
   - Test +/- 10% price changes
   - Monitor conversion rate impact
   - Track unit session percentage

## Buy Box Considerations

Factors affecting Buy Box win rate:
- Price (including shipping)
- Fulfillment method (FBA preferred)
- Seller metrics
- Stock availability
- Account health

## Margin Targets

| Category | Minimum Margin | Target Margin |
|----------|----------------|---------------|
| Electronics | 15% | 25%+ |
| Home & Kitchen | 20% | 35%+ |
| Sports & Outdoors | 25% | 40%+ |
| Toys | 20% | 30%+ |
""",
        "expiry_days": 180,
        "confidence": 0.95,
    },
]

# =============================================================================
# OPS CORPUS - Sourcing, QC, shipping, negotiation
# =============================================================================

OPS_DOCUMENTS = [
    {
        "title": "Alibaba Sourcing Best Practices",
        "domain": "sourcing",
        "content": """
# Alibaba Sourcing Guide

## Finding Suppliers

### Search Strategy
1. Use English product keywords
2. Add "manufacturer" or "factory" to filter traders
3. Check "Trade Assurance" filter
4. Minimum 3 years on Alibaba
5. Verified supplier badge preferred

### Red Flags
- Price too good to be true (likely bait & switch)
- No product photos of actual factory
- Refuses video call
- No Trade Assurance
- Generic product images from other sellers
- Pushes for Western Union or direct bank transfer

### Green Flags
- Factory photos and videos
- Clear communication
- Reasonable MOQ negotiation
- Accepts Trade Assurance
- Provides certifications proactively
- References available

## Due Diligence Checklist

Before ordering:
- [ ] Verify business license
- [ ] Check Alibaba seller history
- [ ] Request and verify certifications
- [ ] Ask for customer references
- [ ] Video call to see factory
- [ ] Request samples before bulk order
- [ ] Confirm Trade Assurance terms

## Communication Tips

1. Be professional but friendly
2. Don't show desperation
3. Mention potential for repeat orders
4. Ask detailed questions
5. Request photos of YOUR production
6. Get everything in writing
""",
        "expiry_days": 365,
        "confidence": 1.0,
    },
    {
        "title": "Quality Control Checklist",
        "domain": "qc",
        "content": """
# Quality Control for Amazon FBA Products

## Pre-Production QC

Before mass production:
1. Approve golden sample
2. Confirm materials specification
3. Verify packaging design
4. Check certifications
5. Review production timeline

## During Production Inspection (DPI)

At 20-30% completion:
- Raw materials check
- Production process verification
- Early defect detection
- Timeline confirmation

## Pre-Shipment Inspection (PSI)

Standard: AQL 2.5 (Critical: 0, Major: 2.5, Minor: 4.0)

### Visual Inspection
- No visible defects
- Correct colors and dimensions
- Proper finishing
- Labels correct and secure

### Functional Testing
- All functions work as specified
- Durability test (if applicable)
- Safety compliance

### Packaging Check
- Correct packaging materials
- Proper labeling (FNSKU, etc.)
- Sufficient protection
- Correct quantity

## Common Defect Categories

**Critical (0 tolerance)**
- Safety hazards
- Complete functionality failure
- Wrong product

**Major**
- Affects functionality
- Visible defects
- Missing components

**Minor**
- Cosmetic imperfections
- Slight color variations
- Minor scratches (hidden areas)

## Third-Party Inspection Services

Recommended:
- QIMA (formerly AsiaInspection)
- Bureau Veritas
- SGS
- Intertek

Cost: $300-500 per inspection
""",
        "expiry_days": 365,
        "confidence": 1.0,
    },
    {
        "title": "International Shipping Terms (Incoterms)",
        "domain": "shipping",
        "content": """
# Incoterms for Amazon FBA Sourcing

## Common Terms

### EXW (Ex Works)
- Seller responsibility ends at factory door
- Buyer handles ALL shipping
- Lowest price, highest buyer risk
- **Not recommended for beginners**

### FOB (Free on Board)
- Seller delivers to port, loads on ship
- Most common for China sourcing
- Buyer pays sea freight + insurance
- **Recommended starting point**

### CIF (Cost, Insurance, Freight)
- Seller pays shipping to destination port
- Seller provides cargo insurance
- Buyer handles customs + local delivery
- Easier to budget total cost

### DDP (Delivered Duty Paid)
- Seller handles everything to your door
- Highest price, lowest buyer risk
- Includes customs clearance
- **Best for beginners** (if offered)

## Cost Comparison Example (China to US)

For a 20ft container (~$25,000 goods):

| Incoterm | Approx Cost | Seller Handles |
|----------|-------------|----------------|
| EXW | +$0 | Nothing |
| FOB | +$200-500 | Export customs, port delivery |
| CIF | +$3,000-5,000 | + Sea freight + insurance |
| DDP | +$5,000-8,000 | Everything |

## Tips

1. **Always get FOB minimum** - EXW is too risky
2. **Compare CIF vs FOB + own freight** - Sometimes CIF is cheaper
3. **For first orders, consider DDP** - Simplicity worth premium
4. **Insurance is mandatory** - Either seller or buyer must cover
5. **Confirm port** - FOB Shenzhen vs FOB Shanghai affects cost
""",
        "expiry_days": 365,
        "confidence": 1.0,
    },
    {
        "title": "Supplier Negotiation Tactics",
        "domain": "negotiation",
        "content": """
# Negotiation Strategies for Chinese Suppliers

## Mindset

1. **Build relationship first** - "Guanxi" matters
2. **Never show desperation** - They can smell urgency
3. **Have BATNA ready** - Best Alternative to Negotiated Agreement
4. **Win-win mentality** - Squeeze too hard = quality suffers

## What's Negotiable

- Unit price (5-15% typically possible)
- MOQ (Minimum Order Quantity)
- Payment terms (30/70 vs 50/50)
- Lead time
- Packaging upgrades
- Shipping terms
- Sample costs
- Warranty/defect policy

## Tactics That Work

### 1. Volume Commitment
"If quality is good, we plan to order 10,000 units/month"

### 2. Competitor Reference
"Another supplier quoted $X, but we prefer working with you"

### 3. Long-term Relationship
"We're looking for a partner for 3-5 years, not just one order"

### 4. Bundle Negotiation
"If you include shipping, we'll accept higher MOQ"

### 5. Quick Payment Leverage
"Can you reduce 5% if we pay 100% upfront?"

### 6. Order Timing
"We can be flexible on delivery if you can reduce price"

## What NOT to Do

- Don't insult their initial price
- Don't lie about competitor quotes
- Don't threaten to walk unless you mean it
- Don't negotiate via email only (call/video better)
- Don't forget cultural differences
- Don't skip the relationship-building phase

## Sample Negotiation Scripts

**Opening:**
"Thank you for your quote. We're very interested in working together. We see potential for a long-term partnership. To move forward, we need to discuss pricing to ensure this works for both of us."

**Price Push:**
"Your quality looks good, but to hit our target retail price and margins, we need to reach $X per unit. What can we do together to get there?"

**Closing:**
"If you can confirm $X FOB with the payment terms we discussed, we can proceed with a purchase order this week."
""",
        "expiry_days": 365,
        "confidence": 1.0,
    },
]

# =============================================================================
# TEMPLATES CORPUS - RFQ, messages, contracts
# =============================================================================

TEMPLATES_DOCUMENTS = [
    {
        "title": "Initial Supplier Contact Template",
        "domain": "sourcing",
        "content": """
# First Contact Message Template

## Template (English - for Chinese suppliers)

---

Subject: Product Inquiry - [Product Name] - Potential Long-term Partnership

Hello,

My name is [Your Name] and I represent [Company Name], an e-commerce company based in [Country].

We are looking for a reliable manufacturing partner for [Product Description]. We found your company on Alibaba and are impressed by your product range.

**Our Requirements:**
- Product: [Specific product name/description]
- Estimated quantity: [X] units for first order
- Target price: $[X] per unit (FOB)
- Quality requirements: [Any certifications needed]
- Destination: USA (Amazon FBA warehouse)

**Questions:**
1. What is your MOQ for this product?
2. What is your best price for [quantity] units FOB [port]?
3. What is your production lead time?
4. Can you provide product certifications (CE, FCC, etc.)?
5. Do you accept Trade Assurance?

If you are interested, please send:
- Product specification sheet
- Price list for different quantities
- Photos of your factory
- Any certifications

We are looking for a long-term partner and expect to grow orders significantly if quality meets our standards.

Best regards,
[Your Name]
[Company Name]
[Email]
[Phone/WhatsApp]

---

## Key Points

- Be professional but friendly
- Mention long-term potential
- Ask specific questions
- Request documentation upfront
- Provide clear requirements
""",
        "expiry_days": None,
        "confidence": 1.0,
    },
    {
        "title": "Sample Request Template",
        "domain": "sourcing",
        "content": """
# Sample Request Message Template

## Template

---

Subject: Sample Request - [Product Name] - Order #[Reference]

Hello [Supplier Name],

Thank you for the quotation. We would like to proceed with samples before placing a bulk order.

**Sample Request:**
- Product: [Exact product description]
- Quantity: [2-5 samples]
- Specifications: [Color, size, any customization]

**Please confirm:**
1. Sample cost per unit
2. Shipping cost to [Your Address]
3. Estimated delivery time
4. Payment method for samples

We understand samples are charged separately from bulk orders. Once we receive and approve the samples, we plan to place an initial order of [X] units.

Please send PayPal/Trade Assurance invoice for the samples.

Best regards,
[Your Name]

---

## Follow-up (if no response in 3 days)

---

Hello [Supplier Name],

I wanted to follow up on my sample request from [date]. Are you able to provide samples for evaluation?

Please let me know if you need any additional information from our side.

Thank you,
[Your Name]

---
""",
        "expiry_days": None,
        "confidence": 1.0,
    },
    {
        "title": "Price Negotiation Templates",
        "domain": "negotiation",
        "content": """
# Price Negotiation Message Templates

## Initial Counter-Offer

---

Hello [Supplier Name],

Thank you for your quote of $[X] per unit.

After reviewing our costs and market analysis, we need to reach $[Target Price] per unit to make this work for both of us.

Here's our situation:
- Amazon selling price: $[X]
- Amazon fees (FBA + referral): ~35%
- Shipping and import costs: ~$[X]/unit
- Our required margin: [X]%

At $[Their Price], our margins don't work. At $[Your Target], we can proceed with [quantity] units and plan for monthly reorders.

Is there any way to reach $[Target Price]? We're flexible on:
- Payment terms (can pay more upfront)
- Order quantity (can increase if price is right)
- Delivery timeline (not urgent)

Looking forward to finding a solution together.

Best regards,
[Your Name]

---

## Response to Rejection

---

Hello [Supplier Name],

Thank you for your response. I understand $[Target] is difficult.

What is the absolute best price you can offer for:
- [Quantity 1] units: $?
- [Quantity 2] units: $?
- [Quantity 3] units: $?

We're also open to discussing:
- Different materials that might reduce cost
- Simplified packaging
- Longer production time

Let's find a middle ground that works for both of us.

Best regards,
[Your Name]

---

## Final Acceptance

---

Hello [Supplier Name],

Thank you for working with us on the pricing.

We accept $[Final Price] per unit for [Quantity] units FOB [Port].

Please confirm:
1. Final unit price: $[X]
2. Total order value: $[X]
3. Payment terms: [30% deposit, 70% before shipping]
4. Production time: [X] days
5. Shipping port: [Port name]

Once confirmed, please send Proforma Invoice via Trade Assurance.

Looking forward to a successful partnership!

Best regards,
[Your Name]

---
""",
        "expiry_days": None,
        "confidence": 1.0,
    },
    {
        "title": "Quality Issue Complaint Template",
        "domain": "qc",
        "content": """
# Quality Issue Communication Templates

## Initial Report

---

Subject: URGENT - Quality Issues - Order #[Reference]

Hello [Supplier Name],

We have received our order and found quality issues that need immediate attention.

**Order Details:**
- Order number: [Reference]
- Product: [Description]
- Quantity ordered: [X] units
- Quantity received: [X] units

**Issues Found:**
1. [Issue 1 - e.g., "20% of units have scratched surfaces"]
2. [Issue 2 - e.g., "15 units missing components"]
3. [Issue 3 - e.g., "Packaging damaged on 30 units"]

**Evidence:**
- Photos attached: [List]
- Video: [Link if applicable]
- Inspection report: [Attached if available]

**Impact:**
- [X] units are unsellable
- Estimated loss: $[X]

**Requested Resolution:**
- Replacement of defective units
- Refund for unsellable inventory
- Explanation of how this will be prevented

Please respond within 24 hours with your proposed solution.

Best regards,
[Your Name]

---

## Follow-up (Escalation)

---

Subject: RE: Quality Issues - Escalation Required - Order #[Reference]

Hello,

I have not received a satisfactory response to our quality complaint from [date].

To summarize:
- [X] defective units received
- Loss of $[X]
- Original request: [replacement/refund]

If we cannot resolve this within 48 hours, we will:
1. Open a Trade Assurance dispute
2. Leave detailed review on Alibaba
3. Seek resolution through other means

We prefer to resolve this directly and maintain our business relationship. Please escalate to management if needed.

Awaiting your urgent response.

Best regards,
[Your Name]

---
""",
        "expiry_days": None,
        "confidence": 1.0,
    },
]


def get_all_seed_documents() -> List[Dict[str, Any]]:
    """
    Get all seed documents for initial corpus ingestion.

    Returns:
        List of document dictionaries ready for ingestion
    """
    documents = []

    # Add rules documents
    for doc in RULES_DOCUMENTS:
        documents.append({
            **doc,
            "doc_type": "rules",
            "source": "seed_data",
            "source_type": "manual",
        })

    # Add ops documents
    for doc in OPS_DOCUMENTS:
        documents.append({
            **doc,
            "doc_type": "ops",
            "source": "seed_data",
            "source_type": "manual",
        })

    # Add template documents
    for doc in TEMPLATES_DOCUMENTS:
        documents.append({
            **doc,
            "doc_type": "templates",
            "source": "seed_data",
            "source_type": "manual",
        })

    return documents
