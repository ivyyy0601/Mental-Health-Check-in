from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os
import time
import json
import requests
import anthropic 
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError
# ❗ Daytona SDK 导入 - 必须安装 'pip install daytona' ❗
try:
    from daytona import Daytona, DaytonaConfig
except ImportError:
    # 如果 SDK 未安装，使用 MOCK 类避免程序崩溃
    class Daytona:
        def __init__(self, *args, **kwargs): pass
        def create(self, **kwargs): return self
        def process(self): return self
        def delete(self): pass
    class DaytonaConfig:
        def __init__(self, *args, **kwargs): pass
    print("[Daytona SDK MOCK] Daytona SDK not found. Using MOCK objects.")
    

# --- Initialization ---
# 从 .env 文件中加载环境变量
load_dotenv()

# 从环境变量中读取 API 密钥和配置
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# --- Tigris S3 Configuration ---
TIGRIS_S3_ENDPOINT = os.getenv("TIGRIS_S3_ENDPOINT")
TIGRIS_BUCKET = os.getenv("TIGRIS_BUCKET")
TIGRIS_ACCESS_KEY = os.getenv("TIGRIS_ACCESS_KEY")
TIGRIS_SECRET_KEY = os.getenv("TIGRIS_SECRET_KEY")

# ❗ Daytona API KEY ❗
DAYTONA_API_KEY = os.getenv("DAYTONA_API_KEY")


app = Flask(__name__)

# 初始化 Anthropic Client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# 初始化 Daytona Client (用于动态沙箱)
daytona_client = None
if DAYTONA_API_KEY:
    try:
        config = DaytonaConfig(api_key=DAYTONA_API_KEY)
        daytona_client = Daytona(config)
        print("[Daytona Client] SDK initialized for dynamic sandbox creation.")
    except Exception as e:
        print(f"[Daytona Client ERROR] Failed to initialize Daytona SDK: {e}")


# 初始化 Tigris S3 Client 
s3 = None
try:
    if not TIGRIS_S3_ENDPOINT or not TIGRIS_ACCESS_KEY or not TIGRIS_SECRET_KEY:
        raise ValueError("Tigris S3 credentials or endpoint are missing.")
        
    # S3 endpoint URL handling for Boto3 (ensures https:// prefix)
    s3_endpoint_url = TIGRIS_S3_ENDPOINT
    if not TIGRIS_S3_ENDPOINT and not TIGRIS_S3_ENDPOINT.startswith("http"):
        s3_endpoint_url = "https://" + TIGRIS_S3_ENDPOINT

    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint_url,
        aws_access_key_id=TIGRIS_ACCESS_KEY,
        aws_secret_access_key=TIGRIS_SECRET_KEY,
        config=Config(s3={"addressing_style": "virtual"}),
    )
    print("[Tigris S3] Client initialized successfully.")
    
except Exception as e:
    print(f"[Tigris S3 ERROR] Client initialization failed: {e}")


# --- Tigris RAG Helper ---
def get_recent_checkins(user_id, days=7):
    if not s3 or not TIGRIS_BUCKET:
        print("[Tigris RAG] S3 client or bucket is missing. Skipping history retrieval.")
        return [], []

    threshold = int(time.time()) - (days * 24 * 3600)
    
    prompt_history = []
    display_history = []
    prefix = f"mood_checkins/{user_id}/"

    try:
        response = s3.list_objects_v2(Bucket=TIGRIS_BUCKET, Prefix=prefix)
        if 'Contents' in response:
            for item in response['Contents']:
                try:
                    key_parts = item['Key'].split('_')
                    if len(key_parts) > 1:
                        file_timestamp = int(key_parts[-1].split('.')[0]) // 1000
                    else:
                        continue
                        
                    if file_timestamp >= threshold:
                        obj = s3.get_object(Bucket=TIGRIS_BUCKET, Key=item['Key'])
                        data = json.loads(obj['Body'].read().decode('utf-8'))
                        
                        prompt_history.append(f"Date: {data.get('date')}, Mood: {data.get('emotion_label')}, Text: {data.get('input_text')[:50]}...")
                        display_history.append(data)
                        
                except Exception as e:
                    print(f"[Tigris RAG ERROR] Failed to parse/fetch object {item['Key']}: {e}")
                    continue

    except Exception as e:
        print(f"[Tigris RAG ERROR] Failed to list objects: {e}")

    display_history.sort(key=lambda x: x['timestamp'], reverse=True)
    prompt_history.sort(reverse=True) 

    return prompt_history, display_history


def call_claude(text, user_id):
    # RAG Step: Get historical context
    prompt_history, _ = get_recent_checkins(user_id)
    history_context = "\n".join(prompt_history) if prompt_history else "No recent check-in history available."
    lang_instruction = "written in English."


    prompt = f"""
You are a gentle, calm, and supportive Mental Health Check-in Assistant.
Your goal is to analyze the user's current mood and provide a personalized, safe response.

--- CONTEXT: RECENT CHECK-INS (For Personalized Advice) ---
The user's mood history from the last 7 days is provided below. Use it to give more relevant advice.
{history_context}
---------------------------------------------------------

User's current input:
{text}

Please output a JSON with the following fields:
- emotion_label: A brief English mood word (e.g., "sad", "anxious", "angry", "neutral")
- risk_level: Integer from 0 to 3 (0=Safe, 3=High Risk)
- text_reply: A kind, supportive reply and specific advice {lang_instruction}. DO NOT mention you are an AI or bot.
- voice_script: A short, natural, conversational script suitable for being read aloud for comfort, {lang_instruction}.

Output ONLY the JSON object, with no extra text.
"""

    try:
        resp = client.messages.create(
            model="claude-3-haiku-20240307", 
            max_tokens=400,
            temperature=0.4,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
    except anthropic.APIStatusError as e:
        print(f"Anthropic API Error: {e}")
        error_msg = "Sorry, the AI service is currently unresponsive. Please try again later."
        return "error", 0, error_msg, None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        error_msg = "An unexpected error occurred. Please check your network and configuration."
        return "error", 0, error_msg, None


    content = resp.content[0].text
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        print("JSON Parsing failed, Claude returned:", content)
        data = {
            "emotion_label": "neutral",
            "risk_level": 0,
            "text_reply": "Thank you for sharing your feelings. It sounds like you are carrying a lot right now. Remember to take a deep breath and give yourself a moment of rest.",
            "voice_script": "I hear you. Thank you for reaching out. Please take a deep breath, you don't have to carry this alone. How about doing a little something just for yourself tonight?"
        }

    emotion_label = data.get("emotion_label", "neutral")
    try:
        risk_level = int(data.get("risk_level", 0))
    except ValueError:
        risk_level = 0
        
    text_reply = data.get("text_reply", "")
    voice_script = data.get("voice_script", "")

    if risk_level >= 3:
        text_reply += "\n\n⚠️ Safety Alert: If you are having strong thoughts of self-harm, please reach out immediately to a trusted person, a mental health professional, or a local emergency hotline. This is not a medical service and is not a substitute for professional help."

    return emotion_label, risk_level, text_reply, voice_script


def save_to_tigris(user_id, text, emotion_label, risk_level, text_reply):
    # Persist the check-in record to the Tigris S3 bucket.
    if not s3:
        print("[Tigris ERROR] S3 client failed to initialize. Skipping save.")
        return
    
    if not TIGRIS_BUCKET:
        print("[Tigris ERROR] No bucket configured. Skipping save.")
        return

    checkin_doc = {
        "id": f"{user_id}_{int(time.time() * 1000)}",
        "user_id": user_id,
        "input_text": text,
        "emotion_label": emotion_label,
        "risk_level": risk_level,
        "model_reply": text_reply,
        "timestamp": int(time.time()),
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    key = f"mood_checkins/{user_id}/{checkin_doc['id']}.json"

    try:
        s3.put_object(
            Bucket=TIGRIS_BUCKET,
            Key=key,
            Body=json.dumps(checkin_doc, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        print(f"[Tigris] Saved checkin to bucket as {key}")
    except EndpointConnectionError as e:
        print(f"[Tigris ERROR] Connection error. Check TIGRIS_S3_ENDPOINT: {e}")
    except ClientError as e:
        print(f"[Tigris ERROR] S3 Client Error (Auth/Bucket): {e}")
    except Exception as e:
        print(f"[Tigris ERROR] An unexpected error occurred during S3 save: {e}")

def call_elevenlabs(voice_script):
    # Calls the ElevenLabs API to convert voice_script to an audio URL, using the fixed voice.
    if not voice_script or not ELEVENLABS_API_KEY:
        print("[ElevenLabs MOCK] API Key is missing or script is empty. Skipping TTS.")
        return None

    # Fixed Voice ID: Bella (Calm Female)
    VOICE_ID = "UgBBYS2sOqTuMpoF3BR0"
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": voice_script,
        "model_id": "eleven_multilingual_v2", 
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.7
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code != 200:
            print("ElevenLabs Error:", resp.status_code, resp.text)
            return None

        os.makedirs("static", exist_ok=True)
        filename = f"static/audio_{int(time.time())}.mp3"
        with open(filename, "wb") as f:
            f.write(resp.content)

        audio_url = "/" + filename
        print(f"[ElevenLabs] Audio saved to: {audio_url}")
        return audio_url
    except requests.exceptions.RequestException as e:
        print(f"ElevenLabs request failed: {e}")
        return None


# --- NEW ROUTE: Retrieve History for Display ---
@app.route("/history", methods=["GET"])
def get_history_data():
    """Returns the user's recent check-in history for UI display."""
    user_id = request.args.get("user_id", "demo-user-1")
    # We only need the display data here (the second returned value)
    _, history_data = get_recent_checkins(user_id)
    
    return jsonify(history_data)
    
# --- Routes ---

@app.route("/")
def index():
    """Renders the main page."""
    # This route is used by the client to load the HTML/frontend.
    return render_template("index.html")

@app.route("/checkin", methods=["POST"])
def checkin():
    """Handles the user's emotion check-in request."""
    data = request.get_json()
    user_id = data.get("user_id", "demo-user-1") 
    text = data.get("text")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    # 1. Call Claude for analysis and script (language is fixed to English)
    emotion_label, risk_level, text_reply, voice_script = call_claude(text, user_id)
    
    if emotion_label == "error":
        return jsonify({
            "emotion_label": "error",
            "risk_level": 0,
            "text_reply": text_reply, 
            "audio_url": None
        })

    # ❗ CHECK FOR HIGH RISK AND INITIATE DAYTONA SANDBOX ❗
    if risk_level >= 3 and daytona_client:
        print("[Daytona Sandbox] HIGH RISK DETECTED. Initiating secure isolation...")
        
        # ❗ THE CORE API CODE STARTS HERE ❗
        # This is the Python code that will run inside the isolated Daytona Sandbox
        analysis_code = f"""
import json
import time
# 导入只有在沙箱中才允许运行的敏感或高危库 (例如：高级风险模型)
# import advanced_risk_model 

# 1. 接收输入数据 (从主应用传入的文本和风险等级)
user_data = {{"user_id": "{user_id}", "input_text": "{text}", "initial_risk": {risk_level}, "timestamp": {int(time.time())}}}

# 2. 模拟运行深度分析 / 高危操作
#    - 模拟加载高级模型，进行深度风险计算 (如果模型存在)
#    - 耗时操作，例如：result = advanced_risk_model.run(user_data['input_text'])
import random
final_risk_score = user_data['initial_risk'] + random.uniform(0.1, 0.5)

# 3. 确定最终建议和状态
if final_risk_score >= 3.0:
    recommendation = "Immediate professional contact required."
else:
    recommendation = "System monitoring initiated."

# 4. 返回结构化结果给主应用 (通过标准输出)
result_payload = {{
    "status": "isolated_analysis_complete", 
    "recommendation": recommendation,
    "final_risk_score": round(final_risk_score, 2),
    "processed_by": "Daytona Sandbox"
}}

print(json.dumps(result_payload))
"""
        # ❗ THE CORE API CODE ENDS HERE ❗

        try:
            # 1. Create a new, isolated Sandbox instance
            sandbox = daytona_client.create(name=f"risk-{user_id}-{int(time.time())}", 
                                            timeout_seconds=60)
            
            # 2. Run the analysis code securely inside the isolated Sandbox
            response = sandbox.process.code_run(analysis_code)
            
            # 3. Check for success and process results
            if response.exit_code == 0 and response.result:
                try:
                    sandbox_result = json.loads(response.result)
                    print(f"[Daytona Sandbox] Analysis complete. Recommendation: {sandbox_result.get('recommendation')}")
                    # 可以将 recommendation 附加到 text_reply 中
                    text_reply += f"\n\n[System Alert] Deep Scan Result: {sandbox_result.get('recommendation')} (Score: {sandbox_result.get('final_risk_score')})"
                except json.JSONDecodeError:
                    print(f"[Daytona Sandbox ERROR] Invalid JSON output: {response.result}")
                    
            else:
                print(f"[Daytona Sandbox ERROR] Sandbox failed. Exit Code: {response.exit_code}. Error: {response.result}")

            # 4. Clean up the disposable sandbox
            sandbox.delete()
            print(f"[Daytona Sandbox] Isolation complete. Sandbox deleted.")

        except Exception as e:
            print(f"[Daytona Sandbox ERROR] Failed to create/run sandbox: {e}")
            
        # Append message to user that system is taking extra steps
        text_reply += "\n\n🚨 Our system has initiated a secondary, isolated analysis due to the severity level. We are processing your submission with utmost priority."
    # -------------------------------------------------------------


    # 2. Persist to Tigris S3
    save_to_tigris(user_id, text, emotion_label, risk_level, text_reply)

    # 3. Get audio URL from ElevenLabs (voice is fixed to Bella)
    audio_url = call_elevenlabs(voice_script) if voice_script else None

    return jsonify({
        "emotion_label": emotion_label,
        "risk_level": risk_level,
        "text_reply": text_reply,
        "audio_url": audio_url
    })


if __name__ == "__main__":
    app.run(debug=True)