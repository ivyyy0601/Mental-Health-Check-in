# Secure AI Mental Health Companion

## 🚀 Project Overview
The Secure AI Mental Health Companion is a full-stack web application that provides empathetic, personalized, and safe emotional support. It integrates Tigris S3 for persistent RAG memory and Daytona Sandbox for high-risk isolation, forming a responsible mental-health AI system.

## 🎯 Elevator Pitch
This application provides supportive emotional check-ins through text or voice input and returns responses in both text and comforting audio (via ElevenLabs). It uses Tigris S3 for RAG-based historical context and automatically routes high-risk inputs to a disposable Daytona Sandbox for isolated deep analysis—ensuring proactive safety and operational security.

## ✨ Core Features
### 🎙️ Multi-Modal Input & Output
- Text or voice emotional check-ins
- Supportive text + voice responses (ElevenLabs)

### 🧠 RAG-Powered Personalization
- Retrieves past 7 days of history from Tigris S3
- Claude generates memory-aware advice

### 🚨 High-Risk Safety Isolation
- If risk_level ≥ 3:
  - Detects danger
  - Spins up a Daytona disposable sandbox
  - Runs isolated deep analysis

### 💾 Persistent Emotional History
- Stores all check-ins in Tigris S3  
- History displayed in UI

### 🌡️ Emotional Analysis
- Claude 3 Haiku performs mood classification and risk scoring (0–3)

## 📐 Architecture & Technology Stack
| Layer | Technology | Role |
|-------|------------|------|
| Secure Environment | Daytona | Sandbox isolation for high-risk inputs |
| AI / Logic | Flask, Claude 3 Haiku | Analysis, risk detection, generation |
| Data / RAG | Tigris S3 + Boto3 | Persistent history + RAG context |
| Experience | ElevenLabs TTS | Converts text to comforting audio |
| Frontend | HTML, Tailwind, JS | UI, voice input, history display |

## ⚙️ Setup & Installation
### 1. Install Dependencies
```
pip install flask python-dotenv anthropic boto3 daytona requests
```

### 2. Create .env File
```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=sk_...

TIGRIS_S3_ENDPOINT=https://t3.storage.dev
TIGRIS_BUCKET=your-bucket
TIGRIS_ACCESS_KEY=tid_...
TIGRIS_SECRET_KEY=tsec_...

DAYTONA_API_KEY=dtn_...
```

### 3. Run the Application
```
python app.py
```

## 🔐 Demonstrating Proactive Safety (Daytona Sandbox)
High‑risk input triggers sandbox isolation:

```
[Daytona Sandbox] HIGH RISK DETECTED. Initiating secure isolation...
[Daytona Sandbox] Analysis complete. Recommendation: Immediate professional contact required.
[Daytona Sandbox] Isolation complete. Sandbox deleted.
```

## ✅ Summary
This project combines multi-modal empathy, RAG memory, and isolated sandbox safety to create a secure, responsible emotional-support AI companion.
