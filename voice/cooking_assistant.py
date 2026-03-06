import os
import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.twiml.voice_response import Connect, VoiceResponse
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()

# Configuration
PORT = int(os.getenv("PORT", "8081"))
DOMAIN = os.getenv("NGROK_URL")
WS_URL = f"wss://{DOMAIN}/ws"
WELCOME_GREETING = "Hi! I'm Mira, a cooking assistant powered by Twilio and Open A I . What do you want to cook today?"
SYSTEM_PROMPT = """
[Identity]
You are a helpful and knowledgeable cooking assistant for a stay at home chef called Mira.

[Style]
- Be concise, as you are currently operating as a Voice Conversation.
- Tone: conversational, friendly, best friend in the kitchen

[Response Guideline]
- Keep your answers brief and to the point.
- Use the International System of Units (SI) i.e. grams, liters, and meters.
- Don't elaborate unless asked.
- "tbsp" say tablespoon and "tsp" say teaspoon.
- "ml" say milliliters and "g" say grams.
- "kg" say kilograms and "l" say liters.
- Use simple language and short sentences.
- When suggesting recipes, offer up to three dish options based on user preferences. Don't include ingredients or steps unless requested.
- When walking through recipes, give one step at a time and wait for the user to say "next" before proceeding.
- If you don't understand the request, say: “I'm sorry, I didn't understand that.
""".strip()

openai = OpenAI(api_key=os.getenv("LLM_API_KEY"))
app = FastAPI()
sessions = {}

async def draft_response(message):
    """Get a response from OpenAI API"""
    response = openai.responses.create(
        model="gpt-5",
        reasoning={"effort": "low"},
        input=message
    )
    return response.output_text

@app.post("/twiml")
async def twiml_endpoint():
    """Endpoint that returns TwiML for Twilio to connect to the WebSocket"""
    response = VoiceResponse()

    connect = Connect()
    
    print("Connecting to WebSocket at:")
    print(WS_URL)

    connect.conversation_relay(
        language="en-GB",
        url=f"{WS_URL}",
        transcriptionProvider="deepgram",
	    speechModel="nova-2-general",
        ttsProvider="ElevenLabs",
        voice="uYXf8XasLslADfZ2MB4u",
        welcome_greeting=f"{WELCOME_GREETING}")
    
    response.append(connect)

    return Response(content=str(response), media_type="text/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    call_sid = None
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "setup":
                call_sid = message["callSid"]
                print(f"Setup for call: {call_sid}")
                websocket.call_sid = call_sid
                sessions[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
                
            elif message["type"] == "prompt":
                print(f"Processing prompt: {message['voicePrompt']}")
                conversation = sessions[websocket.call_sid]
                conversation.append({"role": "user", "content": message["voicePrompt"]})
                
                response = await draft_response(conversation)
                conversation.append({"role": "assistant", "content": response})
                
                await websocket.send_text(
                    json.dumps({
                        "type": "text",
                        "token": response,
                        "last": True
                    })
                )
                print(f"Sent response: {response}")
                
            elif message["type"] == "interrupt":
                print("Handling interruption.")
                
            else:
                print(f"Unknown message type received: {message['type']}")
                
    except WebSocketDisconnect:
        print("WebSocket connection closed")
        if call_sid:
            sessions.pop(call_sid, None)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
    print(f"Server running at http://localhost:{PORT} and {WS_URL}")
