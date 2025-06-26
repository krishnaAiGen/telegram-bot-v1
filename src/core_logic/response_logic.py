# src/core_logic/response_logic.py
import json
import re

from config.settings import APP_CONFIG
from src.services.openai_chat import get_llm_response
from src.services.fetch_db import get_last_100_message_texts
from src.core_logic.llm_personas import PersonaManager
from src.services.state_manager import StateManager
from src.services.openai_chat import get_embedding
from src.services.fetch_db import get_last_n_messages_as_text
from src.services.grok_chat import get_grok_response
from src.core_logic.memory import get_memory_context, add_to_memory


import time
import os
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


embeddings_path = os.path.join('data', 'persona_embeddings.json')
if os.path.exists(embeddings_path):
    with open(embeddings_path, 'r', encoding='utf-8') as f:
        PERSONA_EMBEDDINGS = json.load(f)
else:
    PERSONA_EMBEDDINGS = {}
    print("WARNING: 'persona_embeddings.json' not found. Persona matching will be disabled.")


    
    
async def humanize_grok_response(grok_data: str, original_question: str, persona_manager: PersonaManager, db) -> str:
    """
    Takes raw data from Grok and uses OpenAI to transform it into a natural,
    human-sounding chat message.
    """
    print(f"[BRAIN] Humanizing Grok data: '{grok_data[:50]}...'")
    
    chosen_persona = persona_manager.get_random_persona()
    if not chosen_persona:
        return f"{grok_data}"

    persona_profile = f"Role: {chosen_persona.get('role', '')}. Voice: {chosen_persona.get('signature_voice', {}).get('tone', '')}."
    print(f"[BRAIN] Using persona: {chosen_persona['persona_name']} with profile: {persona_profile}")

    # Get last n messages from the group
    try:
        last_n_messages = await get_last_n_messages_as_text(str(APP_CONFIG['telegram_group_id']), int(os.getenv("RESPONSE_CONTEXT_MESSAGES", "4")), db)
        print(f"-----last_n_messages-----: {last_n_messages}")
    except Exception as e:
        print(f"[BRAIN] Error getting last messages: {e}")
        last_n_messages = "No recent context available"

    # Humanizer prompt
    humanizer_prompt = f"""
        # CONTEXT
        You're in a group chat sharing something interesting. Sound natural and conversational, but vary your style.

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

        7. **RAW TEXT OUTPUT ONLY** - No quotes, headers, or formatting

        ---
        YOUR RESPONSE:
        """
    
    try:
        # max_token = np.random.randint(10, 25)
        # humanized_reply = await get_llm_response(humanizer_prompt, max_tokens=30)
        humanized_reply = await get_grok_response(humanizer_prompt)
        print(f"-----humanized_reply-----: {humanized_reply}")
        
        # Remove double quotes if the entire message is wrapped in them
        humanized_reply = re.sub(r'^"(.*)"|"(.*)$|^"(.*)', r'\1\2\3', humanized_reply.strip().lower())
        
        # Check if the response is valid
        if not humanized_reply or humanized_reply.strip() == "":
            raise ValueError("Empty response from LLM")
            
        print(f"[BRAIN] Successfully humanized response: '{humanized_reply}'")
        return humanized_reply
        
    except Exception as e:
        print(f"[BRAIN] Humanizer failed with error: {e}. Falling back to raw data.")
        # Return the raw grok data without the "I found this update:" prefix
        return grok_data

async def handle_realtime_query(message, sender_queue, persona_manager: PersonaManager, db):
    """
    Handles real-time queries by first getting brief facts from Grok, then
    humanizing the response with OpenAI.
    """
    print(f"[BRAIN] Routing message ID {message.id} to Grok for fact-gathering.")
    
    # Get memory context for the query
    memory_context = get_memory_context(message.text)
    print(f"-----memory_context for realtime query and for message {message.text}-----: {memory_context}")
    
    grok_prompt = f"""##0. Previous chat Context. Use anything from this context if needed to make your response more natural: {memory_context} Regarding the user's query: '{message.text}'.
Provide the single most important fact or data point as a raw, unformatted sentence. Be extremely brief. Do not explain.
"""
    
    raw_grok_data = await get_grok_response(grok_prompt)
    
    if "Error:" in raw_grok_data:
        print(f"[BRAIN] Grok service failed. Aborting response. Reason: {raw_grok_data}")
        return

    final_reply = await humanize_grok_response(raw_grok_data, message.text, persona_manager, db)
    print(f"-----fact:raw grok data-----: {raw_grok_data}")
    print(f"-----fact:humanized reply-----: {final_reply}")

    # Check for errors in final reply before sending to Telegram
    if "Error:" in final_reply or "error" in final_reply.lower() or not final_reply.strip():
        print(f"[BRAIN] Error in final reply, not sending to Telegram: {final_reply}")
        return

    # Add query and response to memory
    add_to_memory(message.text, "user")
    add_to_memory(final_reply, "assistant")

    user_to_send = APP_CONFIG['sender_bot_users'][0]
    
    await sender_queue.put({"message": final_reply, "telegram_user": user_to_send})
    print(f"[BRAIN] Queued final (humanized) response for message {message.id}.")


async def handle_reaction(message, sender_queue, persona_manager: PersonaManager, state_manager: StateManager, db):
    """Generates a reaction using a two-stage process with persona stickiness."""
    text = message.text
    print(f"[BRAIN] Reacting to Message ID: {message.id} | Text: '{text[:40]}...'")
    
    # Get memory context for the message
    memory_context = get_memory_context(text)
    print(f"-----memory_context for reaction and for message {text}-----: {memory_context}")
    
    conversation_context = await get_last_n_messages_as_text(str(APP_CONFIG['telegram_group_id']), APP_CONFIG['response_context_messages'], db)
    
    # --- STAGE 1: LOCAL PERSONA MATCHING ---
    chosen_persona_name = None
    if PERSONA_EMBEDDINGS:
        print("[BRAIN] Stage 1: Finding best persona using local embeddings...")
        user_embedding = await get_embedding(text)
        
        if user_embedding:
            persona_names = list(PERSONA_EMBEDDINGS.keys())
            persona_vectors = list(PERSONA_EMBEDDINGS.values())
            
            user_vector = np.array(user_embedding).reshape(1, -1)
            scores = cosine_similarity(user_vector, np.array(persona_vectors))[0]

            # --- CLEANED UP: Persona Stickiness Logic ---
            last_persona_info = state_manager.get_last_persona_info()
            last_persona_name = last_persona_info.get("name")
            last_persona_time = last_persona_info.get("timestamp", 0)

            if last_persona_name and (time.time() - last_persona_time < 180): # 3 minute window
                try:
                    idx = persona_names.index(last_persona_name)
                    bonus = 1.15 # 15% bonus to make it more impactful
                    print(f"[BRAIN] Applying stickiness bonus of {bonus} to '{last_persona_name}'")
                    scores[idx] *= bonus
                except ValueError:
                    print(f"[BRAIN] Warning: Last used persona '{last_persona_name}' not found in embeddings.")
                    pass

            best_match_index = np.argmax(scores)
            chosen_persona_name = persona_names[best_match_index]
            print(f"[BRAIN] Best local match found: '{chosen_persona_name}' with score {scores[best_match_index]:.4f}")
    
    if not chosen_persona_name:
        random_persona = persona_manager.get_random_persona()
        if not random_persona:
            print("ERROR: Could not get a random persona. Aborting reaction.")
            return
        chosen_persona_name = random_persona['persona_name']
        print(f"[BRAIN] Local matching failed. Falling back to random persona: '{chosen_persona_name}'")

    # --- STAGE 2: FOCUSED LLM CALL ---
    chosen_persona = persona_manager.get_persona_by_name(chosen_persona_name)
    if not chosen_persona:
        print(f"ERROR: Could not find full profile for persona '{chosen_persona_name}'")
        return

    persona_profile = (
    f"Role: {chosen_persona.get('role', '')}. "
    f"Voice: {chosen_persona.get('signature_voice', {}).get('tone', '')}. "
    f"Expertise: {', '.join(chosen_persona.get('expertise', []))}. "
    f"Traits: {', '.join(chosen_persona.get('key_traits', []))}.")


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
**User's Message:** "{text}"
**Your Task:** Generate the most humanly authentic response possible from your assigned persona, strictly following all directives above. Your entire output MUST be only the raw text of the reply. Do NOT use JSON or any other formatting.

---
YOUR REPLY (RAW TEXT ONLY):
"""

    reply = await get_llm_response(super_prompt, max_tokens=60)
    reply = re.sub(r'^"(.*)"$', r'\1', reply.strip())

    print(f"-----Reaction: persona-based-reply-----: {reply}")
    reply = await humanize_grok_response(reply, text, persona_manager, db)
    print(f"-----Reaction:persona-based-reply-after-humanization-----: {reply}")

    # Check for various error patterns before sending to Telegram
    if "Error:" in reply or "error" in reply.lower() or not reply.strip():
        print(f"Error in LLM response, not sending to Telegram: {reply}")
        return
    
    # Add message and response to memory
    add_to_memory(text, "user")
    add_to_memory(reply, "assistant")
    
    # --- CLEANED UP: Update the state with the chosen persona ---
    state_manager.update_last_persona_info(chosen_persona_name)
    print(f"[BRAIN] Updated last used persona to '{chosen_persona_name}'")
    
    user_to_send = chosen_persona.get("telegram_user") or APP_CONFIG['sender_bot_users'][0]
    
    await sender_queue.put({"message": reply, "telegram_user": user_to_send})
    print(f"Brain: Queued reply from {chosen_persona_name} for message {message.id}.")
    
async def handle_initiation(sender_queue, persona_manager: PersonaManager, state_manager: StateManager, db):
    """Generates a new, non-repetitive, engaging topic and queues it for sending."""
    print("[BRAIN] Handling topic initiation...")
    
    messages = await get_last_100_message_texts(str(APP_CONFIG['telegram_group_id']), db)
    if not messages:
        print("[BRAIN] No chat history found to analyze. Skipping initiation.")
        return

    chat_history = "\n".join(messages)
    
    # Get memory context for topic initiation
    memory_context = get_memory_context("topic initiation conversation starter")
    print(f"-----memory_context for topic initiation-----: {memory_context}")

    # FULL ORIGINAL PROMPT - keeping everything the same
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
        # Get the LLM response (should be JSON)
        response_str = await get_llm_response(reengagement_prompt, max_tokens=300)
        print(f"[BRAIN] Raw LLM response: {response_str}")
        
        # Now humanize it using humanize_grok_response
        humanized_response = await humanize_grok_response(response_str, "topic initiation conversation starter", persona_manager, db)
        print(f"[BRAIN] Humanized response: {humanized_response}")
        
        # Try to parse the humanized response as JSON first
        try:
            data = json.loads(humanized_response)
        except json.JSONDecodeError:
            # If humanized response is not JSON, try the original response
            print("[BRAIN] Humanized response is not JSON, trying original response")
            data = json.loads(response_str)
        
        topic = data.get("topic_summary")
        question = data.get("question")
        
        if not (topic and question):
            raise ValueError("Missing required keys in JSON response")
            
        print(f"[BRAIN] Parsed topic: '{topic}', question: '{question}'")
        
        # If we used the original JSON, now humanize just the question
        if humanized_response != response_str and '"' in humanized_response:
            # The humanized response was JSON, use it as is
            final_question = question
        else:
            # The humanized response was casual text, use that as the question
            final_question = humanized_response
            
        print(f"[BRAIN] Final question to send: '{final_question}'")
        
    except json.JSONDecodeError as e:
        print(f"[BRAIN] JSON parsing failed completely. Error: {e}")
        print(f"[BRAIN] Original response: {response_str}")
        print(f"[BRAIN] Humanized response: {humanized_response}")
        
        # If humanized response looks like a question, use it directly
        if "?" in humanized_response or any(word in humanized_response.lower() for word in ["what", "how", "why", "when", "where", "who"]):
            topic = f"humanized_topic_{int(time.time())}"
            final_question = humanized_response
            print(f"[BRAIN] Using humanized response as direct question")
        else:
            print(f"[BRAIN] Complete fallback - skipping initiation")
            return
        
    except Exception as e:
        print(f"[BRAIN] Initiation failed with error: {e}")
        return

    # --- MEMORY CHECK ---
    if state_manager.is_topic_recently_initiated(topic):
        print(f"[BRAIN] Topic '{topic}' was initiated recently. Skipping to avoid repetition.")
        return

    # If the topic is new, log it before sending
    state_manager.log_initiated_topic(topic)
    print(f"[BRAIN] New unique topic identified: '{topic}'. Logging and preparing to send.")
    
    # Add the initiated topic to memory
    add_to_memory(final_question, "assistant")
    
    # Pick a random persona to ask the question
    persona = persona_manager.get_random_persona()
    if not persona: 
        print("[BRAIN] No persona available for initiation")
        return
    
    await sender_queue.put({"message": final_question, "telegram_user": persona.get("telegram_user")})
    print(f"[BRAIN] Queued re-engagement question from {persona['persona_name']}.")

async def handle_scheduled_link_post(link_info: dict, persona_manager: PersonaManager, db):
    """
    Handles the entire intelligent process of posting a scheduled link.
    Returns a dictionary for the sender_queue or None on failure.
    """
    link = link_info.get("link")
    description = link_info.get("description")
    if not link or not description:
        return None

    print(f"[SCHEDULER] Processing link: {link}")

    # 1. Content-Aware Persona Selection
    # We use the link's description to find the best persona
    print("[SCHEDULER] Finding best persona for this content...")
    description_embedding = await get_embedding(description)
    chosen_persona_name = None
    if PERSONA_EMBEDDINGS and description_embedding:
        persona_names = list(PERSONA_EMBEDDINGS.keys())
        persona_vectors = list(PERSONA_EMBEDDINGS.values())
        
        desc_vector = np.array(description_embedding).reshape(1, -1)
        scores = cosine_similarity(desc_vector, np.array(persona_vectors))
        
        best_match_index = np.argmax(scores)
        chosen_persona_name = persona_names[best_match_index]
        print(f"[SCHEDULER] Best persona match: '{chosen_persona_name}'")
    
    if not chosen_persona_name:
        chosen_persona = persona_manager.get_random_persona()
    else:
        chosen_persona = persona_manager.get_persona_by_name(chosen_persona_name)
    
    if not chosen_persona:
        print("[SCHEDULER] ERROR: Could not select a persona. Aborting.")
        return None

    # 2. Dynamic Contextualization
    print("[SCHEDULER] Fetching recent chat for context...")
    chat_context = await get_last_n_messages_as_text(str(APP_CONFIG['telegram_group_id']), 5, db)

    persona_profile = f"Role: {chosen_persona.get('role', '')}. Voice: {chosen_persona.get('signature_voice', {}).get('tone', '')}."

    # 3. Build and Execute the Link Sharing Prompt
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
    
    crafted_message = await get_llm_response(link_sharing_prompt, max_tokens=100)

    if "Error:" in crafted_message or not crafted_message.strip():
        print(f"[SCHEDULER] ERROR: LLM failed to craft a message for the link.")
        return None

    return {
        "message": crafted_message,
        "telegram_user": chosen_persona.get("telegram_user")
    }