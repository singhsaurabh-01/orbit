"""Prep notes service - suggest what to bring based on errand purpose."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PrepNote:
    """Preparation notes for an errand."""
    documents: list[str]  # Required documents
    items: list[str]  # Items to bring
    tips: list[str]  # Helpful tips
    crowdedness_hint: Optional[str] = None  # e.g., "Usually busy at lunchtime"


# Rule-based suggestions keyed by keywords in purpose
PURPOSE_RULES = {
    # DMV-related
    "dmv": {
        "documents": [
            "Photo ID (driver's license or passport)",
            "Proof of residency (utility bill, bank statement)",
            "Social Security card or proof of SSN",
        ],
        "items": ["Cash or card for fees", "Pen"],
        "tips": [
            "Check DMV website for specific requirements",
            "Consider making an appointment online",
        ],
        "crowdedness": "Typically busiest 11am-2pm; try early morning or late afternoon",
    },
    "license renewal": {
        "documents": [
            "Current driver's license",
            "Proof of residency (utility bill, bank statement)",
        ],
        "items": ["Cash or card for renewal fee"],
        "tips": ["Check if you're eligible for online renewal first"],
        "crowdedness": "Typically busiest 11am-2pm",
    },
    "registration": {
        "documents": [
            "Current registration card",
            "Proof of insurance",
            "Photo ID",
        ],
        "items": ["Payment for registration fee"],
        "tips": ["Check online renewal option first"],
    },
    # Post office
    "post office": {
        "documents": [],
        "items": ["Package ready to ship", "Address written down", "Payment method"],
        "tips": ["Check weight limits and prohibited items online"],
        "crowdedness": "Busiest around lunch hour and end of month",
    },
    "mail": {
        "items": ["Letters/packages", "Stamps if needed", "Addresses written down"],
        "tips": [],
    },
    "package": {
        "items": ["Package securely packed", "Recipient address", "Return address label"],
        "tips": ["Compare shipping rates online beforehand"],
    },
    # Banking
    "bank": {
        "documents": ["Photo ID", "Debit card or account number"],
        "items": ["Deposit items if applicable"],
        "tips": ["Check if transaction can be done via app"],
        "crowdedness": "Busiest first and last days of month",
    },
    "deposit": {
        "documents": ["Photo ID"],
        "items": ["Checks to deposit", "Deposit slip (optional)"],
        "tips": ["Mobile deposit via app is usually faster"],
    },
    "notary": {
        "documents": [
            "Photo ID (unexpired government-issued)",
            "Document(s) to be notarized (unsigned)",
        ],
        "items": ["Pen (black ink preferred)"],
        "tips": ["Call ahead to confirm notary availability"],
    },
    # Healthcare
    "doctor": {
        "documents": [
            "Insurance card",
            "Photo ID",
            "List of current medications",
        ],
        "items": ["Copay payment"],
        "tips": ["Arrive 15 min early for paperwork"],
    },
    "appointment": {
        "documents": ["Photo ID", "Insurance card if applicable"],
        "items": ["Confirmation number or email"],
        "tips": ["Arrive 10-15 minutes early"],
    },
    "pharmacy": {
        "documents": ["Prescription or doctor's name", "Insurance card"],
        "items": ["Payment method"],
        "tips": ["Check if prescription is ready before going"],
    },
    "prescription": {
        "documents": ["Insurance card", "Photo ID"],
        "items": ["Copay payment"],
        "tips": ["Call ahead to confirm it's ready"],
    },
    # Shopping
    "return": {
        "documents": ["Receipt or order confirmation"],
        "items": ["Item(s) to return", "Original packaging if possible", "Credit card used"],
        "tips": ["Check return policy deadline"],
    },
    "pickup": {
        "documents": ["Order confirmation or pickup code", "Photo ID"],
        "items": [],
        "tips": ["Check that order status says 'Ready for pickup'"],
    },
    "grocery": {
        "items": ["Shopping list", "Reusable bags", "Payment method"],
        "tips": ["Check store flyer for sales"],
        "crowdedness": "Busiest on weekends and evening rush",
    },
    # Government
    "passport": {
        "documents": [
            "Current passport (for renewal) or birth certificate (for new)",
            "Photo ID",
            "Passport photos (2x2 inches)",
            "Completed DS-11 or DS-82 form",
        ],
        "items": ["Check or money order for fees (no cash)"],
        "tips": ["Make appointment at USPS or passport agency"],
    },
    "court": {
        "documents": ["Summons or case number", "Photo ID", "Related paperwork"],
        "items": [],
        "tips": [
            "Arrive early for security screening",
            "No phones allowed in some courtrooms",
        ],
    },
    "vote": {
        "documents": ["Photo ID (check state requirements)", "Voter registration card (if required)"],
        "items": [],
        "tips": ["Check your polling location online"],
    },
    # Automotive
    "oil change": {
        "documents": [],
        "items": ["Vehicle owner's manual (for oil spec)"],
        "tips": ["Check for coupons online"],
    },
    "car wash": {
        "items": ["Payment method"],
        "tips": ["Remove valuables from cup holders"],
    },
    "mechanic": {
        "documents": [],
        "items": ["Description of problem written down"],
        "tips": ["Get estimate in writing before approving work"],
    },
    "inspection": {
        "documents": ["Vehicle registration", "Proof of insurance"],
        "items": ["Payment for inspection fee"],
        "tips": ["Check that lights, wipers, horn work beforehand"],
    },
    # Services
    "haircut": {
        "items": ["Payment method", "Photo of desired style (optional)"],
        "tips": ["Tip 15-20% for good service"],
    },
    "dry cleaning": {
        "documents": ["Pickup ticket/receipt"],
        "items": ["Items to drop off (check pockets)"],
        "tips": [],
    },
    "library": {
        "documents": ["Library card"],
        "items": ["Books to return"],
        "tips": ["Check online catalog before going"],
    },
    # Default fallback
    "errand": {
        "documents": ["Photo ID (if required)"],
        "items": ["Payment method"],
        "tips": [],
    },
}


def get_prep_notes(purpose: str, place_name: str = "") -> PrepNote:
    """
    Generate prep notes based on errand purpose and place.

    Args:
        purpose: Description of what user is doing (e.g., "license renewal")
        place_name: Name of the place (e.g., "DMV", "Target")

    Returns:
        PrepNote with suggestions
    """
    purpose_lower = purpose.lower() if purpose else ""
    place_lower = place_name.lower() if place_name else ""

    # Combine for matching
    combined = f"{purpose_lower} {place_lower}"

    documents = []
    items = []
    tips = []
    crowdedness = None

    # Find matching rules (can match multiple)
    matched_rules = []
    for keyword, rules in PURPOSE_RULES.items():
        if keyword in combined:
            matched_rules.append((keyword, rules))

    # Sort by keyword length (longer = more specific = higher priority)
    matched_rules.sort(key=lambda x: len(x[0]), reverse=True)

    # Aggregate from all matching rules (deduplicating)
    seen_docs = set()
    seen_items = set()
    seen_tips = set()

    for _, rules in matched_rules:
        for doc in rules.get("documents", []):
            if doc not in seen_docs:
                documents.append(doc)
                seen_docs.add(doc)
        for item in rules.get("items", []):
            if item not in seen_items:
                items.append(item)
                seen_items.add(item)
        for tip in rules.get("tips", []):
            if tip not in seen_tips:
                tips.append(tip)
                seen_tips.add(tip)
        if not crowdedness and rules.get("crowdedness"):
            crowdedness = rules["crowdedness"]

    # If nothing matched, use generic errand
    if not documents and not items and not tips:
        default = PURPOSE_RULES.get("errand", {})
        documents = default.get("documents", [])
        items = default.get("items", [])
        tips = default.get("tips", [])

    return PrepNote(
        documents=documents,
        items=items,
        tips=tips,
        crowdedness_hint=crowdedness,
    )


def format_prep_notes(prep: PrepNote) -> str:
    """Format prep notes as markdown string."""
    lines = []

    if prep.documents:
        lines.append("**Documents to bring:**")
        for doc in prep.documents:
            lines.append(f"- {doc}")
        lines.append("")

    if prep.items:
        lines.append("**Items to bring:**")
        for item in prep.items:
            lines.append(f"- {item}")
        lines.append("")

    if prep.tips:
        lines.append("**Tips:**")
        for tip in prep.tips:
            lines.append(f"- {tip}")
        lines.append("")

    if prep.crowdedness_hint:
        lines.append(f"**Crowdedness:** {prep.crowdedness_hint}")

    return "\n".join(lines) if lines else "No specific preparation needed."
