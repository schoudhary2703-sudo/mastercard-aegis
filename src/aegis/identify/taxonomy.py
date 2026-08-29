"""Evidence-backed breadth taxonomy outside the three simulator contracts.

The shared ``AttackFamily`` enum stays deliberately fixed at three.  Entries
marked ``IDENTIFIED_ONLY`` therefore remain research records: they do not
silently acquire a blueprint, generator, or detector result.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from aegis.shared.base import AegisModel


class ImplementationStatus(str, Enum):
    IDENTIFIED_ONLY = "IDENTIFIED_ONLY"
    DEEP_SIMULATED = "DEEP_SIMULATED"


class SimulationReadiness(str, Enum):
    READY = "READY"
    CANDIDATE = "CANDIDATE"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class EvidenceSource(AegisModel):
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)


class FraudScenario(AegisModel):
    id: str = Field(..., min_length=1, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    channels: list[str] = Field(..., min_length=1)
    rails: list[str] = Field(..., min_length=1)
    genai_abuse_mechanism: str = Field(..., min_length=1)
    payment_system_surface: list[str] = Field(..., min_length=1)
    observable_signals: list[str] = Field(..., min_length=1)
    plausibility_evidence_note: str = Field(..., min_length=1)
    evidence_sources: list[EvidenceSource] = Field(..., min_length=1)
    simulation_readiness: SimulationReadiness
    implementation_status: ImplementationStatus

    @model_validator(mode="after")
    def _deep_simulation_is_ready(self) -> FraudScenario:
        if (
            self.implementation_status is ImplementationStatus.DEEP_SIMULATED
            and self.simulation_readiness is not SimulationReadiness.READY
        ):
            raise ValueError("a deeply simulated scenario must be READY")
        return self


class TaxonomySummary(AegisModel):
    total_attacks_identified: int = Field(..., ge=0)
    categories_represented: list[str]
    channels_represented: list[str]
    rails_represented: list[str]
    deeply_simulated: int = Field(..., ge=0)


class FraudTaxonomy(AegisModel):
    taxonomy_version: str = "mastercard-alignment-v1"
    scope_note: str = (
        "Breadth catalog only. IDENTIFIED_ONLY entries have no AEGIS generator or reported "
        "detector performance; only the existing three AttackFamily values are deeply simulated."
    )
    scenarios: list[FraudScenario]
    summary: TaxonomySummary


MC_AI_REPORT = EvidenceSource(
    title="Mastercard: Securing the digital ecosystem with AI",
    url=(
        "https://www.mastercard.com/content/dam/mccom/shared/news-and-trends/insights/"
        "2024/securing-the-digital-ecosystem-with-ai/pdf/"
        "securing-the-digital-ecosystem-with-ai.pdf"
    ),
)
MC_PAYMENT_AI_SURVEY = EvidenceSource(
    title="Mastercard: On the right side of AI — payment fraud prevention",
    url=(
        "https://www.mastercard.com/content/dam/mccom/shared/news-and-trends/insights/"
        "2025/one-the-right-side-of-ai/"
        "the-right-side-of-ai-shaping-the-future-of-payment-fraud-prevention.pdf"
    ),
)
MC_A2A_REPORT = EvidenceSource(
    title="Mastercard: Uniting against account-to-account fraud",
    url=(
        "https://www.mastercard.com/content/dam/mccom/shared/business/b2b/reports/"
        "mc_rtp_financial_crime_whitepaper_updated-march-2025.pdf"
    ),
)
MC_MERCHANT_REPORT = EvidenceSource(
    title="Mastercard: Combating scams and fraudulent merchants",
    url=(
        "https://www.mastercard.com/content/dam/mccom/shared/news-and-trends/insights/"
        "2025/scam-websites/Building%20digital%20trust%20by%20combating%20scams%20and%20"
        "fraudulent%20merchants%20(May%202025).pdf"
    ),
)
MC_MERCHANT_TRUST = EvidenceSource(
    title="Mastercard: How to stop the scammers behind the storefronts",
    url=(
        "https://www.mastercard.com/global/en/news-and-trends/stories/2026/"
        "merchant-trust-services.html"
    ),
)
MC_CYBER_FRAUD = EvidenceSource(
    title="Mastercard: How banks prevent cyberfraud with threat intelligence",
    url=(
        "https://www.mastercard.com/global/en/news-and-trends/Insights/2025/"
        "how-banks-prevent-cyber-fraud-with-improved-threat-intelligence.html"
    ),
)
INTERNAL_ADAPTIVE = EvidenceSource(
    title="AEGIS: Adaptive detector evasion research and simulator limits",
    url="docs/ADAPTIVE_DETECTOR_EVASION.md",
)


SCENARIOS: tuple[FraudScenario, ...] = (
    FraudScenario(
        id="synthetic-identity-bustout",
        name="Synthetic identity trust build and bust-out",
        category="identity-and-onboarding",
        channels=["mobile-banking", "digital-onboarding"],
        rails=["account-to-account", "credit"],
        genai_abuse_mechanism=(
            "Synthetic imagery, forged identity documents, biometric spoofing, and large-scale "
            "assembly of blended identity profiles make onboarding abuse cheaper."
        ),
        payment_system_surface=["account onboarding", "KYC", "credit line", "transfers"],
        observable_signals=[
            "new-account tenure",
            "long benign-looking warm-up",
            "abrupt amount transition",
            "short drain window",
        ],
        plausibility_evidence_note=(
            "Mastercard describes GenAI-assisted onboarding artifacts, dormancy, credit building, "
            "and eventual bust-out. AEGIS implements only a PaySim-derived behavioral analogue."
        ),
        evidence_sources=[MC_AI_REPORT],
        simulation_readiness=SimulationReadiness.READY,
        implementation_status=ImplementationStatus.DEEP_SIMULATED,
    ),
    FraudScenario(
        id="mule-network-structuring",
        name="Mule network micro-structuring and layering",
        category="money-movement-and-laundering",
        channels=["mobile-banking", "online-banking"],
        rails=["real-time-account-to-account", "cash-out"],
        genai_abuse_mechanism=(
            "No criminal GenAI mechanism is required or claimed by the cited evidence. In AEGIS, "
            "GenAI may only propose bounded simulator parameters; it does not create mule rows."
        ),
        payment_system_surface=["inbound transfers", "mule accounts", "layering", "cash-out"],
        observable_signals=[
            "fan-out and fan-in",
            "rapid pass-through",
            "many counterparties",
            "amounts split across linked accounts",
        ],
        plausibility_evidence_note=(
            "Mastercard explicitly documents micro-structuring and mule-account networks on RTP "
            "rails. The GenAI recruitment link is a bounded hypothesis, not a measured result."
        ),
        evidence_sources=[MC_A2A_REPORT],
        simulation_readiness=SimulationReadiness.READY,
        implementation_status=ImplementationStatus.DEEP_SIMULATED,
    ),
    FraudScenario(
        id="adaptive-detector-evasion",
        name="Feedback-guided detector evasion",
        category="adversarial-optimization",
        channels=["mobile-banking"],
        rails=["account-to-account", "cash-out"],
        genai_abuse_mechanism=(
            "A reasoning model can prioritize bounded parameter variants from observed outcomes; "
            "the deterministic simulator, never GenAI, produces transaction rows."
        ),
        payment_system_surface=["authorization risk scoring", "transaction monitoring"],
        observable_signals=[
            "amount jitter",
            "inter-event pacing",
            "destination diversity",
            "risk scores below a fixed action threshold",
        ],
        plausibility_evidence_note=(
            "This is an AEGIS synthetic-only adversarial benchmark. It demonstrates a bounded "
            "research loop and does not claim real-world probing access or evasion capability."
        ),
        evidence_sources=[INTERNAL_ADAPTIVE],
        simulation_readiness=SimulationReadiness.READY,
        implementation_status=ImplementationStatus.DEEP_SIMULATED,
    ),
    FraudScenario(
        id="deepfake-impersonation-app-fraud",
        name="Deepfake impersonation leading to authorized push payment fraud",
        category="scams-and-social-engineering",
        channels=["voice-call", "video-call", "messaging", "social-media"],
        rails=["real-time-account-to-account", "p2p"],
        genai_abuse_mechanism=(
            "Voice cloning and deepfake video impersonate a trusted person or authority and induce "
            "the victim to authorize an otherwise valid payment."
        ),
        payment_system_surface=["payment initiation", "confirmation of payee", "beneficiary risk"],
        observable_signals=[
            "new beneficiary",
            "unusual device interaction",
            "high-risk recipient",
            "atypical amount or urgency",
        ],
        plausibility_evidence_note=(
            "Mastercard documents AI-simulated voices and deepfake endorsements as APP-fraud "
            "enablers. PaySim lacks victim-contact and authorization-intent evidence."
        ),
        evidence_sources=[MC_A2A_REPORT, MC_AI_REPORT],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="genai-phishing-account-takeover",
        name="GenAI-scaled phishing followed by account takeover",
        category="account-compromise",
        channels=["email", "sms", "web", "mobile-banking"],
        rails=["account-to-account", "card"],
        genai_abuse_mechanism=(
            "GenAI produces convincing, targeted phishing messages and sites at scale; stolen "
            "credentials are then used to control a legitimate account."
        ),
        payment_system_surface=["login", "device binding", "beneficiary setup", "authorization"],
        observable_signals=[
            "new device or location",
            "credential reset",
            "new beneficiary",
            "rapid post-login drain",
        ],
        plausibility_evidence_note=(
            "Mastercard links GenAI-scaled phishing to account takeover and unauthorized money "
            "movement. A transaction-only simulator cannot represent the compromise stage."
        ),
        evidence_sources=[MC_AI_REPORT, MC_CYBER_FRAUD],
        simulation_readiness=SimulationReadiness.CANDIDATE,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="scam-merchant-purchase-fraud",
        name="GenAI-built scam merchant and goods-not-delivered purchase fraud",
        category="merchant-and-ecommerce",
        channels=["web", "mobile-commerce", "social-media"],
        rails=["card-not-present", "digital-wallet"],
        genai_abuse_mechanism=(
            "Professional-looking storefronts, ads, testimonials, and deepfake endorsements are "
            "generated quickly to make a fake merchant appear legitimate."
        ),
        payment_system_surface=["merchant onboarding", "authorization", "clearing", "disputes"],
        observable_signals=[
            "very young merchant or domain",
            "low-value purchase concentration",
            "descriptor churn",
            "goods-not-delivered disputes",
        ],
        plausibility_evidence_note=(
            "Mastercard describes AI-generated scam storefronts that take card payments, fail to "
            "deliver goods, and may harvest credentials. PaySim has no merchant lifecycle."
        ),
        evidence_sources=[MC_MERCHANT_REPORT, MC_MERCHANT_TRUST],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="merchant-account-takeover-redirection",
        name="Merchant account takeover and settlement redirection",
        category="merchant-and-ecommerce",
        channels=["merchant-portal", "email", "web"],
        rails=["merchant-acquiring", "bank-transfer"],
        genai_abuse_mechanism=(
            "GenAI-enhanced phishing can acquire merchant credentials; the attacker then changes "
            "routing details or intercepts customer payments."
        ),
        payment_system_surface=["merchant portal", "settlement instructions", "merchant profile"],
        observable_signals=[
            "routing-detail change",
            "new administrative device",
            "settlement destination change",
            "inherited merchant volume followed by anomalies",
        ],
        plausibility_evidence_note=(
            "Mastercard documents takeover of reputable merchant accounts followed by routing "
            "changes and payment interception. Settlement state is absent from PaySim."
        ),
        evidence_sources=[MC_MERCHANT_REPORT],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="payment-credential-harvesting-cnp",
        name="Payment-credential harvesting followed by card-not-present fraud",
        category="card-and-credential-fraud",
        channels=["phishing-site", "compromised-checkout", "ecommerce"],
        rails=["card-not-present"],
        genai_abuse_mechanism=(
            "GenAI improves phishing copy and fake-site quality; harvested card details are used "
            "for later unauthorized e-commerce purchases."
        ),
        payment_system_surface=["checkout page", "card authorization", "merchant dispute"],
        observable_signals=[
            "new merchant-device combination",
            "cross-merchant credential reuse",
            "post-authorization chargebacks",
            "skimming infrastructure link",
        ],
        plausibility_evidence_note=(
            "Mastercard describes GenAI phishing, checkout-page skimming, credential harvesting, "
            "and subsequent fraudulent card purchases. PaySim is not a card-authorization corpus."
        ),
        evidence_sources=[MC_AI_REPORT, MC_MERCHANT_REPORT],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="card-enumeration-testing",
        name="BIN enumeration and card testing",
        category="card-and-credential-fraud",
        channels=["ecommerce", "merchant-test-interface"],
        rails=["card-not-present"],
        genai_abuse_mechanism=(
            "The evidenced enabler is automation rather than GenAI. GenAI may support upstream "
            "fake-merchant content, but this taxonomy does not claim it generates valid cards."
        ),
        payment_system_surface=["authorization endpoint", "merchant identifier", "card vault"],
        observable_signals=[
            "high decline ratio",
            "many cards per merchant or device",
            "small authorization amounts",
            "rapid systematic attempts",
        ],
        plausibility_evidence_note=(
            "Mastercard explicitly documents automated BIN enumeration and bot-driven card "
            "testing. The limited GenAI role is stated to avoid overstating the evidence."
        ),
        evidence_sources=[MC_AI_REPORT, MC_CYBER_FRAUD],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="bnpl-synthetic-account-abuse",
        name="Unauthorized BNPL account and transaction abuse",
        category="identity-and-onboarding",
        channels=["digital-onboarding", "ecommerce"],
        rails=["buy-now-pay-later", "card"],
        genai_abuse_mechanism=(
            "Mastercard documents GenAI-assisted identity artifacts and BNPL abuse separately; "
            "this catalog does not assert a BNPL-specific GenAI mechanism without direct evidence."
        ),
        payment_system_surface=["BNPL onboarding", "credit decision", "merchant checkout"],
        observable_signals=[
            "identity inconsistencies",
            "new-account velocity",
            "device reuse across applicants",
            "early delinquency or bust-out",
        ],
        plausibility_evidence_note=(
            "Mastercard separately identifies BNPL abuse as a growing payment risk and GenAI-made "
            "identity artifacts as an onboarding risk; AEGIS does not claim a measured causal link."
        ),
        evidence_sources=[MC_PAYMENT_AI_SURVEY, MC_AI_REPORT],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="synthetic-refund-chargeback-misuse",
        name="Synthetic-customer refund and chargeback misuse",
        category="first-party-and-dispute-abuse",
        channels=["ecommerce", "customer-service"],
        rails=["card", "refund", "chargeback"],
        genai_abuse_mechanism=(
            "Synthetic identity use is documented, but a GenAI-specific refund/dispute mechanism "
            "is not established by the cited evidence and is therefore not claimed."
        ),
        payment_system_surface=["refund initiation", "chargeback", "merchant account"],
        observable_signals=[
            "refunds to linked identities",
            "merchant-customer ownership overlap",
            "repeat dispute patterns",
            "funds routed across related accounts",
        ],
        plausibility_evidence_note=(
            "Mastercard documents fraudulent merchants acting as their own customers, issuing "
            "unauthorized refunds, and using synthetic identities in disputes and fund funnels."
        ),
        evidence_sources=[MC_MERCHANT_REPORT],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="cross-border-ecommerce-scam",
        name="Cross-border multi-channel e-commerce scam",
        category="merchant-and-ecommerce",
        channels=["social-media", "mobile-web", "ecommerce"],
        rails=["cross-border-card", "payment-service-provider"],
        genai_abuse_mechanism=(
            "GenAI scales localized ads, brand impersonation, and credible storefront content "
            "across markets and languages."
        ),
        payment_system_surface=["merchant onboarding", "cross-border authorization", "PSP routing"],
        observable_signals=[
            "young domains across jurisdictions",
            "shared infrastructure",
            "merchant descriptor churn",
            "cross-border dispute clusters",
        ],
        plausibility_evidence_note=(
            "Mastercard documents social-ad-to-storefront-to-PSP paths and cross-border scam-site "
            "networks; GenAI storefront scaling is also documented."
        ),
        evidence_sources=[MC_MERCHANT_REPORT, MC_MERCHANT_TRUST],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="me-to-me-a2a-consolidation-scam",
        name="Me-to-me account consolidation scam",
        category="scams-and-social-engineering",
        channels=["voice-call", "messaging", "mobile-banking"],
        rails=["real-time-account-to-account"],
        genai_abuse_mechanism=(
            "Mastercard documents GenAI-enabled phishing/voice impersonation and me-to-me scams "
            "separately; their use together is a research hypothesis, not a measured claim."
        ),
        payment_system_surface=["beneficiary setup", "cross-bank transfer", "recipient account"],
        observable_signals=[
            "multiple own-account inflows",
            "rapid consolidation",
            "new payee",
            "immediate onward movement",
        ],
        plausibility_evidence_note=(
            "Mastercard documents me-to-me fraud and separately documents GenAI voice/phishing "
            "impersonation. Cross-institution identity linkage is unavailable in PaySim."
        ),
        evidence_sources=[MC_AI_REPORT, MC_A2A_REPORT],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
    FraudScenario(
        id="genai-bec-invoice-redirection",
        name="GenAI-enhanced BEC and invoice redirection",
        category="scams-and-social-engineering",
        channels=["email", "messaging", "voice-call"],
        rails=["business-account-to-account", "cross-border-transfer"],
        genai_abuse_mechanism=(
            "Targeted executive or supplier impersonation, polished invoice text, and voice clones "
            "make fraudulent payment-instruction changes more credible."
        ),
        payment_system_surface=[
            "invoice workflow",
            "beneficiary change",
            "corporate payment approval",
        ],
        observable_signals=[
            "new supplier bank details",
            "unusual approver sequence",
            "first payment to beneficiary",
            "amount or geography deviation",
        ],
        plausibility_evidence_note=(
            "Mastercard identifies BEC/CEO impersonation and GenAI-targeted schemes. PaySim lacks "
            "invoice, approver, and corporate-identity context."
        ),
        evidence_sources=[MC_AI_REPORT, MC_PAYMENT_AI_SURVEY],
        simulation_readiness=SimulationReadiness.RESEARCH_ONLY,
        implementation_status=ImplementationStatus.IDENTIFIED_ONLY,
    ),
)


def build_fraud_taxonomy() -> FraudTaxonomy:
    scenarios = list(SCENARIOS)
    return FraudTaxonomy(
        scenarios=scenarios,
        summary=TaxonomySummary(
            total_attacks_identified=len(scenarios),
            categories_represented=sorted({item.category for item in scenarios}),
            channels_represented=sorted(
                {channel for item in scenarios for channel in item.channels}
            ),
            rails_represented=sorted({rail for item in scenarios for rail in item.rails}),
            deeply_simulated=sum(
                item.implementation_status is ImplementationStatus.DEEP_SIMULATED
                for item in scenarios
            ),
        ),
    )


__all__ = [
    "FraudScenario",
    "FraudTaxonomy",
    "ImplementationStatus",
    "SimulationReadiness",
    "TaxonomySummary",
    "build_fraud_taxonomy",
]
