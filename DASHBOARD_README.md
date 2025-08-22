# AI Persona Management Dashboard

A web-based dashboard for generating and managing AI personas using your persona-management pipeline.

## Features

- **Real Persona Generation**: Integrates directly with your `persona-management` pipeline
- **Firebase Integration**: Stores generated personas and pipeline runs in Firestore
- **Simple Authentication**: JWT-based auth with demo credentials
- **Web Interface**: Clean, responsive dashboard for managing AI personas
- **Pipeline History**: Track all your persona generation runs

## Quick Start

### 1. Prerequisites

Make sure you have:
- Python 3.8+ with your virtual environment activated
- Firebase credentials configured in `data/firebase-credentials.json`
- OpenAI API key in your `.env` file
- All dependencies installed: `pip install -r requirements.txt`

### 2. Start the Dashboard

```bash
python run_dashboard.py
```

The dashboard will be available at:
- **Frontend**: http://localhost:8000/dashboard
- **API Docs**: http://localhost:8000/docs

### 3. Login

Use the demo credentials:
- **Email**: `demo@persona.ai`
- **Password**: `password`

### 4. Generate Personas

1. Enter your bot's high-level goal in the text area
2. Click "Generate AI Team"
3. Wait 30-60 seconds for the pipeline to complete
4. View and manage your generated personas

## How It Works

### Backend (FastAPI)
- **Authentication**: Simple JWT-based auth with hardcoded demo credentials
- **Pipeline Integration**: Calls your `run_persona_factory_pipeline` function directly
- **Firebase Storage**: Automatically saves all generated personas and pipeline runs
- **API Endpoints**:
  - `POST /login` - Authentication
  - `POST /generate-personas` - Run the persona generation pipeline
  - `GET /personas/library` - Get user's persona library
  - `GET /pipeline-runs` - Get pipeline run history

### Frontend (HTML/CSS/JavaScript)
- **Clean Interface**: Modern, responsive design
- **Real-time Updates**: Shows actual pipeline progress and results
- **Persona Management**: View, organize, and deploy persona teams
- **Library System**: Browse and reuse previously generated personas

### Firebase Collections
- **`pipeline_runs`**: Complete history of all generation runs
- **`personas`**: Individual persona profiles with metadata
- **`dashboard_users`**: User accounts and preferences

## Example Usage

1. **Coffee Shop Bot**: 
   ```
   I'm launching a premium coffee brand called "Aether Grind". I need a bot team for our Discord community to educate about brewing methods, discuss coffee origins, and manage weekly events.
   ```

2. **SaaS Support Bot**:
   ```
   I need a professional team for our SaaS product's Discord server. We need community management, technical support, and feature announcements.
   ```

3. **Gaming Community**:
   ```
   Create a fun, engaging team for our gaming Discord. We need event coordination, community engagement, and game-specific expertise.
   ```

## Development

### File Structure
```
dashboard/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── firebase_service.py  # Firebase integration
│   ├── auth.py             # Authentication utilities
│   └── jwt_key.py          # JWT secret key
├── frontend/
│   └── index.html          # Web dashboard
└── run_dashboard.py        # Startup script
```

### Adding Features

1. **New API Endpoints**: Add to `dashboard/backend/main.py`
2. **Frontend Updates**: Modify `dashboard/frontend/index.html`
3. **Database Schema**: Update Firebase collections as needed

## Troubleshooting

### Common Issues

1. **"Connection error"**: Make sure the backend is running on port 8000
2. **"Firebase initialization failed"**: Check your `firebase-credentials.json` path
3. **"OpenAI API error"**: Verify your OpenAI API key in `.env`
4. **"Pipeline failed"**: Check the console logs for detailed error messages

### Logs

The backend provides detailed logging:
- Pipeline execution steps
- Firebase operations
- API request/response details
- Error messages with stack traces

## Security Notes

- This is a **development/demo setup** with hardcoded credentials
- For production use:
  - Implement proper user registration/authentication
  - Use environment variables for secrets
  - Add input validation and rate limiting
  - Configure proper CORS origins

## Next Steps

- Add user registration and proper authentication
- Implement persona editing and customization
- Add deployment integration with your bot systems
- Create persona templates and presets
- Add analytics and usage tracking