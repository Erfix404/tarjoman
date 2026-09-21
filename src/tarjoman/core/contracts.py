"""
Data Contracts and Pydantic Models for Tarjoman Universal Translation Engine.
"""
from __future__ import annotations
from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class DomainType(str, Enum):
    LITERARY = "literary"           # رمان، داستان و نثر ادبی
    SCIENTIFIC = "scientific"       # مقالات، کتاب‌های مرجع و دانشگاهی
    PHILOSOPHY = "philosophy"       # فلسفه، اندیشه و علوم انسانی
    LEGAL = "legal"                 # حقوقی، قراردادها و اسناد رسمی
    TECHNICAL = "technical"         # نرم‌افزار، کد و اسناد مهندسی
    MEDICAL = "medical"             # پزشکی، بالینی و داروسازی
    MEDIA = "media"                 # رسانه، اخبار و ژورنالیسم
    FINANCIAL = "financial"         # اقتصاد، بازرگانی و مالی
    CLASSICAL = "classical"         # متون کهن، تاریخی و متون مقدس
    TRANSCREATION = "transcreation" # بازآفرینی خلاق، برندینگ و تبلیغات


class EmDashPolicy(str, Enum):
    ERADICATE = "eradicate"
    ADAPT = "adapt"
    PRESERVE = "preserve"


class TypographicRules(BaseModel):
    em_dash_policy: EmDashPolicy = EmDashPolicy.ADAPT
    enforce_persian_quotes: bool = True
    invert_dialogue_tags: bool = False
    strict_zwnj: bool = True
    western_digits: bool = False
    isolate_english_terms: bool = False


class DomainProfile(BaseModel):
    id: DomainType
    title_fa: str
    description: str
    system_prompt: str
    banned_calques: List[str] = Field(default_factory=list)
    terminology_map: Dict[str, str] = Field(default_factory=dict)
    typography: TypographicRules = Field(default_factory=TypographicRules)
    few_shot_examples: List[Dict[str, str]] = Field(default_factory=list)


class TextSegment(BaseModel):
    id: int
    source_text: str
    is_protected: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    translated_text: Optional[str] = None
    reflection_critique: Optional[str] = None
    polished_text: Optional[str] = None


class StageResult(BaseModel):
    stage_name: str
    success: bool
    segments: List[TextSegment]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class AuditFinding(BaseModel):
    rule_id: str
    severity: str              # "critical" | "major" | "minor"
    segment_id: int
    message: str
    excerpt: str


class AuditReport(BaseModel):
    passed: bool
    quality_score: float       # 0.0 to 100.0
    omission_count: int
    banned_calque_count: int
    findings: List[AuditFinding] = Field(default_factory=list)


class BookManifest(BaseModel):
    title: str
    source_language: str = "en"
    target_language: str = "fa"
    total_chapters: int = 1
    current_chapter: int = 0
    total_segments: int = 0
    translated_segments: int = 0
    terms_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
