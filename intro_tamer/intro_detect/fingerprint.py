"""Audio fingerprint-based intro detection."""

import pickle
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
from pydantic import BaseModel

from intro_tamer.extract_audio import extract_audio_segment


class IntroBoundaries(BaseModel):
    """Detected intro boundaries."""

    start: float
    end: float
    confidence: float
    method: str


class FingerprintDetector:
    """Detect intro using audio fingerprint matching."""

    def __init__(
        self,
        reference_audio: Optional[np.ndarray] = None,
        reference_fingerprint_path: Optional[Path] = None,
        sample_rate: int = 22050,
        similarity_threshold: float = 0.82,
    ):
        """
        Initialize fingerprint detector.

        Args:
            reference_audio: Reference audio array (or None if loading from file)
            reference_fingerprint_path: Path to saved fingerprint (.npz or .pkl)
            sample_rate: Sample rate for analysis
            similarity_threshold: Minimum similarity score for match
        """
        self.sample_rate = sample_rate
        self.similarity_threshold = similarity_threshold

        if reference_fingerprint_path and reference_fingerprint_path.exists():
            self.reference_fingerprint = self._load_fingerprint(reference_fingerprint_path)
        elif reference_audio is not None:
            self.reference_fingerprint = self._compute_fingerprint(reference_audio)
        else:
            raise ValueError("Must provide either reference_audio or reference_fingerprint_path")

    def _compute_fingerprint(self, audio: np.ndarray) -> np.ndarray:
        """
        Compute audio fingerprint using chroma features.

        Args:
            audio: Audio array

        Returns:
            Fingerprint feature matrix
        """
        # Use chroma features for music-like content
        chroma = librosa.feature.chroma_stft(y=audio, sr=self.sample_rate)
        # Also include MFCC for additional discrimination
        mfcc = librosa.feature.mfcc(y=audio, sr=self.sample_rate, n_mfcc=13)

        # Combine features
        features = np.vstack([chroma, mfcc])
        return features

    def _load_fingerprint(self, path: Path) -> np.ndarray:
        """Load fingerprint from file."""
        if path.suffix == ".npz":
            data = np.load(path)
            return data["fingerprint"]
        elif path.suffix == ".pkl":
            with open(path, "rb") as f:
                return pickle.load(f)
        else:
            raise ValueError(f"Unsupported fingerprint format: {path.suffix}")

    def _save_fingerprint(self, fingerprint: np.ndarray, path: Path) -> None:
        """Save fingerprint to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".npz":
            np.savez_compressed(path, fingerprint=fingerprint)
        elif path.suffix == ".pkl":
            with open(path, "wb") as f:
                pickle.dump(fingerprint, f)
        else:
            raise ValueError(f"Unsupported fingerprint format: {path.suffix}")

    def _compute_similarity(self, ref_fp: np.ndarray, query_fp: np.ndarray) -> float:
        """
        Compute cosine similarity between fingerprints.

        Args:
            ref_fp: Reference fingerprint
            query_fp: Query fingerprint

        Returns:
            Similarity score [0, 1]
        """
        # Flatten and normalize
        ref_flat = ref_fp.flatten()
        query_flat = query_fp.flatten()

        # Ensure same length (pad or truncate)
        min_len = min(len(ref_flat), len(query_flat))
        ref_flat = ref_flat[:min_len]
        query_flat = query_flat[:min_len]

        # Cosine similarity
        dot_product = np.dot(ref_flat, query_flat)
        norm_ref = np.linalg.norm(ref_flat)
        norm_query = np.linalg.norm(query_flat)

        if norm_ref == 0 or norm_query == 0:
            return 0.0

        similarity = dot_product / (norm_ref * norm_query)
        # Normalize to [0, 1] (cosine similarity is [-1, 1])
        return (similarity + 1) / 2

    def detect(
        self,
        video_path: Path,
        search_start: float = 0.0,
        search_duration: float = 300.0,
        audio_stream_index: int = 0,
        padding_ms: float = 200.0,
    ) -> Optional[IntroBoundaries]:
        """
        Detect intro boundaries in video file.

        Args:
            video_path: Path to video file
            search_start: Start of search window in seconds
            search_duration: Duration of search window in seconds
            audio_stream_index: Audio stream index
            padding_ms: Padding to add before/after match in milliseconds

        Returns:
            IntroBoundaries if detected, None otherwise
        """
        # Extract search window audio
        search_audio, _ = extract_audio_segment(
            video_path,
            search_start,
            search_duration,
            audio_stream_index,
            self.sample_rate,
        )

        # Sliding window search
        ref_duration = self.reference_fingerprint.shape[1] / self.sample_rate * 512  # Approximate
        window_samples = int(ref_duration * self.sample_rate)
        hop_samples = int(0.5 * self.sample_rate)  # 0.5s hop

        best_match = None
        best_score = 0.0
        best_offset = 0

        for offset in range(0, len(search_audio) - window_samples, hop_samples):
            window = search_audio[offset : offset + window_samples]
            window_fp = self._compute_fingerprint(window)
            similarity = self._compute_similarity(self.reference_fingerprint, window_fp)

            if similarity > best_score:
                best_score = similarity
                best_offset = offset
                best_match = window

        if best_score < self.similarity_threshold:
            return None

        # Convert offset to time
        match_start_time = search_start + (best_offset / self.sample_rate)
        match_end_time = match_start_time + (window_samples / self.sample_rate)

        # Add padding
        padding_seconds = padding_ms / 1000.0
        intro_start = max(0.0, match_start_time - padding_seconds)
        intro_end = match_end_time + padding_seconds

        return IntroBoundaries(
            start=intro_start,
            end=intro_end,
            confidence=best_score,
            method="fingerprint",
        )

    @classmethod
    def create_fingerprint_from_reference(
        cls,
        video_path: Path,
        start_time: float,
        end_time: float,
        output_path: Path,
        audio_stream_index: int = 0,
        sample_rate: int = 22050,
    ) -> None:
        """
        Create and save fingerprint from reference audio segment.

        Args:
            video_path: Path to video file with reference intro
            start_time: Start time of reference intro
            end_time: End time of reference intro
            output_path: Path to save fingerprint
            audio_stream_index: Audio stream index
            sample_rate: Sample rate
        """
        from intro_tamer.extract_audio import extract_reference_audio

        reference_audio = extract_reference_audio(
            video_path, start_time, end_time, audio_stream_index, sample_rate
        )

        detector = cls(reference_audio=reference_audio, sample_rate=sample_rate)
        detector._save_fingerprint(detector.reference_fingerprint, output_path)

