"""FFmpeg filtergraph building and rendering."""

import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class RenderConfig(BaseModel):
    """Configuration for audio rendering."""

    intro_start: float
    intro_end: float
    outro_start: Optional[float] = None  # Optional outro start time
    outro_end: Optional[float] = None  # Optional outro end time
    gain_db: float  # Negative = reduce loudness
    fade_ms: int = 120
    audio_stream_index: int = 0
    all_audio_tracks: bool = False


def build_audio_filtergraph(config: RenderConfig) -> str:
    """
    Build FFmpeg audio filtergraph for intro and outro ducking.

    Uses volume filter with time-based expression to apply gain to both intro and outro segments,
    with smooth fade transitions.

    Args:
        config: Render configuration

    Returns:
        Filtergraph string
    """
    fade_seconds = config.fade_ms / 1000.0
    gain_multiplier = 10 ** (config.gain_db / 20.0)
    
    # Calculate fade boundaries for intro
    intro_fade_in_end = config.intro_start + fade_seconds
    intro_fade_out_start = config.intro_end - fade_seconds
    
    # Build expression for intro segment
    intro_expr = (
        f"if(between(t,{config.intro_start},{config.intro_end}),"
        f"if(lt(t,{intro_fade_in_end}),1+({gain_multiplier}-1)*((t-{config.intro_start})/{fade_seconds}),"
        f"if(gt(t,{intro_fade_out_start}),{gain_multiplier}+(1-{gain_multiplier})*((t-{intro_fade_out_start})/{fade_seconds}),"
        f"{gain_multiplier})),1)"
    )
    
    # Build expression for outro segment (if provided)
    if config.outro_start is not None and config.outro_end is not None:
        outro_fade_in_end = config.outro_start + fade_seconds
        outro_fade_out_start = config.outro_end - fade_seconds
        
        outro_expr = (
            f"if(between(t,{config.outro_start},{config.outro_end}),"
            f"if(lt(t,{outro_fade_in_end}),1+({gain_multiplier}-1)*((t-{config.outro_start})/{fade_seconds}),"
            f"if(gt(t,{outro_fade_out_start}),{gain_multiplier}+(1-{gain_multiplier})*((t-{outro_fade_out_start})/{fade_seconds}),"
            f"{gain_multiplier})),1)"
        )
        
        # Combine intro and outro expressions
        # Apply the minimum of the two (so if either segment applies reduction, use it)
        filtergraph = (
            f"volume="
            f"'min({intro_expr},{outro_expr})':eval=frame"
        )
    else:
        # Only intro
        filtergraph = (
            f"volume="
            f"'{intro_expr}':eval=frame"
        )

    return filtergraph


def render_video(
    input_path: Path,
    output_path: Path,
    config: RenderConfig,
    force_reencode: bool = False,
    keep_codecs: bool = True,
) -> None:
    """
    Render video with ducked intro audio.

    Uses a complex filtergraph to split audio into segments, apply volume only to intro,
    then concatenate back together.

    Args:
        input_path: Input video file
        output_path: Output video file
        config: Render configuration
        force_reencode: Force re-encoding even if stream copy possible
        keep_codecs: Attempt to copy video stream, re-encode audio only

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails
    """
    from intro_tamer.media_probe import probe_media
    
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Probe media to get audio codec information
    media_info = probe_media(input_path)
    audio_stream = None
    for stream in media_info.audio_streams:
        if stream.index == config.audio_stream_index:
            audio_stream = stream
            break
    
    if not audio_stream:
        raise ValueError(f"Audio stream {config.audio_stream_index} not found")

    fade_seconds = config.fade_ms / 1000.0
    
    # Build volume expression with fades
    gain_multiplier = 10 ** (config.gain_db / 20.0)
    fade_in_end = config.intro_start + fade_seconds
    fade_out_start = config.intro_end - fade_seconds
    
    volume_expr = (
        f"if(lt(t,{config.intro_start}),1,"
        f"if(lt(t,{fade_in_end}),1+({gain_multiplier}-1)*((t-{config.intro_start})/{fade_seconds}),"
        f"if(lt(t,{fade_out_start}),{gain_multiplier},"
        f"if(lt(t,{config.intro_end}),{gain_multiplier}+(1-{gain_multiplier})*((t-{fade_out_start})/{fade_seconds}),1))))"
    )
    
    filtergraph = f"volume='{volume_expr}':eval=frame"

    cmd = ["ffmpeg", "-i", str(input_path), "-y"]

    # Map video stream (copy if possible)
    if keep_codecs and not force_reencode:
        cmd.extend(["-map", "0:v:0", "-c:v", "copy"])
    else:
        cmd.extend(["-map", "0:v:0", "-c:v", "libx264", "-crf", "23"])

    # Determine audio codec and bitrate settings
    # Since we're applying filters, we need to re-encode audio
    # But we should preserve quality based on original codec
    audio_codec = audio_stream.codec_name.lower()
    original_bitrate = audio_stream.bit_rate
    
    # Choose appropriate codec and quality settings
    if audio_codec in ("flac", "pcm", "pcm_s16le", "pcm_s24le", "pcm_s32le"):
        # Lossless source - use FLAC to preserve quality
        audio_codec_arg = "flac"
        audio_quality_args = ["-compression_level", "5"]  # Good compression/speed balance
    elif audio_codec == "aac":
        # Already AAC - use high quality AAC
        audio_codec_arg = "aac"
        if original_bitrate:
            try:
                bitrate = int(original_bitrate) // 1000  # Convert to kbps
                audio_quality_args = ["-b:a", f"{max(bitrate, 192)}k"]  # Use original or min 192k
            except (ValueError, TypeError):
                audio_quality_args = ["-b:a", "320k"]  # High quality default
        else:
            audio_quality_args = ["-b:a", "320k"]
    elif audio_codec in ("ac3", "eac3"):
        # AC3/EAC3 - preserve codec
        audio_codec_arg = audio_codec
        if original_bitrate:
            try:
                bitrate = int(original_bitrate) // 1000
                audio_quality_args = ["-b:a", f"{max(bitrate, 192)}k"]
            except (ValueError, TypeError):
                audio_quality_args = ["-b:a", "384k"]  # AC3 default
        else:
            audio_quality_args = ["-b:a", "384k"]
    elif audio_codec in ("dts", "truehd"):
        # High-quality codecs - use high-bitrate AAC as fallback
        audio_codec_arg = "aac"
        audio_quality_args = ["-b:a", "320k"]
    else:
        # Unknown codec - use high-quality AAC
        audio_codec_arg = "aac"
        audio_quality_args = ["-b:a", "320k"]

    # Map audio stream(s)
    if config.all_audio_tracks:
        # Process all audio tracks
        cmd.extend(["-map", "0:a"])
        cmd.extend(["-af", filtergraph])
        cmd.extend(["-c:a", audio_codec_arg] + audio_quality_args)
    else:
        # Process default audio track
        cmd.extend(["-map", f"0:{config.audio_stream_index}"])
        cmd.extend(["-af", filtergraph])
        cmd.extend(["-c:a", audio_codec_arg] + audio_quality_args)

    # Copy other streams (subtitles, etc.)
    cmd.extend(["-map", "0:s?", "-c:s", "copy"])

    cmd.append(str(output_path))

    subprocess.run(cmd, check=True, capture_output=True)

