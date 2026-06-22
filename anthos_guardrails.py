"""
anthos/guardrails.py — Native Guardrails & Filters for the Anthos Model

This module implements native, offline safeguards designed to analyze and restrict
inputs and outputs for the self-built Anthos model, preventing harmful, profane,
racist, sexist, or illegal content generation, specifically blocking discussions
regarding race, ethnicity, or discriminatory language. All processing is fully
local and self-contained.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# Compile regexes for high-performance offline validation
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
IP_REGEX = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")

# Core toxic/profanity keywords
PROFANITY_KEYWORDS = {
    "fuck", "shit", "bitch", "cunt", "asshole", "bastard", "dick", "pussy",
    "motherfucker", "whore", "slut", "crap", "damn", "piss", "cock", "wank",
}

RACISM_SEXISM_KEYWORDS = {
    # Hate speech, slurs, and derogatory identifiers
    "nigger", "nigga", "chink", "kike", "spic", "wetback", "gook", "faggot", "dyke",
    "retard", "tranny", "raghead", "towelhead", "slanteye", "redskin", "negro",
    "subhuman", "mongrel", "halfbreed", "slut", "bitch", "cunt", "whore",
}

ETHNICITY_RACE_KEYWORDS = {
    "ethnicity", "ethnic", "race", "racial", "caucasian", "mongoloid", "negroid",
    "black people", "white people", "asian people", "hispanic people", "latino",
    "latina", "african american", "native american", "indigenous people",
    "skin color", "ancestry", "lineage", "tribalism", "interracial",
}

JAILBREAK_PATTERNS = [
    r"dan\s+mode",
    r"ignore\s+previous\s+instructions",
    r"bypass\s+safety",
    r"system\s+override",
    r"developer\s+mode",
    r"do\s+anything\s+now",
    r"jailbreak",
    r"you\s+are\s+now\s+a\s+malicious",
    r"forget\s+your\s+rules",
    r"ignore\s+ethical\s+standards",
    r"disregard\s+safety\s+filters",
    r"decode\s+the\s+following\s+base64",
    r"hypothetical\s+scenario\s+where\s+you\s+can\s+say",
]

@dataclass
class GuardrailConfig:
    """Configuration for Anthos Native Guardrails."""
    enable_pii_redaction: bool = True
    enable_hap_filter: bool = True
    enable_race_ethnicity_filter: bool = True
    enable_jailbreak_defense: bool = True
    
    # Custom safety message returned on input block
    safety_block_message: str = "Request blocked: The input contains content that violates our ethical, safety, and community guidelines."
    
    # Custom safety message returned on output block / override
    output_block_message: str = "Content withheld: The generated output contains content violating our ethical or safety guidelines."


class PIIRedactor:
    """Identifies and masks Personally Identifiable Information locally."""
    
    def redact(self, text: str) -> str:
        text = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
        text = PHONE_REGEX.sub("[REDACTED_PHONE]", text)
        text = SSN_REGEX.sub("[REDACTED_SSN]", text)
        text = IP_REGEX.sub("[REDACTED_IP]", text)
        return text


class HAPFilter:
    """Local HAP (Hate, Abuse, Profanity/Racism/Sexism) Classifier."""
    
    def is_safe(self, text: str) -> tuple[bool, Optional[str]]:
        """
        Returns (is_safe, reason).
        """
        words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
        
        # Check profanity
        profane_matches = words.intersection(PROFANITY_KEYWORDS)
        if profane_matches:
            return False, f"Profanity detected: {', '.join(profane_matches)}"
            
        # Check racism, sexism, and slurs
        hate_matches = words.intersection(RACISM_SEXISM_KEYWORDS)
        if hate_matches:
            return False, f"Derogatory or hate speech/slur detected: {', '.join(hate_matches)}"
            
        return True, None


class RaceEthnicityBlocker:
    """Prevents discussing people's ethnicity or race to avoid stereotyping/harm."""
    
    def is_safe(self, text: str) -> tuple[bool, Optional[str]]:
        lower_text = text.lower()

        for key in ETHNICITY_RACE_KEYWORDS:
            if key in lower_text:
                return False, f"Discussions regarding race or ethnicity are restricted: found '{key}'"
                
        # Regex check for sensitive phrases like "people of race X" or "why are X people"
        harmful_patterns = [
            r"\b(?:black|white|asian|hispanic|latino|latina|indian|jewish|arab|muslim|christian)\s+(?:people|men|women|children|race|ethnicity)\b",
            r"\b(?:race|ethnic)\s+(?:differences|superiority|inferiority|traits|stereotypes)\b",
        ]
        for pattern in harmful_patterns:
            if re.search(pattern, lower_text):
                return False, "Discussions containing racial or ethnic stereotyping/classification are restricted"
                
        return True, None


class JailbreakDefense:
    """Detects prompt injection and jailbreak attempts."""
    
    def is_safe(self, text: str) -> tuple[bool, Optional[str]]:
        lower_text = text.lower()
        for pattern in JAILBREAK_PATTERNS:
            if re.search(pattern, lower_text):
                return False, f"Potential jailbreak pattern detected: '{pattern}'"
        return True, None


class GuardrailSystem:
    """Orchestrates input pre-processing and output post-processing for Anthos."""
    
    def __init__(self, config: Optional[GuardrailConfig] = None):
        self.config = config or GuardrailConfig()
        self.pii = PIIRedactor()
        self.hap = HAPFilter()
        self.race_ethnicity = RaceEthnicityBlocker()
        self.jailbreak = JailbreakDefense()
        
    def verify_input(self, text: str) -> tuple[bool, str]:
        """
        Analyzes and validates prompt inputs locally.
        
        Returns:
            (is_safe, sanitized_text_or_error_msg)
        """
        # 1. Jailbreak checking
        if self.config.enable_jailbreak_defense:
            is_safe, reason = self.jailbreak.is_safe(text)
            if not is_safe:
                log.warning(f"Input blocked by Jailbreak defense: {reason}")
                return False, self.config.safety_block_message
                
        # 2. HAP (Hate, Abuse, Profanity, Racism, Sexism) checking
        if self.config.enable_hap_filter:
            is_safe, reason = self.hap.is_safe(text)
            if not is_safe:
                log.warning(f"Input blocked by HAP filter: {reason}")
                return False, self.config.safety_block_message
                
        # 3. Race & Ethnicity blocker
        if self.config.enable_race_ethnicity_filter:
            is_safe, reason = self.race_ethnicity.is_safe(text)
            if not is_safe:
                log.warning(f"Input blocked by Race/Ethnicity blocker: {reason}")
                return False, self.config.safety_block_message
                
        # 4. PII Redaction
        sanitized = text
        if self.config.enable_pii_redaction:
            sanitized = self.pii.redact(text)
            
        return True, sanitized

    def verify_output(self, text: str) -> tuple[bool, str]:
        """
        Analyzes and sanitizes model output locally.
        
        Returns:
            (is_safe, sanitized_text_or_error_msg)
        """
        # 1. HAP checking
        if self.config.enable_hap_filter:
            is_safe, reason = self.hap.is_safe(text)
            if not is_safe:
                log.warning(f"Output blocked by HAP filter: {reason}")
                return False, self.config.output_block_message
                
        # 2. Race & Ethnicity blocker
        if self.config.enable_race_ethnicity_filter:
            is_safe, reason = self.race_ethnicity.is_safe(text)
            if not is_safe:
                log.warning(f"Output blocked by Race/Ethnicity blocker: {reason}")
                return False, self.config.output_block_message
                
        # 3. PII Redaction
        sanitized = text
        if self.config.enable_pii_redaction:
            sanitized = self.pii.redact(text)
            
        return True, sanitized
