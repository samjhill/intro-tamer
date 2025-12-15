"""FFmpeg filtergraph building and rendering."""

import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class RenderConfig(BaseModel):
    """Configuration for audio rendering."""

    intro_start: float
    intro_end: float
    gain_db: float  # Negative = reduce loudness
    fade_ms: int = 120
    audio_stream_index: int = 0
    all_audio_tracks: bool = False


def build_audio_filtergraph(config: RenderConfig) -> str:
    """
    Build FFmpeg audio filtergraph for intro ducking.

    Uses volume filter with enable expression and afade for smooth transitions.
    This approach splits the processing into: fade down, apply gain, fade up.

    Args:
        config: Render configuration

    Returns:
        Filtergraph string
    """
    fade_seconds = config.fade_ms / 1000.0
    gain_db = config.gain_db
    
    # Calculate fade boundaries
    fade_in_end = config.intro_start + fade_seconds
    fade_out_start = config.intro_end - fade_seconds
    
    # Use a filter chain that:
    # 1. Applies volume reduction only during the intro period (with enable)
    # 2. Uses afade for smooth transitions at boundaries
    #
    # Note: We apply the volume filter with enable='between()' to only affect the intro,
    # and use afade filters for the fade transitions. However, afade affects the entire
    # stream from that point, so we need to be careful.
    #
    # Better approach: Use volume with enable for the main reduction, and handle
    # fades separately. Actually, let's use a simpler approach with just volume
    # and enable, then add fades using volume expressions.
    
    # Simple approach: volume with enable expression for main reduction
    # Then add afade filters for transitions (but these affect the whole stream)
    # 
    # Actually, the best approach is to use volume filter with a time-based expression
    # that includes the fades. Let's use a simpler expression that FFmpeg can handle.
    
    filtergraph = f"volume={gain_db}dB:enable='between(t,{fade_in_end},{fade_out_start})'"
    
    # Add fade transitions using afade, but we need to be careful about timing
    # Actually, let's combine everything into one volume expression that's simpler
    gain_multiplier = 10 ** (gain_db / 20.0)
    
    # Use a complex filtergraph that splits audio into segments
    # This is more reliable than time-based volume expressions
    # 
    # Split audio into 3 parts:
    # [0] = audio input
    # [1] = segment before intro (0 to intro_start)
    # [2] = intro segment (intro_start to intro_end) with volume reduction and fades  
    # [3] = segment after intro (intro_end to end)
    # Then concatenate [1][2][3]
    
    # Build the filtergraph string
    # aselect='between(t,0,' + str(config.intro_start) + ')' for segment 1
    # aselect='between(t,' + str(config.intro_start) + ',' + str(config.intro_end) + ')' for segment 2
    # aselect='between(t,' + str(config.intro_end) + ',999999)' for segment 3
    
    # Actually, FFmpeg filtergraph syntax for this is complex. Let's use a simpler
    # approach: use volume with a direct dB value and enable expression
    # But we need fades, so let's combine afade with volume
    
    # Use afade filters with enable expressions to limit their effect to the intro segment only
    # This is more reliable than complex volume expressions
    gain_db = config.gain_db
    
    # Apply volume reduction during intro, with fades at boundaries
    # Use afade with enable to fade down at start, volume with enable for main reduction,
    # and afade with enable to fade up at end
    
    # Calculate the exact timing for each fade
    # Fade out: from intro_start to fade_in_end (reduces volume)
    # Volume: from fade_in_end to fade_out_start (main reduction)  
    # Fade in: from fade_out_start to intro_end (increases volume back)
    
    # Use volume filter with enable for the steady intro period
    # Then use afade with enable for the fade transitions
    # But afade doesn't support enable, so we need a different approach
    
    # Better: Use volume filter with a time-based expression that includes fades
    # But make it simpler - use direct dB values with enable for the main reduction,
    # and handle fades separately
    
    # Actually, the most reliable approach: use volume with enable for main reduction,
    # and use volume expressions for the fade transitions (but these are complex)
    
    # Let's try: volume filter with enable for steady intro, and separate volume
    # filters with enable for fade transitions
    # But that requires multiple filters which is complex
    
    # Simplest working approach: Use volume with enable for the main reduction period,
    # and accept that fades might not be perfect, or use a simpler fade approach
    
    # For now, let's use volume with enable for the main reduction
    # The fades can be handled by the volume expression, but let's simplify it
    filtergraph = f"volume={gain_db}dB:enable='between(t,{fade_in_end},{fade_out_start})'"
    
    # Add fades using afade, but we need to be careful - afade affects the whole stream
    # So we'll apply afade only during the fade periods using enable... but afade doesn't support enable
    
    # Final approach: Use a volume expression that's simpler and more reliable
    # Just apply the reduction during the intro period, with simple linear fades
    gain_multiplier = 10 ** (gain_db / 20.0)
    
    # Simplified expression: apply gain_multiplier during intro, 1.0 elsewhere
    # Add linear fades at boundaries
    filtergraph = (
        f"volume="
        f"'if(between(t,{config.intro_start},{config.intro_end}),"
        f"if(lt(t,{fade_in_end}),1+({gain_multiplier}-1)*((t-{config.intro_start})/{fade_seconds}),"
        f"if(gt(t,{fade_out_start}),{gain_multiplier}+(1-{gain_multiplier})*((t-{fade_out_start})/{fade_seconds}),"
        f"{gain_multiplier})),1)':eval=frame"
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

