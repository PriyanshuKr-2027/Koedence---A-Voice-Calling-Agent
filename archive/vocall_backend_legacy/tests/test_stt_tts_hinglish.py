import pytest
import base64
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech
from app.services.emotion.text_signal import analyze_text_emotion


@pytest.mark.asyncio
async def test_stt_sarvam_hinglish_routing():
    """Verify that language='hi' or 'hinglish' routes to Sarvam AI Saarika v2."""
    mock_audio = b"fake_wav_data"
    api_keys = {"sarvam": "test_sarvam_key"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"transcript": "main samajh gaya, let me check that for you"}
        mock_post.return_value = mock_response

        # Test language = 'hi'
        res_hi = await transcribe_audio(mock_audio, "hi", api_keys)
        assert res_hi == "main samajh gaya, let me check that for you"

        # Verify endpoint and headers
        mock_post.assert_called()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.sarvam.ai/speech-to-text"
        assert call_args[1]["headers"]["api-subscription-key"] == "test_sarvam_key"

        # Test language = 'hinglish'
        mock_post.reset_mock()
        res_hinglish = await transcribe_audio(mock_audio, "hinglish", api_keys)
        assert res_hinglish == "main samajh gaya, let me check that for you"
        assert mock_post.call_args[0][0] == "https://api.sarvam.ai/speech-to-text"


@pytest.mark.asyncio
async def test_stt_groq_whisper_routing():
    """Verify that English / default language routes to Groq Whisper large-v3."""
    mock_audio = b"fake_wav_data"
    api_keys = {"groq": "test_groq_key"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"text": "Hello, how can I help you today?"}
        mock_post.return_value = mock_response

        res = await transcribe_audio(mock_audio, "en", api_keys)
        assert res == "Hello, how can I help you today?"

        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.groq.com/openai/v1/audio/transcriptions"
        assert call_args[1]["headers"]["Authorization"] == "Bearer test_groq_key"
        assert call_args[1]["data"]["model"] == "whisper-large-v3"


@pytest.mark.asyncio
async def test_tts_hume_routing():
    """Verify provider='hume' with emotion_state routes to Hume Octave 2."""
    voice_config = {"provider": "hume", "voice_id": "test_hume_voice"}
    api_keys = {"hume": "test_hume_key"}
    emotion_state = {"valence": 0.8, "arousal": 0.6, "dominant": "joy"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"hume_audio_bytes"
        mock_post.return_value = mock_response

        audio = await synthesize_speech("Hello!", voice_config, api_keys, emotion_state)
        assert audio == b"hume_audio_bytes"

        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.hume.ai/v0/tts"
        assert call_args[1]["headers"]["X-Hume-Api-Key"] == "test_hume_key"


@pytest.mark.asyncio
async def test_tts_sarvam_routing():
    """Verify provider='sarvam' routes to Sarvam AI Bulbul v2."""
    voice_config = {"provider": "sarvam", "voice_id": "meera"}
    api_keys = {"sarvam": "test_sarvam_key"}
    raw_audio = b"sarvam_audio_bytes"
    audio_b64 = base64.b64encode(raw_audio).decode()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"audios": [audio_b64]}
        mock_post.return_value = mock_response

        audio = await synthesize_speech("Aapka swagat hai", voice_config, api_keys)
        assert audio == raw_audio

        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.sarvam.ai/text-to-speech"
        assert call_args[1]["headers"]["api-subscription-key"] == "test_sarvam_key"


@pytest.mark.asyncio
async def test_tts_cartesia_default_routing():
    """Verify default / provider='cartesia' routes to Cartesia Sonic-2."""
    voice_config = {"provider": "cartesia", "voice_id": "sonic_voice_id"}
    api_keys = {"cartesia": "test_cartesia_key"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"cartesia_pcm_bytes"
        mock_post.return_value = mock_response

        audio = await synthesize_speech("Default English speech", voice_config, api_keys)
        assert audio == b"cartesia_pcm_bytes"

        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.cartesia.ai/tts/bytes"
        assert call_args[1]["headers"]["X-API-Key"] == "test_cartesia_key"


def test_text_signal_hinglish_note():
    """Verify text_signal module contains the required language note."""
    import inspect
    source = inspect.getsource(analyze_text_emotion)
    assert "transcript may be in English, Hindi, or Hinglish — analyze regardless of language." in source
