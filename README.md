# Telegram Bot with AI Memory & Persona Management

A sophisticated Telegram bot that uses AI personas, memory management, and multiple AI services to create engaging, context-aware conversations in group chats.

## 🚀 Features

- **AI-Powered Personas**: Multiple distinct AI personalities with unique voices and expertise
- **Memory Integration**: Remembers past conversations using Mem0 for contextual responses
- **Multi-Service AI**: Combines OpenAI GPT, Grok, and other AI services
- **Real-time Query Handling**: Processes fact-based queries with up-to-date information
- **Intelligent Reactions**: Context-aware responses to group messages
- **Topic Initiation**: Proactively starts engaging conversations
- **Persona Stickiness**: Maintains character consistency across conversations
- **Firestore Integration**: Persistent message storage and retrieval

## 🏗️ Architecture

```
src/
├── core_logic/
│   ├── response_logic.py    # Main response handling logic
│   ├── memory.py           # Memory management with Mem0
│   └── llm_personas.py     # Persona management system
├── services/
│   ├── openai_chat.py      # OpenAI API integration
│   ├── grok_chat.py        # Grok API integration
│   ├── fetch_db.py         # Database operations
│   └── state_manager.py    # State management
├── workers/
│   ├── brain.py            # Core processing worker
│   └── sender.py           # Message sending worker
└── config/
    └── settings.py         # Configuration management
```

## 🛠️ Setup

### Prerequisites

- Python 3.8+
- Telegram Bot Token
- OpenAI API Key
- Grok API Key
- Mem0 API Key
- Google Cloud Firestore credentials

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd telegram_bot_tg
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Environment Setup**
Create a `.env` file in the root directory:
```env
# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_GROUP_ID=your_group_id

# AI Services
OPENAI_API_KEY=your_openai_api_key
GROK_API_KEY=your_grok_api_key
MEM0_API_KEY=your_mem0_api_key

# Google Cloud (for Firestore)
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/service-account.json
```

4. **Configure Settings**
Update `config/settings.py` with your specific configuration:
```python
APP_CONFIG = {
    'telegram_group_id': 'your_group_id',
    'sender_bot_users': ['bot_username'],
    'response_context_messages': 10,
    # ... other settings
}
```

5. **Setup Personas**
Create persona embeddings for better matching:
```bash
python -c "from src.core_logic.llm_personas import PersonaManager; pm = PersonaManager(); pm.generate_embeddings()"
```

## 🎭 Persona System

The bot includes multiple AI personas, each with unique characteristics:

- **Crypto OG**: Experienced blockchain enthusiast
- **DeFi Degen**: High-risk DeFi trader
- **NFT Collector**: Digital art and collectibles expert
- **Tech Minimalist**: Privacy and security focused
- **Community Builder**: Engagement and networking specialist
- **Meme Lord**: Humor and viral content creator
- **Data Analyst**: Numbers and analytics focused
- **Venture Capitalist**: Investment and funding expert
- **Developer**: Technical implementation specialist
- **Enthusiast**: General crypto enthusiast

Each persona has:
- Unique voice and tone
- Specialized expertise areas
- Distinct communication patterns
- Emoji usage preferences

## 🧠 Memory System

The bot uses Mem0 for advanced memory management:

### Memory Functions

- **`get_memory_context(query)`**: Retrieves relevant past interactions
- **`add_to_memory(content, role)`**: Stores new interactions
- **`handle_memory(query, type)`**: Handles both query and response storage

### Memory Types

- **Query Memory**: Searches for relevant context before responding
- **Response Memory**: Stores bot responses for future reference
- **Context Integration**: Automatically adds memory context to all AI prompts

## 🔄 Core Logic Flow

### 1. Message Triage
```python
# Messages are categorized into:
- PERSONA_OPINION: Regular group interactions
- REALTIME_QUERY: Fact-based queries
- TOPIC_INITIATION: Conversation starters
```

### 2. Response Generation
```python
# Three main handlers:
- handle_reaction(): Persona-based responses
- handle_realtime_query(): Fact gathering + humanization
- handle_initiation(): Topic generation
```

### 3. Memory Integration
```python
# Before each AI call:
memory_context = get_memory_context(message)
prompt = f"##0. Previous chat Context: {memory_context}\n{main_prompt}"

# After response generation:
add_to_memory(user_message, "user")
add_to_memory(bot_response, "assistant")
```

## 🚀 Usage

### Start the Bot
```bash
python -m src.main
```

### Test Memory System
```bash
python memory_test.py
```

### Monitor Logs
The bot provides detailed logging for:
- Message processing
- Persona selection
- Memory operations
- AI service calls
- Error handling

## 📊 Configuration Options

### Response Settings
```python
'response_context_messages': 10,  # Number of messages for context
'max_tokens': 60,                 # AI response length limit
'persona_stickiness_duration': 180 # Persona consistency window (seconds)
```

### Memory Settings
```python
'memory_search_limit': 5,         # Number of relevant memories to retrieve
'memory_user_id': 'telegram_bot'  # Unique identifier for bot memory
```

## 🔧 Advanced Features

### Persona Stickiness
- Maintains character consistency for 3 minutes
- 15% bonus to recently used personas
- Prevents rapid personality switching

### Humanization Pipeline
- Raw AI responses → Grok fact gathering → OpenAI humanization
- Removes formal language and AI-speak
- Adds natural conversation patterns

### Quote Removal
- Automatically removes surrounding quotes from responses
- Regex pattern: `r'^"(.*)"$'`
- Preserves internal quotations

### Error Handling
- Graceful fallbacks for AI service failures
- Memory operation error recovery
- Comprehensive logging for debugging

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Troubleshooting

### Common Issues

**Memory API Errors**
```bash
# Check API key configuration
echo $MEM0_API_KEY

# Verify memory client initialization
python -c "from src.core_logic.memory import memory_client; print('Memory client OK')"
```

**Persona Embeddings Missing**
```bash
# Generate embeddings
python -c "from src.core_logic.llm_personas import PersonaManager; PersonaManager().generate_embeddings()"
```

**Firestore Connection Issues**
```bash
# Verify credentials
export GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
```

### Debug Mode
Enable detailed logging by setting:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review logs for error details
3. Create an issue with detailed information
4. Include relevant configuration (without API keys)

---

**Note**: This bot is designed for educational and experimental purposes. Ensure compliance with Telegram's Terms of Service and applicable regulations when deploying. 