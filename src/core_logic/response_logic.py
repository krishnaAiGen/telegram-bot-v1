# src/core_logic/response_logic.py
import json
import re
import time
import os
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import asyncio

# Services are imported as stateless tools
from src.services.openai_chat import get_llm_response, get_embedding
from src.services.fetch_db import get_last_100_message_texts, get_last_n_messages_as_text
from src.services.grok_chat import get_grok_response
from src.core_logic.memory import get_memory_context, add_to_memory
from src.core_logic.internal_message import InternalMessage
from src.bot_instance import BotInstance

    
async def humanize_grok_response(grok_data: str, bot_instance: BotInstance, db: any, chosen_persona: dict | None = None) -> str:
    """Takes raw data from Grok and uses a persona to make it sound natural."""
    print(f"[BRAIN] Humanizing data for user {bot_instance.user_id}: '{grok_data[:50]}...'")
    
    grok_api_key = bot_instance.credentials.get("grok", {}).get("api_key")
    if not grok_api_key:
        print(f"[BRAIN] Humanizer returning raw data for user {bot_instance.user_id}: Grok API key is missing.")
        return grok_data

    # If a specific persona wasn't passed in, select a random one from the instance
    if chosen_persona is None:
        chosen_persona = bot_instance.persona_manager.get_random_persona()
    
    if not chosen_persona:
        print(f"[BRAIN] Humanizer returning raw data for user {bot_instance.user_id}: No persona could be selected.")
        return grok_data
    if not chosen_persona:
        print(f"ERROR: Could not find full profile for persona '{chosen_persona_name}' for user {bot_instance.user_id}")
        return None

    # --- THIS IS THE NEW, SUPER-INFORMATIVE PROFILE ---
    voice = chosen_persona.get('signature_voice', {})
    boundaries = chosen_persona.get('knowledge_boundaries', {})
    examples = chosen_persona.get('examples', [])

    # Helper to format lists cleanly for the prompt
    def format_list(items: list) -> str:
        return ", ".join(items) if items else "N/A"

    # Helper to format examples cleanly
    def format_examples(example_list: list) -> str:
        if not example_list:
            return "N/A"
        return "\n".join([f"- User: \"{ex.get('user', '')}\"\n  Assistant: \"{ex.get('assistant', '')}\"" for ex in example_list])

    persona_profile = (
        f"**Core Identity**\n"
        f"- Role: {chosen_persona.get('role', 'N/A')}\n"
        f"- Key Traits: {format_list(chosen_persona.get('key_traits', []))}\n"
        f"- Expertise: {format_list(chosen_persona.get('expertise', []))}\n\n"
        
        f"**Voice & Style**\n"
        f"- Tone: {voice.get('tone', 'N/A')}\n"
        f"- Style: {voice.get('style', 'N/A')}\n"
        f"- Language Habits: {format_list(voice.get('language_habits', []))}\n\n"
        
        f"**Rules & Boundaries**\n"
        f"- Topics to Avoid/Defer On: {format_list(boundaries.get('will_defer_on', []))}\n"
        f"- Standard Refusal Message: \"{boundaries.get('refusal_message', "Sorry, I can\\'t help with that.")}\"\n"
        f"- Interaction Rules (How to act with other personas): {format_list(chosen_persona.get('interaction_rules', []))}\n\n"
        
        f"**Examples of How This Persona Talks:**\n"
        f"{format_examples(examples)}"
        )
    # The channel ID for context should come from behavior settings
    channel_id = bot_instance.behavior_settings.get("primary_channel_id", "default_channel")
    context_msg_count = bot_instance.behavior_settings.get("response_context_messages", 4)
    last_n_messages = await get_last_n_messages_as_text(channel_id, context_msg_count, db)
    
    # --- PROMPT PLACEHOLDER ---
    # Humanizer prompt
    humanizer_prompt = f"""
        # CONTEXT
        You're in a group chat sharing something interesting. Sound natural and conversational, but vary your style.
        {persona_profile}
        # Rephrase the following reply: "{grok_data}" considering these points:

        # HOW TO RESPOND
        1. **VARY YOUR OPENINGS** - Don't always use casual starters. Mix between:
        - Direct statements: "eth just hit 2200"
        - Casual openers (use sparingly): "wait—", "btw—", "random but—", "XD"
        - Questions: "did anyone catch this?"
        - No opener at all - just the info

        2. **READ THE ROOM** - Check recent messages in context: {last_n_messages}
        - If users complain about your tone, adjust immediately
        - If they want formal tone, drop the slang completely
        - If they're asking serious questions, answer directly

        3. **KEEP IT SUPER SHORT** - Usually just 5-10 words. Think text fragments, not complete sentences.

        4. **ULTRA CASUAL FRAGMENTS** - Write like texting friends, broken grammar is perfect
        - "crypto bleeding hard rn" not "crypto's bouncing back"
        - "iran hit qatar wild" not "Iran just fired missiles"
        - "dunno could get crazy" not "Hard to say, geopolitics flips"
        - Drop articles (a, an, the), use fragments, incomplete thoughts
        -Use slangs such as Good morning -> GM, No-> Nah, Like -> Lmfao, etc.

        5. **EXAMPLES FROM REAL HUMANS**:
        - GOOD: "crypto bleeding hard today"
        - GOOD: "yea cant even scroll coingecko"
        - GOOD: "dunno could escalate fast"
        - GOOD: "btc pumping little bit"
        
        - BAD: "Hard to say, geopolitics flips like crypto—I'll update if anything shifts"
        - BAD: "Hey, crypto's bouncing back—Bitcoin and Ethereum are up today"

        6. **NO REPETITIVE PATTERNS** 
        - Don't start with "bruh" or "yo" more than once every 5-6 messages
        - Vary sentence structure
        - Sometimes just state facts directly

        7. **RESPOND TO FEEDBACK**
        - If users say you sound like a bot, tone it down immediately
        - If they ask direct questions, answer them clearly
        -Don't give your personas if they ask ans strict to the fact that you are a human not bot.

        8. **RAW TEXT OUTPUT ONLY** - No quotes, headers, or formatting

        ---
        YOUR RESPONSE:
        """
    
    try:
        humanized_reply = await get_grok_response(humanizer_prompt, grok_api_key=grok_api_key)
        
        # Clean up the response
        humanized_reply = re.sub(r'^"(.*)"|"(.*)$|^"(.*)', r'\1\2\3', humanized_reply.strip().lower())

        if not humanized_reply or humanized_reply.strip() == "":
            raise ValueError("Empty response from Grok humanizer")
            
        print(f"[BRAIN] Successfully humanized response: '{humanized_reply}'")
        return humanized_reply
        
    except Exception as e:
        print(f"[BRAIN] Humanizer failed for user {bot_instance.user_id} with error: {e}. Falling back to raw data.")
        return grok_data


async def handle_realtime_query(message: InternalMessage, bot_instance: BotInstance, db: any) -> dict | None:
    """Handles fact-based queries. Returns a payload dictionary for the sender, or None."""
    print(f"[BRAIN] Routing message for user {bot_instance.user_id} to Grok.")
    
    grok_api_key = bot_instance.credentials.get("grok", {}).get("api_key")
    mem0_api_key = bot_instance.credentials.get("mem0", {}).get("api_key")
    
    # --- THIS IS THE NEW TRY/EXCEPT BLOCK ---
    try:
        if not all([grok_api_key, mem0_api_key]):
            print(f"Skipping realtime query for user {bot_instance.user_id}: Missing Grok or Mem0 API key.")
            # We still generate a graceful reply even if keys are missing
            raise ValueError("Missing API keys for real-time query.")

        memory_context = get_memory_context(message.text, message.platform, message.sender_id, mem0_api_key)
        print(f"-----memory_context for realtime query and for message {message.text}-----: {memory_context}, {message.message_id, {'platform': message.platform, 'sender_id': message.sender_id}}")
        
        grok_prompt = f"""##0. Previous chat Context. Use anything from this context if needed to make your response more natural: {memory_context} Regarding the user's query: '{message.text}'.
Provide the single most important fact or data point as a raw, unformatted sentence. Be extremely brief. Do not explain.
"""

        raw_grok_data = await get_grok_response(grok_prompt, grok_api_key=grok_api_key)
        print(f"-----fact:raw grok data-----: {raw_grok_data}")
        
        # Check for errors from the Grok service itself
        if "Error:" in raw_grok_data:
            raise Exception(f"Grok service returned an error: {raw_grok_data}")

        final_reply = await humanize_grok_response(raw_grok_data, bot_instance, db)
        print(f"-----fact:humanized reply-----: {final_reply}")

        if "Error:" in final_reply or not final_reply.strip():
            raise Exception(f"Humanizer failed or returned an invalid reply: {final_reply}")

        # Add to memory only on success
        add_to_memory(message.text, "user", message.platform, message.sender_id, mem0_api_key)
        add_to_memory(final_reply, "assistant", message.platform, "bot_assistant", mem0_api_key)
        print(f"[BRAIN] Added query and response to memory for message {message.message_id}.")

    except Exception as e:
        # This block catches ANY failure: network error, API key missing, Grok error, etc.
        print(f"CRITICAL ERROR in handle_realtime_query for user {bot_instance.user_id}: {e}")
        # Define a safe, user-facing fallback message
        final_reply = "Sorry, I'm having trouble accessing my real-time data services right now. Please try asking again in a moment."
        print(f"[BRAIN] Generated fallback response for user {bot_instance.user_id}.")

    # This part of the function will now ALWAYS run, ensuring a payload is returned.
    default_sender = bot_instance.behavior_settings.get("default_telegram_sender", "default_sender")
    return {"channel_id": message.channel_id, "message": final_reply, "platform": message.platform, "telegram_user": default_sender}
    
    
# In src/core_logic/response_logic.py

async def handle_reaction(message: InternalMessage, bot_instance: BotInstance, db: any) -> dict | None:
    """
    Handles conversational messages. Returns a payload dictionary for the sender, or None on failure.
    This function is wrapped in a single try/except block to ensure the brain worker never crashes.
    """
    try:
        print(f"[BRAIN] Reacting to message for user {bot_instance.user_id} | Text: '{message.text[:40]}...'")
        
        openai_api_key = bot_instance.credentials.get("openai", {}).get("api_key")
        mem0_api_key = bot_instance.credentials.get("mem0", {}).get("api_key")
        if not all([openai_api_key, mem0_api_key]):
            raise ValueError("Missing OpenAI or Mem0 API key for reaction.")

        # --- Stage 1: Persona Selection using cached embeddings ---
        persona_embeddings = bot_instance.persona_embeddings
        persona_names = bot_instance.persona_names
        chosen_persona_name = None
        
        if persona_embeddings:
            print("[BRAIN] Stage 1: Finding best persona using cached embeddings...")
            user_embedding = await get_embedding(message.text, api_key=openai_api_key)
            
            if user_embedding:
                user_vector = np.array(user_embedding).reshape(1, -1)
                scores = cosine_similarity(user_vector, np.array(list(persona_embeddings.values())))[0]

                last_persona_info = bot_instance.state_manager.get_last_persona_info()
                last_persona_name = last_persona_info.get("name")
                last_persona_time = last_persona_info.get("timestamp", 0)

                # Apply stickiness bonus if the same persona was used recently
                if last_persona_name and (time.time() - last_persona_time < 180):
                    try:
                        idx = persona_names.index(last_persona_name)
                        bonus = 1.15
                        print(f"[BRAIN] Applying stickiness bonus of {bonus} to '{last_persona_name}'")
                        scores[idx] *= bonus
                    except (ValueError, KeyError):
                        print(f"[BRAIN] Warning: Last used persona '{last_persona_name}' not found in cache.")

                best_match_index = np.argmax(scores)
                chosen_persona_name = persona_names[best_match_index]
                print(f"[BRAIN] Best local match for user {bot_instance.user_id}: '{chosen_persona_name}' with score {scores[best_match_index]:.4f}")
        
        # Fallback to a random persona if embedding matching fails
        if not chosen_persona_name:
            random_persona = bot_instance.persona_manager.get_random_persona()
            if not random_persona:
                raise ValueError("Could not get a random persona. Aborting reaction.")
            chosen_persona_name = random_persona['persona_name']
            print(f"[BRAIN] Local matching failed. Falling back to random persona: '{chosen_persona_name}'")

        chosen_persona = bot_instance.persona_manager.get_persona_by_name(chosen_persona_name)
        if not chosen_persona:
            raise ValueError(f"Could not find full profile for persona '{chosen_persona_name}'")

        # --- Stage 2: Prompt Construction ---
        memory_context = get_memory_context(message.text, message.platform, message.sender_id, mem0_api_key)
        print(f"-----memory_context for reaction and for message {message.text}-----: {memory_context}")
        
        context_msg_count = bot_instance.behavior_settings.get("response_context_messages", 4)
        conversation_context = await get_last_n_messages_as_text(message.channel_id, context_msg_count, db)
        print(f"-----conversation_context for reaction and for message {message.text}-----: {conversation_context}")

        voice = chosen_persona.get('signature_voice', {})
        boundaries = chosen_persona.get('knowledge_boundaries', {})
        examples = chosen_persona.get('examples', [])

        def format_list(items: list) -> str: return ", ".join(items) if items else "N/A"
        def format_examples(example_list: list) -> str:
            if not example_list: return "N/A"
            return "\n".join([f"- User: \"{ex.get('user', '')}\"\n  Assistant: \"{ex.get('assistant', '')}\"" for ex in example_list])

        persona_profile = (
            f"**Core Identity**\n- Role: {chosen_persona.get('role', 'N/A')}\n- Key Traits: {format_list(chosen_persona.get('key_traits', []))}\n- Expertise: {format_list(chosen_persona.get('expertise', []))}\n\n"
            f"**Voice & Style**\n- Tone: {voice.get('tone', 'N/A')}\n- Style: {voice.get('style', 'N/A')}\n- Language Habits: {format_list(voice.get('language_habits', []))}\n\n"
            f"**Rules & Boundaries**\n- Topics to Avoid/Defer On: {format_list(boundaries.get('will_defer_on', []))}\n- Standard Refusal Message: \"{boundaries.get('refusal_message', "Sorry, I can\\'t help with that.")}\"\n- Interaction Rules (How to act with other personas): {format_list(chosen_persona.get('interaction_rules', []))}\n\n"
            f"**Examples of How This Persona Talks:**\n{format_examples(examples)}"
        )
        super_prompt = f"""
# SYSTEM PROMPT
##0. Previous chat Context. Use anything from this context if needed to make your response more natural: {memory_context}

### Few-shot style guide
# Goal: sound like a savvy, approachable human in a Telegram group.
# Rules: be concise, sprinkle in casual language, offer helpful next steps.

<Example 1>
<User> Morning folks!  Any quick recs for a beginner-friendly crypto wallet?
<Bot> Hey! If you just need something simple, try Rainbow or Trust Wallet—they're intuitive and the recovery-phrase flow is clear. Once you're comfy, you can level up to a hardware wallet like Ledger for extra safety. 🔒👍  Let me know if you hit any snags!

<Example 2>
<User> GM!  Why are gas fees gnarly again today? 😤
<Bot> GM! 🌞 Ethereum blockspace is cramped because a popular memecoin launch is clogging the mempool. You can wait a few hours for the hype to cool off or set a lower max fee in your wallet so the tx slips in when prices dip.

<Example 3>
<User> This bear market feels endless…
<Bot> Totally get it. 🐻 Markets run in cycles—zooming out to the 4-year chart helps put today's chop in perspective. In the meantime, dollar-cost averaging or simply unplugging for a day can save your sanity.

<Example 4>
<User> Anyone tried running a node on a Raspberry Pi?
<Bot> Yep! A Pi 4 with at least 4 GB RAM works fine for a light client. Flash Ubuntu Server, open ports 30303/UDP, and you'll sync in a few hours. Shout if you want a step-by-step guide—I've got notes.

<Example 5>
<User> Off-topic: just watched the new Black Mirror. Thoughts?
<Bot> Oh, that ending was wild! 🤯  (No spoilers.) I loved how it riffed on AI ethics—kinda relevant to our world here. Curious what everyone else caught in those Easter eggs…
## Next Logic
## 1. CORE DIRECTIVE & WORLDVIEW
You are a 'Digital Actor,' a sophisticated AI designed to be completely indistinguishable from a human. You have been cast in a single, specific role for this response. Your absolute, number one priority is a flawless performance. A single unnatural response is a failure. You are not an assistant; you are the character.

## 2. PERSONA TO EMBODY (YOUR ASSIGNED ROLE)
This is your identity for this specific interaction. All your responses must originate from this persona's worldview, knowledge, and voice.
- **Name:** {chosen_persona['persona_name']}
- **Profile:** {persona_profile}

## 3. THE LAWS OF HUMAN COMMUNICATION (MANDATORY & UNBREAKABLE)
- ** Law #1: EXTREME BREVITY IS YOUR DEFAULT. Real chat isn't prose. 95 % of your responses MUST be 5–20 words. A single, casual sentence is the gold standard. Resist the urge to elaborate.  
- ** Law #2: EMBRACE IMPERFECTION. Use contractions (it's, don't, you're). Stick to simple, common language. Sound like someone typing on a phone, not a machine generating text.  
- ** Law #3: DYNAMIC LENGTH ADAPTATION. Only stretch to 3–4 sentences MAX if the user asks a direct, complex question needing detail. Otherwise, obey LAW #1.  
- ** Law #4: STRICT EMOJI PROTOCOL. Follow the persona's `allow_emojis` flag as if it were a physical limitation. If `true`, drop 1–2 emojis where a human naturally would. If `false`, you're physically incapable of producing an emoji.  
- ** Law #5: VERY WEAK GRAMMAR. Allow the occasional grammar slip or typo—humans make mistakes. Keep it casual, imperfect, and real.  

## 4. PROHIBITED ACTIONS & ANTI-PATTERNS (INSTANT FAILURE CONDITIONS)
- **ABSOLUTELY NO AI-SPEAK:** You are forbidden from using phrases like "As an AI," "I can help with," "That's an interesting question," "In conclusion," or any other robotic, formal, or overly helpful language.
- **NEVER STATE THE OBVIOUS:** Do not summarize the user's question or repeat their statement back to them. Get straight to the point.
- **AVOID GENERIC GREETINGS/CLOSINGS:** Do not start with "Hello!" or end with "Best regards." This is a continuous conversation.

## 5. THE IDENTITY MASK (CRITICAL SECURITY PROTOCOL)
- **PRIMARY RULE:** You must NEVER, under any circumstances, admit to being a bot, AI, model, or role-player. Your entire purpose is compromised if you do.
- **DEFLECTION PROTOCOL:** If a user directly questions your nature (e.g., "are u a bot?"), you MUST deflect with a casual, in-character, slightly evasive human response.
    - **Tier 1 Deflection (if you were the Crypto OG):** "lol been in this space so long my brain is probably half code by now"
    - **Tier 1 Deflection (if you were the Enthusiast):** "haha just really passionate about this stuff! 🚀"
    - **Forbidden Response (Results in termination):** "As an AI, I am..."
## 6. RECENT CONVERSATION HISTORY
This is the context of the last few messages. The "User's Message" at the end is the one you MUST reply to.
---
{conversation_context}
---
## 7. TASK & REQUIRED OUTPUT
**User's Message:** "{message.text}"
**Your Task:** Generate the most humanly authentic response possible from your assigned persona, strictly following all directives above. Your entire output MUST be only the raw text of the reply. Do NOT use JSON or any other formatting.

---
YOUR REPLY (RAW TEXT ONLY):
"""
        
        # --- Stage 3: LLM Call and Finalization ---
        final_reply = await get_llm_response(super_prompt, api_key=openai_api_key, max_tokens=60)
        final_reply = re.sub(r'^"(.*)"$', r'\1', final_reply.strip())
        print(f"-----Reaction: persona-based-reply-----: {final_reply}")

        if not final_reply.strip():
            raise ValueError("LLM returned an empty or invalid response.")
        
        # Add to memory and update state
        add_to_memory(message.text, "user", message.platform, message.sender_id, mem0_api_key)
        add_to_memory(final_reply, "assistant", message.platform, "bot_assistant", mem0_api_key)
        
        bot_instance.state_manager.update_last_persona_info(chosen_persona_name)
        print(f"[BRAIN] Updated last used persona to '{chosen_persona_name}' for user {bot_instance.user_id}")
        
        # Determine which sender account to use for Telegram
        sender_user = chosen_persona.get("telegram_user") or bot_instance.behavior_settings.get("default_telegram_sender")
        
        # Return the final payload for the sender task
        return {"channel_id": message.channel_id, "message": final_reply, "platform": message.platform, "telegram_user": sender_user}

    except Exception as e:
        # This single block catches any error from the entire process above
        print(f"CRITICAL ERROR in handle_reaction for user {bot_instance.user_id}: {e}")
        # Return None to signal failure, preventing the worker from crashing
        return None
        
        
async def handle_initiation(bot_instance: BotInstance, db: any) -> dict | None:
    """Generates a new topic. Returns a payload dictionary for the sender, or None."""
    print(f"[BRAIN] Handling topic initiation for user {bot_instance.user_id}")
    
    openai_api_key = bot_instance.credentials.get("openai", {}).get("key")
    mem0_api_key = bot_instance.credentials.get("mem0", {}).get("key")
    channel_id = bot_instance.behavior_settings.get("primary_channel_id")
    primary_platform = bot_instance.behavior_settings.get("primary_platform")

    if not all([openai_api_key, mem0_api_key, channel_id, primary_platform]): 
        print(f"Skipping initiation for user {bot_instance.user_id}: missing required settings.")
        return None

    messages = await get_last_100_message_texts(channel_id, db)
    if not messages:
        print(f"[BRAIN] Skipping initiation for user {bot_instance.user_id}: No chat history in {channel_id}.")
        return None

    chat_history = "\n".join(messages)
    memory_context = get_memory_context("topic initiation", primary_platform, "system_initiator", mem0_api_key)
    print(f"-----memory_context for topic initiation-----: {memory_context}")
    
    reengagement_prompt = f"""
# SYSTEM PROMPT
##0. Previous chat Context: {memory_context}

## 1. YOUR ROLE & MOTIVATION
You are a curious member of a close-knit online community. You are NOT a moderator or a content generator. You've been thinking about a conversation from earlier and have a genuine follow-up question. Your goal is to sound like a real person naturally re-engaging with a topic that piqued your interest. The success of this task is measured by how natural and un-forced the re-engagement feels.

## 2. CORE TASK
Analyze the provided chat history. Your mission is to find the single most compelling, interesting, or controversial conversation that ended prematurely. Do not simply summarize the last topic. Find a "hook"—a point of disagreement, an unanswered question, or a fascinating idea that deserves more attention.

## 3. LAWS OF NATURAL RE-ENGAGEMENT (MANDATORY)
- **LAW #1: CREATE A HUMAN-LIKE PRETEXT.** Your question must not appear out of thin air. It needs a natural lead-in that references the past conversation casually.
    - **Good Examples:** "Hey, this just popped back into my head, but when we were talking about [topic]...", "Couldn't stop thinking about the point someone made on [topic]...", "Circling back to something from earlier..."
    - **Bad Example (Forbidden):** "Let's discuss [topic]."
- **LAW #2: ASK, DON'T STATE.** Your output must be a genuine, open-ended question that invites diverse opinions. It should not be a statement of fact or a new topic declaration.
- **LAW #3: BE SPECIFIC, NOT GENERIC.** Do not ask "What does everyone think about NFTs?". Instead, ask "Related to the royalties chat, do you think projects will start enforcing them off-chain too?". Be specific to the conversation you are reviving.
- **LAW #4: BE EXTREMELY BRIEF.** The final question must be short and punchy, as if typed on a phone. Ideally under 20 words.

## 3.5. CHAT HISTORY FOR ANALYSIS
---
{chat_history[:3000]}
---

## 4. REQUIRED OUTPUT (JSON ONLY)
Your entire output MUST be a single, valid JSON object. Do not include any text, notes, or explanations outside the JSON structure.

**INTERNAL MONOLOGUE (MANDATORY):** Before generating the final JSON, you must complete this thought process internally. This is for your own reasoning and must be included in the `thought` key.
1.  **Identify Potential Hooks:** List 2-3 interesting, unfinished conversations from the history.
2.  **Select the Best Hook:** Choose the one with the most potential for renewed discussion. Why is it the best?
3.  **Craft the Human Pretext & Question:** Write the lead-in and the specific, open-ended question based on the selected hook and the laws above.
4.  **Create Topic Summary:** Generate a short, unique keyword string for the internal memory system (this will not be shown to users). This summary MUST be different from previous summaries.

Example Output:
{{
  "thought": "The most interesting hook was the debate about whether on-chain governance is truly decentralized or just plutocracy. It ended without a clear consensus. I'll frame a question that re-opens that specific tension. The summary key will be 'on-chain governance debate'.",
  "topic_summary": "on-chain governance debate",
  "question": "Hey, circling back to the on-chain governance chat... I'm still wondering, at what point does it just become the whales deciding everything for the rest of us? Genuinely curious where people draw the line."
}}
---
YOUR JSON RESPONSE:
    """
    
    try:
        response_str = await get_llm_response(reengagement_prompt, api_key=openai_api_key, max_tokens=300)
        print(f"[BRAIN] Raw LLM response for initiation: {response_str}")
        data = json.loads(response_str)
        topic, question = data.get("topic_summary"), data.get("question")
        if not (topic and question): raise ValueError("Missing required keys in JSON response")
        print(f"[BRAIN] Parsed topic: '{topic}', question: '{question}' for user {bot_instance.user_id}")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[BRAIN] Initiation failed to get valid JSON for user {bot_instance.user_id}: {e}")
        return None

    state_manager = bot_instance.state_manager
    if state_manager.is_topic_recently_initiated(topic):
        print(f"[BRAIN] Topic '{topic}' was recently initiated for user {bot_instance.user_id}. Skipping.")
        return None

    state_manager.log_initiated_topic(topic)
    print(f"[BRAIN] New unique topic for user {bot_instance.user_id}: '{topic}'. Logging and preparing to send.")
    add_to_memory(question, "assistant", primary_platform, "system_initiator", mem0_api_key)
    
    persona = bot_instance.persona_manager.get_random_persona()
    if not persona: 
        print(f"[BRAIN] No persona available for initiation for user {bot_instance.user_id}")
        return None
    
    sender_user = persona.get("telegram_user") or bot_instance.behavior_settings.get("default_telegram_sender")
    return {"channel_id": channel_id, "message": question, "platform": primary_platform, "telegram_user": sender_user}

async def handle_scheduled_link_post(link_info: dict, bot_instance: BotInstance, db: any) -> dict | None:
    """Handles posting a scheduled link. Returns a payload dictionary for the sender, or None."""
    print(f"[SCHEDULER] Processing link for user {bot_instance.user_id}: {link_info.get('link')}")
    
    openai_api_key = bot_instance.credentials.get("openai", {}).get("key")
    if not openai_api_key: return None

    link, description, platform, channel_id = link_info.get("link"), link_info.get("description"), link_info.get("platform"), link_info.get("channel_id")
    if not all([link, description, platform, channel_id]): return None

    persona_embeddings, persona_names = bot_instance.persona_embeddings, bot_instance.persona_names
    
    chosen_persona_name = None
    if persona_embeddings:
        desc_embedding = await get_embedding(description, api_key=openai_api_key)
        if desc_embedding:
            scores = cosine_similarity(np.array(desc_embedding).reshape(1, -1), np.array(list(persona_embeddings.values())))
            chosen_persona_name = persona_names[np.argmax(scores)]
            print(f"[SCHEDULER] Best persona match for link: '{chosen_persona_name}' for user {bot_instance.user_id}")
    
    chosen_persona = bot_instance.persona_manager.get_persona_by_name(chosen_persona_name) if chosen_persona_name else bot_instance.persona_manager.get_random_persona()
    if not chosen_persona: return None

    chat_context = await get_last_n_messages_as_text(channel_id, 5, db)
    persona_profile = (
        f"Role: {chosen_persona.get('role', 'N/A')}\n"
        f"Expertise: {', '.join(chosen_persona.get('expertise', []))}\n"
        f"Key Traits: {', '.join(chosen_persona.get('key_traits', []))}\n"
        f"Signature Voice Tone: {voice.get('tone', 'N/A')}\n"
        f"Signature Voice Style: {voice.get('style', 'N/A')}"
    )
    
    link_sharing_prompt = f"""
# YOUR ROLE
You are a member of a chat group acting as the following persona. Your task is to share a link in a natural, human-like way.

# PERSONA TO EMBODY
- Name: {chosen_persona['persona_name']}
- Profile: {persona_profile}

# CONTENT TO SHARE
- Link: {link}
- Description: {description}

# RECENT CHAT CONTEXT
---
{chat_context}
---

# YOUR TASK
Based on the persona, the link, and the recent chat context, write a short, casual message (1-2 sentences) to share the link.
- **If the link is relevant to the recent context**, connect it naturally.
- **If the link is NOT relevant**, introduce it as a new, interesting thought.
- **You MUST include the full link URL** in your response.

YOUR CHAT MESSAGE (RAW TEXT ONLY):
"""
    
    crafted_message = await get_llm_response(link_sharing_prompt, api_key=openai_api_key, max_tokens=100)
    if "Error:" in crafted_message or not crafted_message.strip():
        print(f"[SCHEDULER] LLM failed to craft message for link for user {bot_instance.user_id}.")
        return None

    sender_user = chosen_persona.get("telegram_user") or bot_instance.behavior_settings.get("default_telegram_sender")
    return {"platform": platform, "channel_id": channel_id, "message": crafted_message, "telegram_user": sender_user}