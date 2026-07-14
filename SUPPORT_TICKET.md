# Ticket for newo.ai support (copy-paste and send)

**Subject: Intermittent one-way audio on inbound calls + SMS sender not configured (project: naf / X-Park, AI phone +380947120827)**

Hello,

We have four issues, listed by severity.

## 1) One-way audio on inbound calls (critical, losing leads)

On multiple inbound calls the caller's audio never reaches VAD/ASR — there are **zero `user_speech_started` events for the entire call** while the caller is audibly speaking (we have a caller-side recording as proof: the agent's greeting and both "Ви ще тут?" prompts are heard, the caller replies 4 times, the platform detects nothing).

Examples:
- 2026-07-14 07:41:38 UTC, callSid `71a89e5a-7f57-11f1-be13-02420aef3420`, callId `e9dc3bf1-7d80-4ab0-b8bb-7e25cfcd2741`, 52 s — zero inbound speech events (caller-side recording available);
- 2026-07-14 07:59:26 UTC — 59 s call, zero inbound speech events; plus at least 4 more calls the same morning;
- 2026-07-06 — nearly all inbound calls that day (22+) had zero recognized caller speech.

Telephony provider: telnyx. Voice mode: voice-to-voice (openai). Please check the inbound RTP/media path, and whether the Krisp voice filter (`voice_filter_krisp_noise_suppression_level = 100`) could be muting the caller stream intermittently.

## 2) SMS to clients are not delivered

- `twilio_messenger / sms_connector`: `phone_number` is empty, `country_code = US`;
- `newo_sms / newo_sms_connector`: `agent_phone_number` is empty.

The platform logs "SMS was sent" but clients report nothing arrives (e.g. 2026-07-07 16:34 UTC to a UA mobile). What sender (number / alphanumeric ID) must be configured to deliver SMS to Ukrainian mobile numbers? Is Viber Business messaging available as an alternative channel for Ukraine?

## 3) Question: transcription pipeline in voice-to-voice mode

With `voice_mode = voice-to-voice`, `v2v_mode = openai`, `v2v_mode_user_stt = None`, `is_v2v_user_stt_fallback_enabled = True` (deepgram): which component actually produces user transcriptions? Many Russian-language utterances are transcribed as garbled text. Also, what are the intended semantics of `v2v_ignore_first_client_chunks_seconds = 5.0` — is it safe to lower it so the caller's first words are not lost?

## 4) Framework bug report (naf 4.6.0)

The email-collection canned phrase (in `prompt_get_explicit_constraints_voice`) and the hardcoded "email request" SMS template (first item in `_sendSMSInformationGetInformationAllowedToBeSentSkill`) remain active even when `project_attributes_setting_email_send_information_enabled = False`. Result: on 2026-07-10 18:02 UTC an SMS asking the user to confirm their email was sent although the email channel is disabled.

Thank you!
