"""Language detection service using langdetect library."""

from typing import Optional

import structlog
from langdetect import DetectorFactory, LangDetectException, detect_langs

from integritykit.models.language import (
    AlternativeLanguage,
    DetectionMethod,
    LanguageCode,
    LanguageDetectionResult,
)
from integritykit.models.signal import Signal

logger = structlog.get_logger(__name__)

# Set seed for consistent results across runs
DetectorFactory.seed = 0


class LanguageDetectionService:
    """Service for detecting language of signal text content.

    Uses the langdetect library for fast, reliable language detection
    with support for confidence thresholds and alternative candidates.
    """

    # Map langdetect language codes to our LanguageCode enum
    LANGDETECT_TO_LANGUAGE_CODE = {
        "en": LanguageCode.EN,
        "es": LanguageCode.ES,
        "fr": LanguageCode.FR,
    }

    def __init__(
        self,
        confidence_threshold: float = 0.8,
        enabled: bool = True,
        supported_languages: Optional[list[str]] = None,
    ):
        """Initialize language detection service.

        Args:
            confidence_threshold: Minimum confidence score to accept detection (0.0-1.0)
            enabled: Whether language detection is enabled
            supported_languages: List of supported language codes (defaults to en,es,fr)
        """
        self.confidence_threshold = confidence_threshold
        self.enabled = enabled

        # Parse supported languages or use defaults
        if supported_languages:
            self.supported_languages = [
                lang.strip().lower() for lang in supported_languages
            ]
        else:
            self.supported_languages = ["en", "es", "fr"]

        logger.info(
            "Language detection service initialized",
            enabled=self.enabled,
            threshold=self.confidence_threshold,
            supported_languages=self.supported_languages,
        )

    def _normalize_text(self, text: str) -> str:
        """Normalize text for language detection.

        Args:
            text: Raw text content

        Returns:
            Normalized text suitable for detection
        """
        # Remove URLs
        import re
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

        # Remove mentions
        text = re.sub(r'<@[A-Z0-9]+>', '', text)

        # Remove channel references
        text = re.sub(r'<#[A-Z0-9]+\|[^>]+>', '', text)

        # Remove excessive whitespace
        text = ' '.join(text.split())

        return text.strip()

    def detect_language(
        self,
        text: str,
        force_language: Optional[LanguageCode] = None,
    ) -> LanguageDetectionResult:
        """Detect language of text content.

        Args:
            text: Text content to analyze
            force_language: Optional manual override to skip detection

        Returns:
            LanguageDetectionResult with detected language and confidence

        Raises:
            ValueError: If text is empty or detection fails
        """
        # Handle manual override
        if force_language:
            logger.info(
                "Language manually overridden",
                forced_language=force_language.value,
            )
            return LanguageDetectionResult(
                detected_language=force_language,
                confidence=1.0,
                alternative_languages=[],
                detection_method=DetectionMethod.MANUAL_OVERRIDE,
                meets_threshold=True,
                threshold=self.confidence_threshold,
            )

        # Check if detection is enabled
        if not self.enabled:
            logger.warning("Language detection disabled, defaulting to English")
            return LanguageDetectionResult(
                detected_language=LanguageCode.EN,
                confidence=0.5,
                alternative_languages=[],
                detection_method=DetectionMethod.LANGDETECT,
                meets_threshold=False,
                threshold=self.confidence_threshold,
            )

        # Normalize text
        normalized_text = self._normalize_text(text)

        if not normalized_text or len(normalized_text) < 3:
            logger.warning(
                "Text too short for language detection, defaulting to English",
                text_length=len(normalized_text),
            )
            return LanguageDetectionResult(
                detected_language=LanguageCode.EN,
                confidence=0.5,
                alternative_languages=[],
                detection_method=DetectionMethod.LANGDETECT,
                meets_threshold=False,
                threshold=self.confidence_threshold,
            )

        try:
            # Detect languages with probabilities
            lang_probs = detect_langs(normalized_text)

            # Filter to supported languages only
            supported_probs = [
                (prob.lang, prob.prob)
                for prob in lang_probs
                if prob.lang in self.supported_languages
            ]

            if not supported_probs:
                logger.warning(
                    "No supported languages detected, defaulting to English",
                    detected_languages=[prob.lang for prob in lang_probs],
                )
                return LanguageDetectionResult(
                    detected_language=LanguageCode.EN,
                    confidence=0.5,
                    alternative_languages=[],
                    detection_method=DetectionMethod.LANGDETECT,
                    meets_threshold=False,
                    threshold=self.confidence_threshold,
                )

            # Get primary detection
            primary_lang_code, primary_confidence = supported_probs[0]

            # Map to our LanguageCode enum
            detected_language = self.LANGDETECT_TO_LANGUAGE_CODE.get(
                primary_lang_code,
                LanguageCode.EN,
            )

            # Build alternative languages list
            alternatives = []
            for lang_code, confidence in supported_probs[1:]:
                mapped_code = self.LANGDETECT_TO_LANGUAGE_CODE.get(lang_code)
                if mapped_code:
                    alternatives.append(
                        AlternativeLanguage(
                            language_code=mapped_code,
                            confidence=round(confidence, 4),
                        )
                    )

            # Check if meets threshold
            meets_threshold = primary_confidence >= self.confidence_threshold

            result = LanguageDetectionResult(
                detected_language=detected_language,
                confidence=round(primary_confidence, 4),
                alternative_languages=alternatives,
                detection_method=DetectionMethod.LANGDETECT,
                meets_threshold=meets_threshold,
                threshold=self.confidence_threshold,
            )

            logger.info(
                "Language detected",
                detected_language=detected_language.value,
                confidence=primary_confidence,
                meets_threshold=meets_threshold,
                alternatives_count=len(alternatives),
                text_preview=normalized_text[:50],
            )

            return result

        except LangDetectException as e:
            logger.error(
                "Language detection failed",
                error=str(e),
                text_preview=normalized_text[:50],
            )
            # Default to English on error
            return LanguageDetectionResult(
                detected_language=LanguageCode.EN,
                confidence=0.5,
                alternative_languages=[],
                detection_method=DetectionMethod.LANGDETECT,
                meets_threshold=False,
                threshold=self.confidence_threshold,
            )

    def detect_signal_language(
        self,
        signal: Signal,
        force_language: Optional[LanguageCode] = None,
    ) -> LanguageDetectionResult:
        """Detect language for a Signal object.

        Convenience method that extracts text from Signal and detects language.

        Args:
            signal: Signal to analyze
            force_language: Optional manual override

        Returns:
            LanguageDetectionResult with detected language and confidence
        """
        logger.info(
            "Detecting language for signal",
            signal_id=str(signal.id),
            has_force_language=force_language is not None,
        )

        result = self.detect_language(
            text=signal.content,
            force_language=force_language,
        )

        return result

    def batch_detect_languages(
        self,
        signals: list[Signal],
    ) -> dict[str, LanguageDetectionResult]:
        """Detect languages for multiple signals efficiently.

        Args:
            signals: List of signals to analyze

        Returns:
            Dictionary mapping signal ID to detection result
        """
        results = {}

        for signal in signals:
            try:
                result = self.detect_signal_language(signal)
                results[str(signal.id)] = result
            except Exception as e:
                logger.error(
                    "Failed to detect language for signal in batch",
                    signal_id=str(signal.id),
                    error=str(e),
                )
                # Continue with other signals
                continue

        logger.info(
            "Batch language detection complete",
            total_signals=len(signals),
            successful_detections=len(results),
        )

        return results
