"""
Domain Registry and Intelligent Router for Tarjoman Universal Translation Engine.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from tarjoman.core.contracts import DomainProfile, DomainType

DEFAULT_REGISTRY_DIR = Path(__file__).parent / "registry"

# Bilingual aliases mapping Persian and English terms to DomainType
DOMAIN_ALIASES: Dict[str, DomainType] = {
    # Literary
    "literary": DomainType.LITERARY,
    "lit": DomainType.LITERARY,
    "fiction": DomainType.LITERARY,
    "novel": DomainType.LITERARY,
    "story": DomainType.LITERARY,
    "ادبی": DomainType.LITERARY,
    "ادبیات": DomainType.LITERARY,
    "رمان": DomainType.LITERARY,
    "داستان": DomainType.LITERARY,
    "قصه": DomainType.LITERARY,
    "نثر ادبی": DomainType.LITERARY,

    # Scientific
    "scientific": DomainType.SCIENTIFIC,
    "science": DomainType.SCIENTIFIC,
    "academic": DomainType.SCIENTIFIC,
    "paper": DomainType.SCIENTIFIC,
    "research": DomainType.SCIENTIFIC,
    "علمی": DomainType.SCIENTIFIC,
    "دانشگاهی": DomainType.SCIENTIFIC,
    "مقاله": DomainType.SCIENTIFIC,
    "مقالات": DomainType.SCIENTIFIC,
    "پژوهشی": DomainType.SCIENTIFIC,
    "آکادمیک": DomainType.SCIENTIFIC,

    # Philosophy
    "philosophy": DomainType.PHILOSOPHY,
    "philosophical": DomainType.PHILOSOPHY,
    "humanities": DomainType.PHILOSOPHY,
    "فلسفه": DomainType.PHILOSOPHY,
    "فلسفی": DomainType.PHILOSOPHY,
    "علوم انسانی": DomainType.PHILOSOPHY,
    "حکمت": DomainType.PHILOSOPHY,
    "اندیشه": DomainType.PHILOSOPHY,

    # Legal
    "legal": DomainType.LEGAL,
    "law": DomainType.LEGAL,
    "contract": DomainType.LEGAL,
    "statutory": DomainType.LEGAL,
    "حقوقی": DomainType.LEGAL,
    "قرارداد": DomainType.LEGAL,
    "قانون": DomainType.LEGAL,
    "وکالت": DomainType.LEGAL,
    "اسناد": DomainType.LEGAL,
    "اسناد رسمی": DomainType.LEGAL,

    # Technical
    "technical": DomainType.TECHNICAL,
    "tech": DomainType.TECHNICAL,
    "engineering": DomainType.TECHNICAL,
    "software": DomainType.TECHNICAL,
    "code": DomainType.TECHNICAL,
    "فنی": DomainType.TECHNICAL,
    "مهندسی": DomainType.TECHNICAL,
    "نرم‌افزار": DomainType.TECHNICAL,
    "نرم افزار": DomainType.TECHNICAL,
    "برنامه‌نویسی": DomainType.TECHNICAL,
    "برنامه نویسی": DomainType.TECHNICAL,
    "کد": DomainType.TECHNICAL,
    "تکنیکال": DomainType.TECHNICAL,

    # Medical
    "medical": DomainType.MEDICAL,
    "medicine": DomainType.MEDICAL,
    "clinical": DomainType.MEDICAL,
    "pharma": DomainType.MEDICAL,
    "pharmaceutical": DomainType.MEDICAL,
    "پزشکی": DomainType.MEDICAL,
    "بالینی": DomainType.MEDICAL,
    "دارو": DomainType.MEDICAL,
    "داروسازی": DomainType.MEDICAL,
    "درمان": DomainType.MEDICAL,
    "پزشکی و بالینی": DomainType.MEDICAL,

    # Media
    "media": DomainType.MEDIA,
    "journalism": DomainType.MEDIA,
    "news": DomainType.MEDIA,
    "press": DomainType.MEDIA,
    "رسانه": DomainType.MEDIA,
    "رسانه‌ای": DomainType.MEDIA,
    "رسانه ای": DomainType.MEDIA,
    "خبر": DomainType.MEDIA,
    "اخبار": DomainType.MEDIA,
    "ژورنالیسم": DomainType.MEDIA,
    "مطبوعات": DomainType.MEDIA,
    "ژورنالیستی": DomainType.MEDIA,

    # Financial
    "financial": DomainType.FINANCIAL,
    "finance": DomainType.FINANCIAL,
    "economy": DomainType.FINANCIAL,
    "economic": DomainType.FINANCIAL,
    "economics": DomainType.FINANCIAL,
    "مالی": DomainType.FINANCIAL,
    "اقتصاد": DomainType.FINANCIAL,
    "اقتصادی": DomainType.FINANCIAL,
    "بازرگانی": DomainType.FINANCIAL,
    "تجاری": DomainType.FINANCIAL,
    "بورس": DomainType.FINANCIAL,
    "امور مالی": DomainType.FINANCIAL,

    # Classical
    "classical": DomainType.CLASSICAL,
    "historic": DomainType.CLASSICAL,
    "historical": DomainType.CLASSICAL,
    "ancient": DomainType.CLASSICAL,
    "scripture": DomainType.CLASSICAL,
    "کهن": DomainType.CLASSICAL,
    "متون کهن": DomainType.CLASSICAL,
    "تاریخی": DomainType.CLASSICAL,
    "قدیمی": DomainType.CLASSICAL,
    "باستانی": DomainType.CLASSICAL,
    "متون مقدس": DomainType.CLASSICAL,
    "کلاسیک": DomainType.CLASSICAL,

    # Transcreation
    "transcreation": DomainType.TRANSCREATION,
    "branding": DomainType.TRANSCREATION,
    "advertising": DomainType.TRANSCREATION,
    "copywriting": DomainType.TRANSCREATION,
    "marketing": DomainType.TRANSCREATION,
    "creative": DomainType.TRANSCREATION,
    "بازآفرینی": DomainType.TRANSCREATION,
    "بازآفرینی خلاق": DomainType.TRANSCREATION,
    "برندینگ": DomainType.TRANSCREATION,
    "تبلیغات": DomainType.TRANSCREATION,
    "تبلیغاتی": DomainType.TRANSCREATION,
    "شعار": DomainType.TRANSCREATION,
    "کپی‌رایتینگ": DomainType.TRANSCREATION,
    "کپی رایتینگ": DomainType.TRANSCREATION,
    "بازاریابی": DomainType.TRANSCREATION,
}


class DomainRegistry:
    """
    Registry for managing and loading domain profiles from JSON files.
    """

    def __init__(self, registry_dir: Optional[Union[Path, str]] = None) -> None:
        self.registry_dir = Path(registry_dir) if registry_dir else DEFAULT_REGISTRY_DIR
        self._cache: Dict[DomainType, DomainProfile] = {}

    def _load_domain(self, domain: DomainType) -> DomainProfile:
        json_path = self.registry_dir / f"{domain.value}.json"
        if not json_path.exists():
            raise FileNotFoundError(f"Domain profile file not found: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = DomainProfile.model_validate(data)
        self._cache[domain] = profile
        return profile

    def get(self, domain_type: Union[DomainType, str]) -> DomainProfile:
        """
        Get a domain profile by DomainType enum or alias string.
        """
        if isinstance(domain_type, DomainType):
            key = domain_type
        elif isinstance(domain_type, str):
            normalized = domain_type.strip().lower().replace("ي", "ی").replace("ك", "ک")
            if normalized in DOMAIN_ALIASES:
                key = DOMAIN_ALIASES[normalized]
            else:
                key = DomainType(normalized)
        else:
            raise TypeError(f"Expected DomainType or str, got {type(domain_type)}")

        if key not in self._cache:
            self._load_domain(key)
        return self._cache[key]

    def list_all(self) -> List[DomainProfile]:
        """
        List all 10 domain profiles ordered by DomainType.
        """
        if len(self._cache) < len(DomainType):
            self.load_all()
        return [self._cache[domain] for domain in DomainType]

    def load_all(self) -> Dict[DomainType, DomainProfile]:
        """
        Preload all domain profiles into cache.
        """
        for domain in DomainType:
            if domain not in self._cache:
                self._load_domain(domain)
        return self._cache


# Pattern dictionaries with weights for each of the 10 domains
DOMAIN_PATTERNS: Dict[DomainType, List[Tuple[str, float]]] = {
    DomainType.LITERARY: [
        (r"\b(whispered|murmured|gasped|shivered|sighed|sobbed|gazed|smiled|cried)\b", 3.5),
        (r"\b(protagonist|antagonist|dialogue|narrative|chapter|novel|fiction|storytelling|sorrow|shadows|twilight|heartbeat)\b", 2.5),
        (r"(زیر لب گفت|نجوا کرد|فریاد زد|چشمانش|اشک‌هایش|لبخندی زد|نگاهی انداخت|آهی کشید|داستان|(?<![آ-یء-ي])رمان(?![آ-یء-ي])|شخصیت اصلی)", 3.5),
    ],
    DomainType.SCIENTIFIC: [
        (r"\b(statistically\s+significant|p-value|confidence\s+interval|standard\s+deviation)\b", 4.0),
        (r"\b(methodology|hypothesis|hypotheses|empirical|dataset|variables|cohort|et\s+al\.|literature\s+review|peer-reviewed|journal)\b", 3.0),
        (r"\b(correlation|regression|sample\s+size|findings|quantitative|qualitative)\b", 2.0),
        (r"(از نظر آماری معنادار|فرضیه|روش‌شناسی|یافته‌های تجربی|تحلیل آماری|جامعه آماری|همبستگی|مقاله علمی)", 3.5),
    ],
    DomainType.PHILOSOPHY: [
        (r"\b(dasein|ontology|ontological|epistemology|epistemological|phenomenology|phenomenological|hermeneutic[s]?)\b", 4.0),
        (r"\b(metaphysics|metaphysical|existentialism|existential|transcendental|categorical\s+imperative|dialectic[s]?|aufhebung|cogito)\b", 3.5),
        (r"\b(being\s+and\s+time|consciousness|critique\s+of\s+pure\s+reason|a\s+priori|epoche)\b", 3.0),
        (r"(هستی‌شناسی|معرفت‌شناسی|پدیدارشناسی|دازاین|استعلایی|اگزیستانسیال|متافیزیک|دیالکتیک|امر مطلق|پیشینی)", 4.0),
    ],
    DomainType.LEGAL: [
        (r"\b(hereby|hereunder|herein|indemnify|indemnification|hold\s+harmless|jurisdiction|pursuant\s+to)\b", 4.0),
        (r"\b(breach\s+of\s+contract|force\s+majeure|governing\s+law|in\s+witness\s+whereof|clause|statutory|severability)\b", 3.5),
        (r"\b(arbitration|party|parties|liability|liabilities|agreement|licensee|licensor|obligations?)\b", 2.5),
        (r"(بدین‌وسیله|صلاحیت قضایی|جبران خسارت|نقض قرارداد|قوه قاهره|طرفین قرارداد|ماده و تبصره|حل اختلاف)", 4.0),
    ],
    DomainType.TECHNICAL: [
        (r"\b(api|endpoint|docker|kubernetes|cli|runtime|compile|compiler|stack\s+trace|sdk|repository|git)\b", 3.5),
        (r"\b(async|await|function|interface|database|frontend|backend|npm|pip|syntax|debug|bug)\b", 2.5),
        (r"\b(github|pull\s+request|npm\s+install|pip\s+install|yaml|json|microservice)\b", 3.0),
        (r"(کامپایل|اندپوینت|مخزن گیت|داکر|استقرار|خط فرمان|پایگاه داده|دیباگ|توسعه‌دهنده)", 3.5),
    ],
    DomainType.MEDICAL: [
        (r"\b(prognosis|etiology|biopsy|pathology|pharmacology|intravenous|subcutaneous|dosage|mg/kg)\b", 4.0),
        (r"\b(clinical\s+trial|adverse\s+reaction|contraindication|symptoms|therapeutic|oncology|syndrome|diagnosis)\b", 3.5),
        (r"\b(patient|hospital|physician|therapy|prescription|amoxicillin|infection|disease)\b", 2.0),
        (r"(پیش‌آگهی|اتیولوژی|بیوپسی|پاتولوژی|تجویز دارو|دوز|وریدی|کارآزمایی بالینی|عوارض جانبی|منع مصرف|بیمار)", 4.0),
    ],
    DomainType.MEDIA: [
        (r"\b(breaking\s+news|press\s+conference|press\s+briefing|correspondent|reuters|associated\s+press)\b", 4.0),
        (r"\b(spokesperson|spokesman|headline|according\s+to\s+sources|reported\s+that|news\s+agency|dateline)\b", 3.5),
        (r"\b(editorial|broadcast|journalist|journalism|press\s+release|coverage)\b", 2.5),
        (r"(خبر فوری|نشست خبری|گزارشگر|خبرگزاری|سخنگو|به گزارش|تیتر خبر|پوشش خبری|رویترز)", 4.0),
    ],
    DomainType.FINANCIAL: [
        (r"\b(ebitda|balance\s+sheet|fiscal\s+year|cash\s+flow|liquidity|dividend|market\s+cap|ifrs|gaap)\b", 4.0),
        (r"\b(equity|bonds|inflation|quarterly\s+earnings|roi|portfolio|revenue|assets|liabilities|shares)\b", 3.0),
        (r"\b(interest\s+rate|bull\s+market|bear\s+market|capital\s+gain|stock\s+exchange)\b", 2.5),
        (r"(ترازنامه|سود هر سهم|نقدینگی|سال مالی|جریان وجوه نقد|ارزش بازار|نرخ تورم|بازار سرمایه|اوراق بهادار|بورس)", 4.0),
    ],
    DomainType.CLASSICAL: [
        (r"\b(thou|thee|thy|thine|hath|doth|dost|wherefore|art\s+thou|prophesied|covenant)\b", 4.0),
        (r"\b(ancient\s+chronicle|king\s+reign|realm|noble\s+knight|chronicles\s+of\s+old|scripture|sacred|antiquity)\b", 3.5),
        (r"\b(unto|beget|begat|sovereign|chariot|providence)\b", 2.5),
        (r"(اندر آن روزگار|چنین گوید|رویدادنامه|عهد عتیق|شهریار دادگستر|روزگاران کهن|حکایت چنان بود|همانا|دیار)", 4.0),
    ],
    DomainType.TRANSCREATION: [
        (r"\b(tagline|catchphrase|brand\s+identity|call\s+to\s+action|cta|billboard|ad\s+campaign)\b", 4.0),
        (r"\b(slogan|copywriting|reimagine|unleash\s+your|elevate\s+your|marketing\s+punch|brand\s+voice)\b", 3.5),
        (r"\b(advertising|advertisement|branding|commercial|campaign)\b", 2.5),
        (r"(شعار برند|شعار تبلیغاتی|هویت برند|کمپین تبلیغاتی|دعوت به اقدام|کپی‌رایتینگ|متفاوت بیندیشید|روایت برند)", 4.0),
    ],
}


class DomainRouter:
    """
    Intelligent classifier and router that maps source texts or explicit overrides to DomainProfile.
    """

    def __init__(self, registry: Optional[DomainRegistry] = None) -> None:
        self.registry = registry or DomainRegistry()
        # Precompile patterns for fast scoring
        self._compiled_patterns: Dict[DomainType, List[Tuple[re.Pattern, float]]] = {
            domain: [
                (re.compile(pattern, re.IGNORECASE), weight)
                for pattern, weight in patterns
            ]
            for domain, patterns in DOMAIN_PATTERNS.items()
        }

    def route(self, text: str, override: Optional[str] = None) -> Tuple[DomainProfile, float]:
        """
        Route text to the appropriate domain profile.

        If `override` is provided, resolves the override via DOMAIN_ALIASES or DomainType enum
        and returns the profile with confidence 1.0.

        Otherwise, classifies the text using weighted pattern matching and returns
        the best profile and a calculated confidence score between 0.0 and 1.0.
        """
        if override is not None:
            normalized = override.strip().lower().replace("ي", "ی").replace("ك", "ک")
            if normalized in DOMAIN_ALIASES:
                target_domain = DOMAIN_ALIASES[normalized]
            else:
                try:
                    target_domain = DomainType(normalized)
                except ValueError:
                    raise ValueError(f"Unknown domain override: '{override}'")
            return self.registry.get(target_domain), 1.0

        # Pattern scoring
        scores: Dict[DomainType, float] = {domain: 0.0 for domain in DomainType}

        for domain, patterns in self._compiled_patterns.items():
            for regex, weight in patterns:
                matches = regex.findall(text)
                if matches:
                    scores[domain] += weight * len(matches)

        best_domain = max(scores, key=scores.get) # type: ignore[arg-type]
        best_score = scores[best_domain]

        if best_score <= 0.0:
            # Fallback to literary with minimal baseline confidence
            return self.registry.get(DomainType.LITERARY), 0.30

        # Compute confidence based on score strength
        confidence = min(0.99, max(0.50, round(0.50 + (best_score / (best_score + 4.0)) * 0.49, 2)))
        return self.registry.get(best_domain), confidence
